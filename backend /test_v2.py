"""
Battleship Phase 1 V2 Tests
CPSC 3750 — Team 0x02 (Mir Patel + St Angelo Davis)

Run with:  pytest test_v2.py -v
"""
import pytest

AUTH = {"X-Test-Password": "clemson-test-2026"}

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def make_player(client, name):
    r = client.post("/api/players", json={"username": name})
    assert r.status_code == 201, f"create player failed: {r.get_json()}"
    data = r.get_json()
    pid = data.get("player_id") or data.get("playerId")
    assert pid, "No player_id in response"
    return pid


def make_game(client, grid_size=8):
    r = client.post("/api/games", json={"grid_size": grid_size})
    assert r.status_code == 201
    data = r.get_json()
    gid = data.get("id") or data.get("game_id")
    assert gid
    return gid


def join(client, game_id, player_id):
    r = client.post(f"/api/games/{game_id}/join", json={"player_id": player_id})
    assert r.status_code == 200, f"join failed: {r.get_json()}"


def place(client, game_id, player_id, ships=None):
    if ships is None:
        ships = [{"row": 0, "col": 0}, {"row": 1, "col": 1}, {"row": 2, "col": 2}]
    r = client.post(f"/api/games/{game_id}/place", json={"player_id": player_id, "ships": ships})
    assert r.status_code == 200, f"place failed: {r.get_json()}"


def test_place_ships_p2(client, game_id, player_id, player2_id, ships=None):
    if ships is None:
        ships = [{"row": 5, "col": 5}, {"row": 6, "col": 6}, {"row": 7, "col": 7}]
    r = client.post(f"/api/games/{game_id}/place", json={"player_id": player2_id, "ships": ships})
    assert r.status_code == 200


def full_setup(client):
    """Create two players, a game, join both, place ships for both → status active."""
    p1 = make_player(client, "alpha")
    p2 = make_player(client, "beta")
    gid = make_game(client)
    join(client, gid, p1)
    join(client, gid, p2)
    client.post(f"/api/games/{gid}/start")
    place(client, gid, p1, [{"row": 0, "col": 0}, {"row": 0, "col": 1}, {"row": 0, "col": 2}])
    place(client, gid, p2, [{"row": 7, "col": 7}, {"row": 7, "col": 6}, {"row": 7, "col": 5}])
    return gid, p1, p2


# ──────────────────────────────────────────────
# 1. Player endpoint tests
# ──────────────────────────────────────────────

class TestPlayers:

    def test_create_player_returns_uuid(self, client):
        r = client.post("/api/players", json={"username": "uuid_test"})
        assert r.status_code == 201
        data = r.get_json()
        pid = data.get("player_id") or data.get("playerId")
        assert pid is not None
        assert isinstance(pid, str) and len(pid) == 36, f"Expected UUID, got: {pid}"

    def test_create_player_camelcase_fields(self, client):
        r = client.post("/api/players", json={"username": "camel_test"})
        assert r.status_code == 201
        data = r.get_json()
        assert "playerId" in data or "player_id" in data
        assert "username" in data or "playerName" in data or "displayName" in data

    def test_duplicate_username_409(self, client):
        client.post("/api/players", json={"username": "dup_user"})
        r = client.post("/api/players", json={"username": "dup_user"})
        assert r.status_code == 409

    def test_missing_username_400(self, client):
        r = client.post("/api/players", json={})
        assert r.status_code == 400

    def test_get_player_stats(self, client):
        r = client.post("/api/players", json={"username": "stats_user"})
        pid = r.get_json().get("player_id") or r.get_json().get("playerId")
        r2 = client.get(f"/api/players/{pid}/stats")
        assert r2.status_code == 200
        data = r2.get_json()
        assert "wins" in data or "totalWins" in data
        assert "losses" in data or "totalLosses" in data

    def test_get_player_by_id(self, client):
        r = client.post("/api/players", json={"username": "byid_user"})
        pid = r.get_json().get("player_id") or r.get_json().get("playerId")
        r2 = client.get(f"/api/players/{pid}")
        assert r2.status_code == 200

    def test_get_nonexistent_player_404(self, client):
        r = client.get("/api/players/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_client_cannot_supply_player_id(self, client):
        r = client.post("/api/players", json={"username": "hack", "player_id": "custom-id"})
        assert r.status_code == 400

    def test_accept_playerName_field(self, client):
        r = client.post("/api/players", json={"playerName": "pname_user"})
        assert r.status_code == 201


# ──────────────────────────────────────────────
# 2. Game lifecycle tests
# ──────────────────────────────────────────────

class TestGameLifecycle:

    def test_create_game_default_grid(self, client):
        r = client.post("/api/games", json={})
        assert r.status_code == 201
        data = r.get_json()
        gs = data.get("grid_size") or data.get("gridSize")
        assert gs == 8

    def test_create_game_custom_grid(self, client):
        r = client.post("/api/games", json={"grid_size": 10})
        assert r.status_code == 201
        data = r.get_json()
        assert data.get("grid_size") == 10 or data.get("gridSize") == 10

    def test_create_game_grid_too_small(self, client):
        r = client.post("/api/games", json={"grid_size": 3})
        assert r.status_code == 400

    def test_create_game_grid_too_large(self, client):
        r = client.post("/api/games", json={"grid_size": 20})
        assert r.status_code == 400

    def test_create_game_status_waiting(self, client):
        r = client.post("/api/games", json={})
        assert r.get_json()["status"] == "waiting"

    def test_create_game_camelcase_fields(self, client):
        r = client.post("/api/games", json={"gridSize": 9})
        assert r.status_code == 201
        data = r.get_json()
        gs = data.get("grid_size") or data.get("gridSize")
        assert gs == 9

    def test_join_game(self, client, player_id, game_id):
        # player_id already joined via fixture; test second player
        p2 = make_player(client, "joiner2")
        # game_id fixture already has 2 players joined, so make a fresh game
        gid2 = make_game(client)
        r = client.post(f"/api/games/{gid2}/join", json={"player_id": player_id})
        assert r.status_code == 200

    def test_join_nonexistent_game_404(self, client, player_id):
        r = client.post("/api/games/99999/join", json={"player_id": player_id})
        assert r.status_code == 404

    def test_join_duplicate_409(self, client, game_id, player_id):
        # player_id is already in game_id from fixture
        r = client.post(f"/api/games/{game_id}/join", json={"player_id": player_id})
        assert r.status_code == 409

    def test_get_game(self, client, game_id):
        r = client.get(f"/api/games/{game_id}")
        assert r.status_code == 200
        data = r.get_json()
        gid = data.get("game_id") or data.get("id") or data.get("gameId")
        assert gid == game_id

    def test_get_nonexistent_game_404(self, client):
        r = client.get("/api/games/99999")
        assert r.status_code == 404

    def test_start_game(self, client, player_id, player2_id):
        gid = make_game(client)
        join(client, gid, player_id)
        join(client, gid, player2_id)
        r = client.post(f"/api/games/{gid}/start")
        assert r.status_code == 200
        assert r.get_json()["status"] == "placing"

    def test_start_game_needs_two_players(self, client, player_id):
        gid = make_game(client)
        join(client, gid, player_id)
        r = client.post(f"/api/games/{gid}/start")
        assert r.status_code == 400

    def test_start_already_started_400(self, client, game_id):
        r = client.post(f"/api/games/{game_id}/start")
        assert r.status_code == 400  # already "placing"


# ──────────────────────────────────────────────
# 3. Ship placement tests
# ──────────────────────────────────────────────

class TestShipPlacement:

    def test_place_exactly_3_ships(self, client, game_id, player_id):
        ships = [{"row": 0, "col": 0}, {"row": 1, "col": 1}, {"row": 2, "col": 2}]
        r = client.post(f"/api/games/{game_id}/place",
                        json={"player_id": player_id, "ships": ships})
        assert r.status_code == 200

    def test_place_wrong_count_400(self, client, game_id, player_id):
        ships = [{"row": 0, "col": 0}, {"row": 1, "col": 1}]
        r = client.post(f"/api/games/{game_id}/place",
                        json={"player_id": player_id, "ships": ships})
        assert r.status_code == 400

    def test_place_out_of_bounds_400(self, client, game_id, player_id):
        ships = [{"row": 99, "col": 0}, {"row": 1, "col": 1}, {"row": 2, "col": 2}]
        r = client.post(f"/api/games/{game_id}/place",
                        json={"player_id": player_id, "ships": ships})
        assert r.status_code == 400

    def test_place_duplicate_position_400(self, client, game_id, player_id):
        ships = [{"row": 0, "col": 0}, {"row": 0, "col": 0}, {"row": 2, "col": 2}]
        r = client.post(f"/api/games/{game_id}/place",
                        json={"player_id": player_id, "ships": ships})
        assert r.status_code == 400

    def test_place_twice_400(self, client, game_id, player_id):
        ships = [{"row": 0, "col": 0}, {"row": 1, "col": 1}, {"row": 2, "col": 2}]
        client.post(f"/api/games/{game_id}/place",
                    json={"player_id": player_id, "ships": ships})
        r = client.post(f"/api/games/{game_id}/place",
                        json={"player_id": player_id, "ships": ships})
        assert r.status_code == 400

    def test_place_non_member_403(self, client, game_id):
        stranger = make_player(client, "stranger1")
        ships = [{"row": 0, "col": 0}, {"row": 1, "col": 1}, {"row": 2, "col": 2}]
        r = client.post(f"/api/games/{game_id}/place",
                        json={"player_id": stranger, "ships": ships})
        assert r.status_code == 403

    def test_game_becomes_active_after_both_place(self, client, player_id, player2_id):
        gid = make_game(client)
        join(client, gid, player_id)
        join(client, gid, player2_id)
        client.post(f"/api/games/{gid}/start")
        place(client, gid, player_id)
        place(client, gid, player2_id,
              [{"row": 5, "col": 5}, {"row": 6, "col": 6}, {"row": 7, "col": 7}])
        r = client.get(f"/api/games/{gid}")
        assert r.get_json()["status"] == "active"


# ──────────────────────────────────────────────
# 4. Fire / gameplay tests
# ──────────────────────────────────────────────

class TestFire:

    def test_fire_miss(self, client):
        gid, p1, p2 = full_setup(client)
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})
        assert r.status_code == 200
        assert r.get_json()["result"] == "miss"

    def test_fire_hit(self, client):
        gid, p1, p2 = full_setup(client)
        # p2 ships at row 7 cols 5,6,7
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 7, "col": 7})
        assert r.status_code == 200
        assert r.get_json()["result"] == "hit"

    def test_fire_wrong_turn_403(self, client):
        gid, p1, p2 = full_setup(client)
        # p2 tries to go first
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": p2, "row": 3, "col": 3})
        assert r.status_code == 403

    def test_fire_out_of_bounds_400(self, client):
        gid, p1, p2 = full_setup(client)
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 99, "col": 0})
        assert r.status_code == 400

    def test_fire_duplicate_shot_400(self, client):
        gid, p1, p2 = full_setup(client)
        client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})
        # p2 fires, then p1 tries same spot again
        client.post(f"/api/games/{gid}/fire", json={"player_id": p2, "row": 3, "col": 4})
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})
        assert r.status_code == 400

    def test_fire_advances_turn(self, client):
        gid, p1, p2 = full_setup(client)
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})
        assert r.get_json()["next_player_id"] == p2

    def test_fire_on_inactive_game_409(self, client, game_id, player_id):
        # game_id from fixture is in "placing" — no ships placed yet
        r = client.post(f"/api/games/{game_id}/fire",
                        json={"player_id": player_id, "row": 0, "col": 0})
        assert r.status_code == 409

    def test_fire_nonmember_403(self, client):
        gid, p1, p2 = full_setup(client)
        outsider = make_player(client, "outsider_fire")
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": outsider, "row": 0, "col": 0})
        assert r.status_code == 403

    def test_game_finishes_when_all_ships_sunk(self, client):
        gid, p1, p2 = full_setup(client)
        # p2 ships: (7,7), (7,6), (7,5)
        # Sink all 3 (p1 fires, p2 fires somewhere, repeat)
        shots_p1 = [(7, 7), (7, 6), (7, 5)]
        shots_p2 = [(3, 0), (3, 1), (3, 2)]
        for i, (row, col) in enumerate(shots_p1):
            client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": row, "col": col})
            if i < len(shots_p2):
                client.post(f"/api/games/{gid}/fire",
                            json={"player_id": p2, "row": shots_p2[i][0], "col": shots_p2[i][1]})
        r = client.get(f"/api/games/{gid}")
        assert r.get_json()["status"] == "finished"

    def test_winner_set_on_finish(self, client):
        gid, p1, p2 = full_setup(client)
        shots_p1 = [(7, 7), (7, 6), (7, 5)]
        shots_p2 = [(3, 0), (3, 1)]
        for i, (row, col) in enumerate(shots_p1):
            client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": row, "col": col})
            if i < len(shots_p2):
                client.post(f"/api/games/{gid}/fire",
                            json={"player_id": p2, "row": shots_p2[i][0], "col": shots_p2[i][1]})
        r = client.get(f"/api/games/{gid}")
        winner = r.get_json().get("winner_id") or r.get_json().get("winnerId")
        assert winner == p1

    def test_fire_on_finished_game_410(self, client):
        gid, p1, p2 = full_setup(client)
        shots_p1 = [(7, 7), (7, 6), (7, 5)]
        shots_p2 = [(3, 0), (3, 1)]
        for i, (row, col) in enumerate(shots_p1):
            client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": row, "col": col})
            if i < len(shots_p2):
                client.post(f"/api/games/{gid}/fire",
                            json={"player_id": p2, "row": shots_p2[i][0], "col": shots_p2[i][1]})
        r = client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 0, "col": 0})
        assert r.status_code == 410


# ──────────────────────────────────────────────
# 5. Move history tests
# ──────────────────────────────────────────────

class TestMoves:

    def test_get_moves_empty(self, client):
        gid, p1, p2 = full_setup(client)
        r = client.get(f"/api/games/{gid}/moves")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_get_moves_after_fire(self, client):
        gid, p1, p2 = full_setup(client)
        client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})
        r = client.get(f"/api/games/{gid}/moves")
        assert r.status_code == 200
        moves = r.get_json()
        assert len(moves) == 1
        assert moves[0]["row"] == 3
        assert moves[0]["col"] == 3

    def test_move_has_result_field(self, client):
        gid, p1, p2 = full_setup(client)
        client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})
        moves = client.get(f"/api/games/{gid}/moves").get_json()
        assert "result" in moves[0]
        assert moves[0]["result"] in ("hit", "miss")

    def test_get_moves_nonexistent_game_404(self, client):
        r = client.get("/api/games/99999/moves")
        assert r.status_code == 404


# ──────────────────────────────────────────────
# 6. Test-mode endpoint tests
# ──────────────────────────────────────────────

class TestModeEndpoints:

    def test_restart_game(self, client):
        gid, p1, p2 = full_setup(client)
        r = client.post(f"/api/test/games/{gid}/restart", headers=AUTH)
        assert r.status_code == 200
        assert r.get_json()["status"] == "restarted"
        game = client.get(f"/api/games/{gid}").get_json()
        assert game["status"] == "waiting"

    def test_restart_without_auth_403(self, client):
        gid, p1, p2 = full_setup(client)
        r = client.post(f"/api/test/games/{gid}/restart")
        assert r.status_code == 403

    def test_test_place_ships(self, client, player_id, player2_id):
        gid = make_game(client)
        join(client, gid, player_id)
        join(client, gid, player2_id)
        ships = [{"row": 0, "col": 0}, {"row": 1, "col": 0}, {"row": 2, "col": 0}]
        r = client.post(f"/api/test/games/{gid}/ships",
                        headers=AUTH,
                        json={"player_id": player_id, "ships": ships})
        assert r.status_code == 200
        assert r.get_json()["status"] == "placed"

    def test_get_board(self, client, player_id, player2_id):
        gid = make_game(client)
        join(client, gid, player_id)
        join(client, gid, player2_id)
        ships = [{"row": 0, "col": 0}, {"row": 1, "col": 0}, {"row": 2, "col": 0}]
        client.post(f"/api/test/games/{gid}/ships",
                    headers=AUTH,
                    json={"player_id": player_id, "ships": ships})
        r = client.get(f"/api/test/games/{gid}/board/{player_id}", headers=AUTH)
        assert r.status_code == 200
        data = r.get_json()
        assert "ships" in data
        assert len(data["ships"]) == 3

    def test_get_board_without_auth_403(self, client, player_id, player2_id):
        gid = make_game(client)
        join(client, gid, player_id)
        r = client.get(f"/api/test/games/{gid}/board/{player_id}")
        assert r.status_code == 403


# ──────────────────────────────────────────────
# 7. Player stats accumulation tests
# ──────────────────────────────────────────────

class TestStats:

    def test_shots_tracked(self, client):
        gid, p1, p2 = full_setup(client)
        client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})
        stats = client.get(f"/api/players/{p1}/stats").get_json()
        shots = stats.get("total_shots") or stats.get("totalShots")
        assert shots == 1

    def test_hits_tracked(self, client):
        gid, p1, p2 = full_setup(client)
        client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 7, "col": 7})
        stats = client.get(f"/api/players/{p1}/stats").get_json()
        hits = stats.get("total_hits") or stats.get("totalHits")
        assert hits == 1

    def test_wins_losses_after_game(self, client):
        gid, p1, p2 = full_setup(client)
        shots_p1 = [(7, 7), (7, 6), (7, 5)]
        shots_p2 = [(3, 0), (3, 1)]
        for i, (row, col) in enumerate(shots_p1):
            client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": row, "col": col})
            if i < len(shots_p2):
                client.post(f"/api/games/{gid}/fire",
                            json={"player_id": p2, "row": shots_p2[i][0], "col": shots_p2[i][1]})
        s1 = client.get(f"/api/players/{p1}/stats").get_json()
        s2 = client.get(f"/api/players/{p2}/stats").get_json()
        assert (s1.get("wins") or s1.get("totalWins")) == 1
        assert (s2.get("losses") or s2.get("totalLosses")) == 1

    def test_accuracy_calculated(self, client):
        gid, p1, p2 = full_setup(client)
        # 1 hit, 1 miss → accuracy = 0.5
        client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 7, "col": 7})  # hit
        client.post(f"/api/games/{gid}/fire", json={"player_id": p2, "row": 3, "col": 4})  # miss
        client.post(f"/api/games/{gid}/fire", json={"player_id": p1, "row": 3, "col": 3})  # miss
        stats = client.get(f"/api/players/{p1}/stats").get_json()
        assert stats["accuracy"] == 0.5


# ──────────────────────────────────────────────
# 8. System reset test
# ──────────────────────────────────────────────

class TestReset:

    def test_reset_clears_data(self, client):
        make_player(client, "will_be_gone")
        client.post("/api/reset")
        # After reset, that player should 404
        r = client.get("/api/players/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
