import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("SECRET_KEY", "test-secret-key-for-jwt-32-bytes-min")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_app.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

DB_PATH = Path("test_app.db")


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value

    async def exists(self, key: str) -> int:
        return int(key in self.store)

    async def close(self):
        return None


from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    DB_PATH.unlink(missing_ok=True)
    yield
    DB_PATH.unlink(missing_ok=True)


@pytest.fixture()
def client_and_redis():
    fake_redis = FakeRedis()
    with patch("app.main.Redis.from_url", return_value=fake_redis):
        with TestClient(app) as client:
            yield client, fake_redis


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["refresh_token"]
    return data


@pytest.mark.parametrize(
    ("username", "password", "expected_title"),
    [
        ("role1_user", "password1", "Role 1 secret"),
        ("role2_user", "password2", "Role 2 secret"),
    ],
)
def test_role_based_content_access(client_and_redis, username, password, expected_title):
    client, _redis = client_and_redis
    tokens = login(client, username, password)

    response = client.get("/content", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200

    titles = {item["title"] for item in response.json()}
    assert "Common content" in titles
    assert expected_title in titles
    other_title = "Role 2 secret" if expected_title == "Role 1 secret" else "Role 1 secret"
    assert other_title not in titles


def test_refresh_rotates_and_rejects_reuse(client_and_redis):
    client, redis = client_and_redis
    tokens = login(client, "role1_user", "password1")

    first_refresh = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first_refresh.status_code == 200

    reused_refresh = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused_refresh.status_code == 401

    assert any(key.startswith("blacklist:") for key in redis.store)


def test_logout_revokes_access_token(client_and_redis):
    client, _redis = client_and_redis
    tokens = login(client, "role2_user", "password2")

    logout = client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert logout.status_code == 200

    response = client.get("/content", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 401
