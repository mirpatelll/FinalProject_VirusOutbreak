from flask import Blueprint, jsonify, request, current_app

from models import Game, GamePlayer, Move, Player, Ship, db

system_bp = Blueprint("system", __name__)


@system_bp.route("/reset", methods=["POST"])
def reset():
    db.drop_all()
    db.create_all()
    return jsonify({"status": "reset"}), 200


def check_test_auth():
    """Check X-Test-Password header is correct."""
    password = request.headers.get("X-Test-Password")
    if not password or password != current_app.config.get("TEST_PASSWORD", "clemson-test-2026"):
        return False
    return True


# ------------------------------------------------------------------
# POST /test/games/<id>/restart
# ------------------------------------------------------------------
@system_bp.route("/test/games/<int:game_id>/restart", methods=["POST"])
def restart_game(game_id):
    if not check_test_auth():
        return jsonify({"error": "Forbidden"}), 403

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    Ship.query.filter_by(game_id=game_id).delete()
    Move.query.filter_by(game_id=game_id).delete()

    for gp in GamePlayer.query.filter_by(game_id=game_id).all():
        gp.is_eliminated = False
        gp.ships_placed = False

    game.status = "waiting"
    game.current_turn_index = 0
    game.winner_id = None
    db.session.commit()

    return jsonify({"status": "restarted", "game_id": game_id}), 200


# ------------------------------------------------------------------
# POST /test/games/<id>/ships  — Deterministic ship placement
# ------------------------------------------------------------------
@system_bp.route("/test/games/<int:game_id>/ships", methods=["POST"])
def test_place_ships(game_id):
    if not check_test_auth():
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player_id = data.get("player_id") or data.get("playerId")
    if not player_id:
        return jsonify({"error": "player_id is required"}), 400

    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "Invalid player_id"}), 400

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "Player is not in this game"}), 400

    ships = data.get("ships") or data.get("cells") or []
    if not ships:
        return jsonify({"error": "ships array is required"}), 400

    placed = []
    for s in ships:
        row, col = s.get("row"), s.get("col")
        if row is None or col is None:
            return jsonify({"error": "Each ship needs row and col"}), 400
        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return jsonify({"error": f"({row},{col}) out of bounds"}), 400

        ship = Ship(game_id=game_id, player_id=player_id, row=row, col=col)
        db.session.add(ship)
        placed.append({"row": row, "col": col})

    gp.ships_placed = True

    # Auto-start if all players have placed
    all_gps = GamePlayer.query.filter_by(game_id=game_id).all()
    if len(all_gps) >= 2 and all(g.ships_placed for g in all_gps):
        game.status = "active"
        game.current_turn_index = 0

    db.session.commit()

    return jsonify({
        "status": "placed",
        "game_id": game_id,
        "player_id": player_id,
        "ships": placed,
    }), 200


# ------------------------------------------------------------------
# GET /test/games/<id>/board/<player_id>
# ------------------------------------------------------------------
@system_bp.route("/test/games/<int:game_id>/board/<int:player_id>", methods=["GET"])
def test_get_board(game_id, player_id):
    if not check_test_auth():
        return jsonify({"error": "Forbidden"}), 403

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "Player is not in this game"}), 404

    ships = Ship.query.filter_by(game_id=game_id, player_id=player_id).all()
    ship_cells = [{"row": s.row, "col": s.col, "is_sunk": s.is_sunk} for s in ships]

    # Build board grid showing ship positions
    board = [[None for _ in range(game.grid_size)] for _ in range(game.grid_size)]
    for s in ships:
        board[s.row][s.col] = {"player_id": s.player_id, "is_sunk": s.is_sunk}

    return jsonify({
        "game_id": game_id,
        "player_id": player_id,
        "ships": ship_cells,
        "board": board,
    }), 200