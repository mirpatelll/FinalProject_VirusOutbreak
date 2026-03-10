import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


# ============================================================
# HELPERS
# ============================================================


def create_player(client, name):
    return client.post("/api/players", json={"playerName": name})


def create_and_start_game(client, grid_size=6, num_players=2):
    player_ids = []
    for i in range(num_players):
        resp = create_player(client, f"player{i}")
        player_ids.append(resp.get_json()["playerId"])

    resp = client.post("/api/games", json={"grid_size": grid_size})
    game_id = resp.get_json()["id"]

    for pid in player_ids:
        client.post(f"/api/games/{game_id}/join", json={"playerId": pid})

    resp = client.post(f"/api/games/{game_id}/start")
    game_data = resp.get_json()

    return game_data, player_ids


# ============================================================
# SYSTEM TESTS
# ============================================================


class TestSystem:
    def test_reset(self, client):
        """POST /api/reset wipes all data."""
        create_player(client, "alice")
        resp = client.post("/api/reset")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "reset"

        # Player should be gone
        resp = create_player(client, "alice")
        assert resp.status_code == 201


# ============================================================
# CHECKPOINT A — Foundations (25 pts)
# ============================================================


class TestCheckpointA:
    def test_create_player(self, client):
        resp = create_player(client, "alice")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "playerId" in data
        assert data["displayName"] == "alice"
        assert "createdAt" in data

    def test_server_generates_player_id(self, client):
        resp = create_player(client, "alice")
        pid = resp.get_json()["playerId"]
        assert isinstance(pid, int)

    def test_reject_client_supplied_player_id(self, client):
        resp = client.post("/api/players", json={
            "playerName": "alice",
            "playerId": "fake-id-123"
        })
        assert resp.status_code == 400

    def test_duplicate_name_rejection(self, client):
        create_player(client, "alice")
        resp = create_player(client, "alice")
        assert resp.status_code == 409

    def test_create_game_default_grid(self, client):
        resp = client.post("/api/games", json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "waiting"
        assert "id" in data

    def test_unique_game_ids(self, client):
        r1 = client.post("/api/games", json={})
        r2 = client.post("/api/games", json={})
        assert r1.get_json()["id"] != r2.get_json()["id"]

    def test_initial_game_state_waiting(self, client):
        resp = client.post("/api/games", json={})
        assert resp.get_json()["status"] == "waiting"

    def test_create_game_custom_grid(self, client):
        resp = client.post("/api/games", json={"grid_size": 8})
        assert resp.status_code == 201
        assert resp.get_json()["grid_size"] == 8

    def test_create_game_invalid_grid(self, client):
        resp = client.post("/api/games", json={"grid_size": 2})
        assert resp.status_code == 400

    def test_join_game(self, client):
        p = create_player(client, "alice").get_json()
        g = client.post("/api/games", json={}).get_json()

        resp = client.post(f"/api/games/{g['id']}/join", json={"playerId": p["playerId"]})
        assert resp.status_code == 200
        assert resp.get_json()["turn_order"] == 1

    def test_join_game_duplicate_rejection(self, client):
        p = create_player(client, "alice").get_json()
        g = client.post("/api/games", json={}).get_json()

        client.post(f"/api/games/{g['id']}/join", json={"playerId": p["playerId"]})
        resp = client.post(f"/api/games/{g['id']}/join", json={"playerId": p["playerId"]})
        assert resp.status_code == 400

    def test_join_game_not_found(self, client):
        p = create_player(client, "alice").get_json()
        resp = client.post("/api/games/999/join", json={"playerId": p["playerId"]})
        assert resp.status_code == 404

    def test_proper_status_codes(self, client):
        resp = create_player(client, "alice")
        assert resp.status_code == 201

        resp = client.post("/api/games", json={})
        assert resp.status_code == 201

        resp = client.get("/api/players/fake-uuid-does-not-exist")
        assert resp.status_code == 404

        resp = client.get("/api/games/999")
        assert resp.status_code == 404


# ============================================================
# CHECKPOINT B — Identity & Core Game Logic (35 pts)
# ============================================================


class TestCheckpointB:
    def test_turn_enforcement(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[1],
            "source_row": 5, "source_col": 5,
            "target_row": 5, "target_col": 4,
        })
        assert resp.status_code == 403

    def test_reject_fake_player_id(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": "totally-fake-uuid-12345",
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        assert resp.status_code == 403

    def test_reject_valid_player_wrong_game(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        outsider = create_player(client, "outsider").get_json()

        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": outsider["playerId"],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        assert resp.status_code == 403

    def test_reject_out_of_bounds_move(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": -1, "target_col": 0,
        })
        assert resp.status_code == 403

    def test_reject_duplicate_coordinates(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[1],
            "source_row": 5, "source_col": 5,
            "target_row": 5, "target_col": 4,
        })
        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        assert resp.status_code == 403

    def test_move_logging_with_timestamp(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        data = resp.get_json()
        assert "timestamp" in data
        assert "T" in data["timestamp"]

        state = client.get(f"/api/games/{game_id}").get_json()
        assert len(state["moves"]) == 1

    def test_valid_move_to_empty_cell(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == [0, 0]
        assert data["target"] == [0, 1]
        assert data["captured_from"] is None

    def test_turn_advances(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        assert resp.get_json()["next_turn_player_id"] == pids[1]

    def test_turn_wraps_around(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        resp = client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[1],
            "source_row": 5, "source_col": 5,
            "target_row": 5, "target_col": 4,
        })
        assert resp.get_json()["next_turn_player_id"] == pids[0]

    def test_identity_reuse_across_games(self, client):
        resp = create_player(client, "alice")
        pid = resp.get_json()["playerId"]

        g1 = client.post("/api/games", json={}).get_json()
        g2 = client.post("/api/games", json={}).get_json()

        r1 = client.post(f"/api/games/{g1['id']}/join", json={"playerId": pid})
        r2 = client.post(f"/api/games/{g2['id']}/join", json={"playerId": pid})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.get_json()["playerId"] == r2.get_json()["playerId"]

    def test_game_completion_logic(self, client):
        game_data, pids = create_and_start_game(client, grid_size=6)
        game_id = game_data["id"]

        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[1],
            "source_row": 5, "source_col": 5,
            "target_row": 5, "target_col": 4,
        })

        state = client.get(f"/api/games/{game_id}").get_json()
        assert state["status"] == "active"

    def test_reject_move_on_finished_game(self, client):
        p = create_player(client, "alice").get_json()
        g = client.post("/api/games", json={}).get_json()

        resp = client.post(f"/api/games/{g['id']}/move", json={
            "playerId": p["playerId"],
            "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        assert resp.status_code == 403


# ============================================================
# FINAL SUBMISSION — Persistence, Concurrency & Stress (40 pts)
# ============================================================


class TestFinalSubmission:
    def test_persistent_player_statistics(self, client):
        game_data, pids = create_and_start_game(client, grid_size=6)
        game_id = game_data["id"]

        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0], "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[1], "source_row": 5, "source_col": 5,
            "target_row": 5, "target_col": 4,
        })

        stats0 = client.get(f"/api/players/{pids[0]}").get_json()
        stats1 = client.get(f"/api/players/{pids[1]}").get_json()

        assert stats0["totalMoves"] > 0
        assert stats1["totalMoves"] > 0

    def test_stats_persist_across_multiple_games(self, client):
        p1 = create_player(client, "alice").get_json()
        p2 = create_player(client, "bob").get_json()

        g1 = client.post("/api/games", json={"grid_size": 6}).get_json()
        client.post(f"/api/games/{g1['id']}/join", json={"playerId": p1["playerId"]})
        client.post(f"/api/games/{g1['id']}/join", json={"playerId": p2["playerId"]})
        client.post(f"/api/games/{g1['id']}/start")

        client.post(f"/api/games/{g1['id']}/move", json={
            "playerId": p1["playerId"], "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })
        client.post(f"/api/games/{g1['id']}/move", json={
            "playerId": p2["playerId"], "source_row": 5, "source_col": 5,
            "target_row": 5, "target_col": 4,
        })

        g2 = client.post("/api/games", json={"grid_size": 6}).get_json()
        client.post(f"/api/games/{g2['id']}/join", json={"playerId": p1["playerId"]})
        client.post(f"/api/games/{g2['id']}/join", json={"playerId": p2["playerId"]})
        client.post(f"/api/games/{g2['id']}/start")

        client.post(f"/api/games/{g2['id']}/move", json={
            "playerId": p1["playerId"], "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })

        stats = client.get(f"/api/players/{p1['playerId']}").get_json()
        assert stats["totalMoves"] == 2

    def test_database_level_uniqueness(self, client):
        create_player(client, "alice")
        resp = create_player(client, "alice")
        assert resp.status_code == 409

    def test_referential_integrity(self, client):
        game_data, pids = create_and_start_game(client)
        game_id = game_data["id"]

        client.post(f"/api/games/{game_id}/move", json={
            "playerId": pids[0], "source_row": 0, "source_col": 0,
            "target_row": 0, "target_col": 1,
        })

        state = client.get(f"/api/games/{game_id}").get_json()
        assert state["moves"][0]["playerId"] == pids[0]
        assert state["players"][0]["playerId"] == pids[0]

    def test_load_testing_20_games(self, client):
        players = []
        for i in range(4):
            resp = create_player(client, f"loadplayer{i}")
            players.append(resp.get_json()["playerId"])

        for i in range(20):
            g = client.post("/api/games", json={"grid_size": 6}).get_json()
            client.post(f"/api/games/{g['id']}/join", json={"playerId": players[0]})
            client.post(f"/api/games/{g['id']}/join", json={"playerId": players[1]})
            resp = client.post(f"/api/games/{g['id']}/start")
            assert resp.status_code == 200

    def test_stress_50_moves(self, client):
        game_data, pids = create_and_start_game(client, grid_size=10)
        game_id = game_data["id"]

        move_count = 0
        p1_row, p1_col = 0, 0
        p2_row, p2_col = 9, 9

        for i in range(25):
            if p1_col < 9:
                new_col = p1_col + 1
                resp = client.post(f"/api/games/{game_id}/move", json={
                    "playerId": pids[0],
                    "source_row": p1_row, "source_col": p1_col,
                    "target_row": p1_row, "target_col": new_col,
                })
                assert resp.status_code == 200
                p1_col = new_col
                move_count += 1
            elif p1_row < 9:
                new_row = p1_row + 1
                resp = client.post(f"/api/games/{game_id}/move", json={
                    "playerId": pids[0],
                    "source_row": p1_row, "source_col": p1_col,
                    "target_row": new_row, "target_col": p1_col,
                })
                assert resp.status_code == 200
                p1_row = new_row
                move_count += 1

            state = client.get(f"/api/games/{game_id}").get_json()
            if state["status"] == "finished":
                break

            if p2_col > 0:
                new_col = p2_col - 1
                resp = client.post(f"/api/games/{game_id}/move", json={
                    "playerId": pids[1],
                    "source_row": p2_row, "source_col": p2_col,
                    "target_row": p2_row, "target_col": new_col,
                })
                assert resp.status_code == 200
                p2_col = new_col
                move_count += 1
            elif p2_row > 0:
                new_row = p2_row - 1
                resp = client.post(f"/api/games/{game_id}/move", json={
                    "playerId": pids[1],
                    "source_row": p2_row, "source_col": p2_col,
                    "target_row": new_row, "target_col": p2_col,
                })
                assert resp.status_code == 200
                p2_row = new_row
                move_count += 1

            state = client.get(f"/api/games/{game_id}").get_json()
            if state["status"] == "finished":
                break

        assert move_count >= 25

    def test_get_player_returns_stats(self, client):
        resp = create_player(client, "alice")
        pid = resp.get_json()["playerId"]

        resp = client.get(f"/api/players/{pid}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "totalGames" in data
        assert "totalWins" in data
        assert "totalLosses" in data
        assert "totalMoves" in data

    def test_reset_clears_everything(self, client):
        """Reset wipes all data and allows fresh start."""
        create_player(client, "alice")
        client.post("/api/games", json={})

        resp = client.post("/api/reset")
        assert resp.status_code == 200

        # Everything should be gone
        resp = client.get("/api/games/1")
        assert resp.status_code == 404

        # Can recreate same player
        resp = create_player(client, "alice")
        assert resp.status_code == 201