from flask import Blueprint, jsonify, request, current_app

from models import Game, GamePlayer, Move, Player, Ship, db

system_bp = Blueprint("system", __name__)


def _check_auth():
    pw = request.headers.get("X-Test-Password") or request.headers.get("X-Test-Mode")
    return pw == current_app.config.get("TEST_PASSWORD", "clemson-test-2026")


# POST /api/reset
@system_bp.route("/reset", methods=["POST"])
def reset():
    db.drop_all()
    db.create_all()
    return jsonify({"status": "reset"}), 200


# GET /api/health
@system_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# GET /api/version
@system_bp.route("/version", methods=["GET"])
def version():
    return jsonify({"api_version": "2.3.0", "spec_version": "2.3"}), 200


# POST /api/test/games/<id>/restart
@system_bp.route("/test/games/<int:game_id>/restart", methods=["POST"])
def restart_game(game_id):
    if not _check_auth():
        return jsonify({"error": "forbidden", "message": "Invalid test password"}), 403

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    Ship.query.filter_by(game_id=game_id).delete()
    Move.query.filter_by(game_id=game_id).delete()

    for gp in GamePlayer.query.filter_by(game_id=game_id).all():
        gp.is_eliminated = False
        gp.ships_placed = False

    game.status = "waiting_setup"
    game.current_turn_index = 0
    game.winner_id = None
    db.session.commit()

    return jsonify({"status": "reset", "game_id": game_id}), 200


# POST /api/test/games/<id>/ships
@system_bp.route("/test/games/<int:game_id>/ships", methods=["POST"])
def test_place_ships(game_id):
    if not _check_auth():
        return jsonify({"error": "forbidden", "message": "Invalid test password"}), 403

    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    player_id = data.get("player_id") or data.get("playerId")
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    if not db.session.get(Player, player_id):
        return jsonify({"error": "bad_request", "message": "Invalid player_id"}), 400

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "bad_request", "message": "Player is not in this game"}), 400

    ships = data.get("ships") or data.get("cells") or []
    if not ships:
        return jsonify({"error": "bad_request", "message": "ships array is required"}), 400

    placed = []
    for s in ships:
        row, col = s.get("row"), s.get("col")
        if row is None or col is None:
            return jsonify({"error": "bad_request", "message": "Each ship needs row and col"}), 400
        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return jsonify({"error": "bad_request",
                            "message": f"({row},{col}) out of bounds"}), 400
        db.session.add(Ship(game_id=game_id, player_id=player_id, row=row, col=col))
        placed.append({"row": row, "col": col})

    gp.ships_placed = True

    all_gps = GamePlayer.query.filter_by(game_id=game_id).all()
    if len(all_gps) >= 2 and all(g.ships_placed for g in all_gps):
        game.status = "playing"
        game.current_turn_index = 0

    db.session.commit()
    return jsonify({"status": "placed", "game_id": game_id,
                    "player_id": player_id, "ships": placed}), 200


# GET /api/test/games/<id>/board/<player_id>
@system_bp.route("/test/games/<int:game_id>/board/<player_id>", methods=["GET"])
def test_get_board(game_id, player_id):
    if not _check_auth():
        return jsonify({"error": "forbidden", "message": "Invalid test password"}), 403

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    if not db.session.get(Player, player_id):
        return jsonify({"error": "not_found", "message": "Player not found"}), 404

    if not GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first():
        return jsonify({"error": "not_found", "message": "Player is not in this game"}), 404

    ships = Ship.query.filter_by(game_id=game_id, player_id=player_id).all()
    ship_cells = [{"row": s.row, "col": s.col, "is_sunk": s.is_sunk} for s in ships]
    board = [[None] * game.grid_size for _ in range(game.grid_size)]
    for s in ships:
        board[s.row][s.col] = {"player_id": s.player_id, "is_sunk": s.is_sunk}

    return jsonify({"game_id": game_id, "player_id": player_id,
                    "ships": ship_cells, "board": board}), 200
