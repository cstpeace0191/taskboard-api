import pytest
from fastapi.testclient import TestClient

from app.main import TASKS, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_tasks():
    TASKS.clear()
    yield
    TASKS.clear()


def make(task_id: int, title: str = "task", **extra) -> None:
    r = client.post("/tasks", json={"id": task_id, "title": title, **extra})
    assert r.status_code == 201


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_get_task():
    r = client.post("/tasks", json={"id": 1, "title": "write tests"})
    assert r.status_code == 201
    body = client.get("/tasks/1").json()
    assert body["title"] == "write tests"
    assert body["done"] is False
    assert body["priority"] == "medium"


def test_duplicate_id_returns_409():
    make(1, "a")
    r = client.post("/tasks", json={"id": 1, "title": "b"})
    assert r.status_code == 409


def test_empty_title_on_create_returns_422():
    r = client.post("/tasks", json={"id": 1, "title": ""})
    assert r.status_code == 422


def test_missing_task_returns_404():
    assert client.get("/tasks/999").status_code == 404


def test_list_tasks_sorted_by_id():
    make(3)
    make(1)
    make(2)
    ids = [t["id"] for t in client.get("/tasks").json()]
    assert ids == [1, 2, 3]


def test_list_filter_done_true():
    make(1)
    make(2)
    client.patch("/tasks/2", json={"done": True})
    ids = [t["id"] for t in client.get("/tasks", params={"done": "true"}).json()]
    assert ids == [2]


def test_list_filter_done_false_returns_only_incomplete():
    make(1)
    make(2)
    client.patch("/tasks/2", json={"done": True})
    ids = [t["id"] for t in client.get("/tasks", params={"done": "false"}).json()]
    assert ids == [1]


def test_list_filter_done_false():
    make(1)
    make(2)
    client.patch("/tasks/1", json={"done": True})
    client.patch("/tasks/2", json={"done": True})
    assert client.get("/tasks", params={"done": "false"}).json() == []


def test_list_without_done_param_returns_all():
    make(1)
    make(2)
    client.patch("/tasks/2", json={"done": True})
    ids = [t["id"] for t in client.get("/tasks").json()]
    assert ids == [1, 2]


def test_list_invalid_done_value_returns_422():
    assert client.get("/tasks", params={"done": "maybe"}).status_code == 422


def test_list_filter_priority():
    make(1, priority="high")
    make(2, priority="low")
    ids = [t["id"] for t in client.get("/tasks", params={"priority": "high"}).json()]
    assert ids == [1]


def test_update_task():
    make(1, "old")
    r = client.patch("/tasks/1", json={"title": "new", "done": True})
    assert r.status_code == 200
    assert r.json() == {"id": 1, "title": "new", "done": True, "priority": "medium"}


def test_update_missing_task_returns_404():
    assert client.patch("/tasks/42", json={"done": True}).status_code == 404


def test_delete_task():
    make(1)
    assert client.delete("/tasks/1").status_code == 204
    assert client.get("/tasks/1").status_code == 404


def test_delete_missing_task_returns_404():
    r = client.delete("/tasks/999")
    assert r.status_code == 404
    assert r.json() == {"detail": "not found"}


def test_delete_same_task_twice_second_returns_404():
    make(1)
    assert client.delete("/tasks/1").status_code == 204
    r = client.delete("/tasks/1")
    assert r.status_code == 404
    assert r.json() == {"detail": "not found"}


def test_patch_empty_title_returns_422_and_keeps_title():
    make(1, "a")
    r = client.patch("/tasks/1", json={"title": ""})
    assert r.status_code == 422
    assert client.get("/tasks/1").json()["title"] == "a"


def test_patch_title_over_200_chars_returns_422():
    make(1, "a")
    r = client.patch("/tasks/1", json={"title": "x" * 201})
    assert r.status_code == 422
    assert client.get("/tasks/1").json()["title"] == "a"


def test_patch_title_at_200_chars_is_accepted():
    make(1, "a")
    r = client.patch("/tasks/1", json={"title": "x" * 200})
    assert r.status_code == 200
    assert r.json()["title"] == "x" * 200


def test_patch_invalid_priority_returns_422_and_keeps_task():
    make(1, "a", priority="high")
    r = client.patch("/tasks/1", json={"priority": "urgent", "title": "b"})
    assert r.status_code == 422
    assert client.get("/tasks/1").json() == {
        "id": 1,
        "title": "a",
        "done": False,
        "priority": "high",
    }


def test_failed_patch_does_not_change_any_field():
    make(1, "a", priority="low")
    before = client.get("/tasks/1").json()
    r = client.patch("/tasks/1", json={"title": "", "done": True, "priority": "high"})
    assert r.status_code == 422
    assert client.get("/tasks/1").json() == before


def test_patch_null_title_returns_422_and_keeps_title():
    make(1, "a")
    r = client.patch("/tasks/1", json={"title": None})
    assert r.status_code == 422
    assert client.get("/tasks/1").json()["title"] == "a"


def test_patch_null_done_returns_422():
    make(1, "a")
    r = client.patch("/tasks/1", json={"done": None})
    assert r.status_code == 422
    assert client.get("/tasks/1").json()["done"] is False


def test_stats_empty_repo_returns_all_zeros():
    r = client.get("/tasks/stats")
    assert r.status_code == 200
    assert r.json() == {
        "total": 0,
        "done": 0,
        "open": 0,
        "by_priority": {"low": 0, "medium": 0, "high": 0},
    }


def test_stats_counts_done_open_and_priority():
    make(1, priority="medium")
    make(2, priority="medium")
    make(3, priority="high")
    client.patch("/tasks/1", json={"done": True})
    r = client.get("/tasks/stats")
    assert r.status_code == 200
    assert r.json() == {
        "total": 3,
        "done": 1,
        "open": 2,
        "by_priority": {"low": 0, "medium": 2, "high": 1},
    }
