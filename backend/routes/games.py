from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from config import Config
from models import Game, GamePlayer, Move, Player, Ship, db

games_bp = Blueprint("games", __name__)


def _pid(data):
    return data.get("player_id") or data.get("playerId")


# ------------------------------------------------------------------
# POST /api/games
# ------------------------------------------------------------------
@games_bp.route("/games", methods=["POST"])
def create_game():
    data = request.get_json(silent=True) or {}

    grid_size = data.get("grid_size") or data.get("gridSize") or Config.DEFAULT_GRID_SIZE
    max_players = data.get("max_players") or data.get("maxPlayers") or 2

    if not isinstance(grid_size, int) or not (Config.MIN_GRID_SIZE <= grid_size <= Config.MAX_GRID_SIZE):
        return jsonify({"error": "bad_request",
                        "message": f"Grid size must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"}), 400

    if not isinstance(max_players, int) or max_players < 2 or max_players > 10:
        return jsonify({"error": "bad_request", "message": "max_players must be between 2 and 10"}), 400

    creator_id = _pid(data) or data.get("creator_id") or data.get("creatorId")
    if creator_id:
        if not db.session.get(Player, creator_id):
            return jsonify({"error": "not_found", "message": "Creator not found"}), 404

    game = Game(grid_size=grid_size, max_players=max_players, status="waiting_setup")
    db.session.add(game)
    db.session.flush()

    if creator_id:
        db.session.add(GamePlayer(game_id=game.id, player_id=creator_id, turn_order=0))

    db.session.commit()
    return jsonify(game.to_dict()), 201


# ------------------------------------------------------------------
# POST /api/games/<id>/join
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status != "waiting_setup":
        return jsonify({"error": "bad_request", "message": "Game is not accepting players"}), 400

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    if not db.session.get(Player, player_id):
        return jsonify({"error": "not_found", "message": "Player does not exist"}), 404

    if GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first():
        return jsonify({"error": "conflict", "message": "Player already in this game"}), 409

    current_count = GamePlayer.query.filter_by(game_id=game_id).count()
    if current_count >= game.max_players:
        return jsonify({"error": "bad_request", "message": "Game is full"}), 400

    db.session.add(GamePlayer(game_id=game_id, player_id=player_id, turn_order=current_count))
    db.session.commit()

    return jsonify({"status": "joined", "game_id": game_id, "player_id": player_id}), 200


# ------------------------------------------------------------------
# GET /api/games/<id>
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404
    return jsonify(game.to_dict()), 200


# ------------------------------------------------------------------
# POST /api/games/<id>/start  (optional convenience — not in V2 spec but harmless)
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/start", methods=["POST"])
def start_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status != "waiting_setup":
        return jsonify({"error": "bad_request", "message": "Game already started or finished"}), 400

    if GamePlayer.query.filter_by(game_id=game_id).count() < 2:
        return jsonify({"error": "bad_request", "message": "Need at least 2 players to start"}), 400

    # stays waiting_setup until all ships placed — this is now a no-op marker
    db.session.commit()
    return jsonify(game.to_dict()), 200


# ------------------------------------------------------------------
# POST /api/games/<id>/place
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status != "waiting_setup":
        return jsonify({"error": "conflict",
                        "message": "Ships can only be placed in waiting_setup phase"}), 409

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    if not db.session.get(Player, player_id):
        return jsonify({"error": "forbidden", "message": "Invalid player_id"}), 403

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "Player is not in this game"}), 403

    if gp.ships_placed:
        return jsonify({"error": "conflict", "message": "Ships already placed"}), 409

    ships = data.get("ships") or []
    if not isinstance(ships, list) or len(ships) != 3:
        return jsonify({"error": "bad_request", "message": "Must place exactly 3 ships"}), 400

    positions = set()
    for i, s in enumerate(ships):
        row, col = s.get("row"), s.get("col")
        if row is None or col is None:
            return jsonify({"error": "bad_request", "message": f"Ship {i} missing row or col"}), 400
        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return jsonify({"error": "bad_request",
                            "message": f"Ship at ({row},{col}) out of bounds"}), 400
        if (row, col) in positions:
            return jsonify({"error": "bad_request",
                            "message": f"Duplicate position ({row},{col})"}), 400
        positions.add((row, col))

    placed = []
    for row, col in positions:
        db.session.add(Ship(game_id=game_id, player_id=player_id, row=row, col=col))
        placed.append({"row": row, "col": col})

    gp.ships_placed = True

    # Auto-transition to "playing" when ALL players have placed ships
    all_gps = GamePlayer.query.filter_by(game_id=game_id).all()
    if len(all_gps) >= 2 and all(g.ships_placed for g in all_gps):
        game.status = "playing"
        game.current_turn_index = 0

    db.session.commit()
    return jsonify({"status": "placed", "game_id": game_id,
                    "player_id": player_id, "ships": placed}), 200


# ------------------------------------------------------------------
# POST /api/games/<id>/fire
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/fire", methods=["POST"])
def fire(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    # V2 spec: fire after finished → 400 Bad Request
    if game.status == "finished":
        return jsonify({"error": "bad_request", "message": "Game is already finished"}), 400

    # Not yet in playing state
    if game.status != "playing":
        return jsonify({"error": "conflict",
                        "message": "Game is not active. All players must place ships first."}), 409

    player_id = _pid(data)
    row = data.get("row")
    col = data.get("col")

    if player_id is None or row is None or col is None:
        return jsonify({"error": "bad_request",
                        "message": "player_id, row, and col are required"}), 400

    if not db.session.get(Player, player_id):
        return jsonify({"error": "forbidden", "message": "Invalid player_id"}), 403

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "Player is not in this game"}), 403

    # Turn enforcement → 403 Forbidden
    active_players = (GamePlayer.query
                      .filter_by(game_id=game_id, is_eliminated=False)
                      .order_by(GamePlayer.turn_order).all())

    if not active_players:
        return jsonify({"error": "bad_request", "message": "No active players"}), 400

    current_player = active_players[game.current_turn_index % len(active_players)]
    if current_player.player_id != player_id:
        return jsonify({"error": "forbidden", "message": "Not your turn"}), 403

    # Bounds check
    if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
        return jsonify({"error": "bad_request", "message": "Coordinates out of bounds"}), 400

    # Duplicate shot → 409 Conflict
    if Move.query.filter_by(game_id=game_id, player_id=player_id, row=row, col=col).first():
        return jsonify({"error": "conflict", "message": "Cell already fired upon"}), 409

    # Check hit
    hit_ship = Ship.query.filter(
        Ship.game_id == game_id,
        Ship.player_id != player_id,
        Ship.row == row,
        Ship.col == col,
        Ship.is_sunk == False,
    ).first()

    result = "hit" if hit_ship else "miss"
    if hit_ship:
        hit_ship.is_sunk = True

    db.session.add(Move(game_id=game_id, player_id=player_id,
                        row=row, col=col, result=result))

    player = db.session.get(Player, player_id)
    player.total_shots += 1
    if result == "hit":
        player.total_hits += 1

    # Check eliminations
    for other_gp in active_players:
        if other_gp.player_id == player_id or other_gp.is_eliminated:
            continue
        if Ship.query.filter_by(game_id=game_id,
                                player_id=other_gp.player_id, is_sunk=False).count() == 0:
            other_gp.is_eliminated = True

    # Refresh active list
    active_players = (GamePlayer.query
                      .filter_by(game_id=game_id, is_eliminated=False)
                      .order_by(GamePlayer.turn_order).all())

    next_player_id = None
    if len(active_players) <= 1:
        game.status = "finished"
        if active_players:
            game.winner_id = active_players[0].player_id
        for g in GamePlayer.query.filter_by(game_id=game_id).all():
            p = db.session.get(Player, g.player_id)
            if p:
                p.games_played += 1
                if g.player_id == game.winner_id:
                    p.wins += 1
                else:
                    p.losses += 1
    else:
        current_idx = next(
            (i for i, ap in enumerate(active_players) if ap.player_id == player_id), 0)
        next_idx = (current_idx + 1) % len(active_players)
        game.current_turn_index = active_players[next_idx].turn_order
        next_player_id = active_players[next_idx].player_id

    db.session.commit()

    response = {
        "result": result,
        "next_player_id": next_player_id,
        "game_status": game.status,
    }
    if game.status == "finished":
        response["winner_id"] = game.winner_id
    return jsonify(response), 200


# ------------------------------------------------------------------
# GET /api/games/<id>/moves
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/moves", methods=["GET"])
def get_moves(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404
    moves = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()
    return jsonify([m.to_dict() for m in moves]), 200
