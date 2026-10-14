from fastapi.testclient import TestClient
from app.main import app 

client = TestClient(app)

def test_default_page_has_10_users():
    r = client.get("/users")
    assert r.status_code == 200
    assert len(r.json()) == 10

def test_page_and_limit():
    r = client.get("/users?page=2&limit=5")
    assert [u["id"] for u in r.json()] == [6, 7, 8, 9, 10]

def test_last_page_is_partial():
    r = client.get("/users?page=3&limit=10")
    assert len(r.json()) == 5

def test_page_zero_is_rejected():
    assert client.get("/users?page=0").status_code == 422


def test_limit_above_100_is_rejected():
    assert client.get("/users?limit=101").status_code == 422


def test_page_past_the_end_is_empty():
    assert client.get("/users?page=99").json() == []


def test_total_count_header():
    assert client.get("/users").headers["X-Total-Count"] == "25"