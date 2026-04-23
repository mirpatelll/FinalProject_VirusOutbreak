import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from config import TestConfig
from models import db


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def player_id(client):
    resp = client.post("/api/players", json={"username": "player1"})
    return resp.get_json()["player_id"]


@pytest.fixture
def player2_id(client):
    resp = client.post("/api/players", json={"username": "player2"})
    return resp.get_json()["player_id"]


@pytest.fixture
def game_id(client, player_id, player2_id):
    resp = client.post("/api/games", json={"grid_size": 8})
    gid = resp.get_json()["id"]
    client.post(f"/api/games/{gid}/join", json={"player_id": player_id})
    client.post(f"/api/games/{gid}/join", json={"player_id": player2_id})
    client.post(f"/api/games/{gid}/start")
    return gid
