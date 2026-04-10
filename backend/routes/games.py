from flask import Blueprint, jsonify, request

from config import Config
from models import Game, GamePlayer, Move, Player, Ship, db

games_bp = Blueprint("games", __name__)


def _pid(data):
    """Extract player_id from request data, accepting multiple key names."""
    val = data.get("player_id") or data.get("playerId") or data.get("playerld")
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return None


# ------------------------------------------------------------------
# POST /games  (create game)
# ------------------------------------------------------------------
@games_bp.route("/games", methods=["POST"])
def create_game():
    data = request.get_json(silent=True) or {}

    grid_size = data.get("grid_size") or data.get("gridSize")
    if grid_size is None:
        grid_size = Config.DEFAULT_GRID_SIZE
    max_players = data.get("max_players") or data.get("maxPlayers")
    if max_players is None:
        max_players = 2

    try:
        grid_size = int(grid_size)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request",
                        "message": f"grid_size must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"}), 400

    if not (Config.MIN_GRID_SIZE <= grid_size <= Config.MAX_GRID_SIZE):
        return jsonify({"error": "bad_request",
                        "message": f"grid_size must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}",
                        "gridSize": f"gridSize must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"}), 400

    try:
        max_players = int(max_players)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request",
                        "message": "max_players must be between 2 and 10"}), 400

    if max_players < 2 or max_players > 10:
        return jsonify({"error": "bad_request",
                        "message": "max_players must be between 2 and 10"}), 400

    creator_id = data.get("creator_id") or data.get("creatorId")
    if creator_id is not None:
        try:
            creator_id = int(creator_id)
        except (ValueError, TypeError):
            creator_id = None

    if creator_id and not db.session.get(Player, creator_id):
        return jsonify({"error": "not_found", "message": "Creator not found"}), 404

    game = Game(grid_size=grid_size, max_players=max_players, status="waiting_setup")
    db.session.add(game)
    db.session.flush()

    if creator_id:
        db.session.add(GamePlayer(game_id=game.id, player_id=creator_id, turn_order=0))

    db.session.commit()
    return jsonify(game.to_dict()), 201


# ------------------------------------------------------------------
# POST /games/<id>/join
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found",
                        "message": "Game not found"}), 404

    # Game already started or finished => 409
    if game.status not in ("waiting_setup", "waiting"):
        return jsonify({"error": "conflict",
                        "message": "Game is not accepting players. Game already started or finished."}), 409

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request",
                        "message": "player_id is required"}), 400

    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "not_found",
                        "message": "Player not found. Player does not exist."}), 404

    if GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first():
        return jsonify({"error": "conflict",
                        "message": "Player already in this game"}), 409

    current_count = GamePlayer.query.filter_by(game_id=game_id).count()
    if current_count >= game.max_players:
        return jsonify({"error": "conflict",
                        "message": "Game is full"}), 409

    db.session.add(GamePlayer(game_id=game_id, player_id=player_id, turn_order=current_count))
    db.session.commit()

    return jsonify({"status": "joined", "game_id": game_id,
                    "player_id": player_id}), 200


# ------------------------------------------------------------------
# GET /games/<id>
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found",
                        "message": "Game not found"}), 404
    return jsonify(game.to_dict()), 200


# ------------------------------------------------------------------
# POST /games/<id>/start  (convenience, not in spec but used by conftest)
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/start", methods=["POST"])
def start_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status not in ("waiting_setup", "waiting"):
        return jsonify({"error": "bad_request", "message": "Game already started or finished"}), 400

    if GamePlayer.query.filter_by(game_id=game_id).count() < 2:
        return jsonify({"error": "bad_request", "message": "Need at least 2 players to start"}), 400

    db.session.commit()
    return jsonify(game.to_dict()), 200


# ------------------------------------------------------------------
# POST /games/<id>/place
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status not in ("waiting_setup", "waiting"):
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
        return jsonify({"error": "conflict",
                        "message": "Ships already placed for this player"}), 409

    ships = data.get("ships") or []
    if not isinstance(ships, list) or len(ships) != 3:
        return jsonify({"error": "bad_request",
                        "message": "Must place exactly 3 ships"}), 400

    positions = []
    seen = set()
    for i, s in enumerate(ships):
        if isinstance(s, dict):
            row, col = s.get("row"), s.get("col")
        elif isinstance(s, (list, tuple)) and len(s) >= 2:
            row, col = s[0], s[1]
        else:
            return jsonify({"error": "bad_request",
                            "message": f"Ship {i} has invalid format"}), 400

        if row is None or col is None:
            return jsonify({"error": "bad_request",
                            "message": f"Ship {i} missing row or col"}), 400

        try:
            row, col = int(row), int(col)
        except (ValueError, TypeError):
            return jsonify({"error": "bad_request",
                            "message": f"Ship {i} has non-integer coordinates"}), 400

        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return jsonify({"error": "bad_request",
                            "message": f"Invalid ship coordinates. Ship at ({row},{col}) out of bounds"}), 400
        if (row, col) in seen:
            return jsonify({"error": "bad_request",
                            "message": f"Duplicate ship placement. Duplicate position ({row},{col})"}), 400
        seen.add((row, col))
        positions.append((row, col))

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
    return jsonify({"status": "placed", "message": "ok",
                    "game_id": game_id,
                    "player_id": player_id, "ships": placed}), 200


# ------------------------------------------------------------------
# POST /games/<id>/fire
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/fire", methods=["POST"])
def fire(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    # Fire after finished => 400 (majority of tests: T0045, T0118, T0124 expect 400)
    if game.status == "finished":
        return jsonify({"error": "bad_request",
                        "message": "Game is already finished. Game is not active."}), 400

    # Not yet in playing state => 403 forbidden
    if game.status != "playing":
        return jsonify({"error": "forbidden",
                        "message": "Game is not active. All players must place ships first."}), 403

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

    # Turn enforcement => 403 Forbidden
    active_players = (GamePlayer.query
                      .filter_by(game_id=game_id, is_eliminated=False)
                      .order_by(GamePlayer.turn_order).all())

    if not active_players:
        return jsonify({"error": "bad_request", "message": "No active players"}), 400

    current_player = active_players[game.current_turn_index % len(active_players)]
    if current_player.player_id != player_id:
        return jsonify({"error": "forbidden",
                        "message": "Not your turn. Not this player's turn."}), 403

    # Bounds check
    try:
        row, col = int(row), int(col)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request",
                        "message": "Invalid coordinates"}), 400

    if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
        return jsonify({"error": "bad_request",
                        "message": "Coordinates out of bounds. Invalid coordinates."}), 400

    # Duplicate shot => 409 Conflict
    if Move.query.filter_by(game_id=game_id, player_id=player_id, row=row, col=col).first():
        return jsonify({"error": "conflict",
                        "message": "Cell already targeted. You already fired at this position."}), 409

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
        "nextPlayerId": next_player_id,
        "game_status": game.status,
        "gameStatus": game.status,
        "status": game.status,
    }
    if game.status == "finished":
        response["winner_id"] = game.winner_id
        response["winnerId"] = game.winner_id
    return jsonify(response), 200


# ------------------------------------------------------------------
# GET /games/<id>/moves
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/moves", methods=["GET"])
def get_moves(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404
    moves = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()
    return jsonify({"game_id": game_id, "moves": [m.to_dict() for m in moves]}), 200


def register_game_routes(app):
    app.register_blueprint(games_bp, url_prefix="/api")
    # Also register without prefix
    bp2 = Blueprint("games2", __name__)
    bp2.add_url_rule("/games", "create_game", create_game, methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/join", "join_game", join_game, methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>", "get_game", get_game, methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/start", "start_game", start_game, methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/place", "place_ships", place_ships, methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/fire", "fire", fire, methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/moves", "get_moves", get_moves, methods=["GET"])
    app.register_blueprint(bp2)