from flask import Blueprint, jsonify, request

from config import Config
from models import Game, GamePlayer, Move, Player, Ship, db

games_bp = Blueprint("games", __name__)

# Ship definitions — must match frontend
SHIP_TYPES = {
    "submarine":  1,
    "destroyer":  2,
    "cruiser":    3,
    "battleship": 4,
}
REQUIRED_SHIPS = ["submarine", "destroyer", "cruiser", "battleship"]


def _pid(data):
    val = data.get("player_id") or data.get("playerId") or data.get("playerld")
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return None


# ------------------------------------------------------------------
# POST /games
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
                        "message": f"grid_size must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"}), 400

    try:
        max_players = int(max_players)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request", "message": "max_players must be between 2 and 10"}), 400

    if max_players < 2 or max_players > 10:
        return jsonify({"error": "bad_request", "message": "max_players must be between 2 and 10"}), 400

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
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    if game.status not in ("waiting_setup", "placing"):
        return jsonify({"error": "conflict", "message": "Game already started or finished"}), 409

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "not_found", "message": "Player not found."}), 404

    existing_gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if existing_gp:
        return jsonify({"error": "conflict", "message": "Player already in this game"}), 409

    current_count = GamePlayer.query.filter_by(game_id=game_id).count()
    if current_count >= game.max_players:
        return jsonify({"error": "conflict", "message": "Game is full"}), 409

    db.session.add(GamePlayer(game_id=game_id, player_id=player_id, turn_order=current_count))
    db.session.commit()

    return jsonify({"status": "joined", "game_id": game_id, "player_id": player_id}), 200


# ------------------------------------------------------------------
# GET /games/<id>
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404
    return jsonify(game.to_dict()), 200


# ------------------------------------------------------------------
# POST /games/<id>/start
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/start", methods=["POST"])
def start_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status not in ("waiting_setup", "placing"):
        return jsonify({"error": "bad_request", "message": "Game already started or finished"}), 400

    if GamePlayer.query.filter_by(game_id=game_id).count() < 2:
        return jsonify({"error": "bad_request", "message": "Need at least 2 players to start"}), 400

    game.status = "placing"
    db.session.commit()
    return jsonify(game.to_dict()), 200


# ------------------------------------------------------------------
# POST /games/<id>/place
# Expects ships array with 4 vessels:
#   submarine(1), destroyer(2), cruiser(3), battleship(4)
# Each: { ship_type, start_row, start_col, orientation }
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status not in ("waiting_setup", "placing"):
        return jsonify({"error": "conflict", "message": "Ships can only be placed in setup phase"}), 409

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    if not db.session.get(Player, player_id):
        return jsonify({"error": "forbidden", "message": "Invalid player_id"}), 403

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "Player is not in this game"}), 403

    if gp.ships_placed:
        return jsonify({"error": "bad_request", "message": "Ships already placed for this player"}), 400

    ships_data = data.get("ships") or []
    if not isinstance(ships_data, list) or len(ships_data) != 4:
        return jsonify({"error": "bad_request",
                        "message": "Must place exactly 4 ships: submarine, destroyer, cruiser, battleship"}), 400

    occupied_cells = set()
    validated = []

    for i, s in enumerate(ships_data):
        if not isinstance(s, dict):
            return jsonify({"error": "bad_request", "message": f"Ship {i} invalid format"}), 400

        ship_type   = s.get("ship_type", "").lower()
        orientation = s.get("orientation", "H").upper()
        start_row   = s.get("start_row")
        start_col   = s.get("start_col")

        if start_row is None:
            start_row = s.get("row")
        if start_col is None:
            start_col = s.get("col")

        if ship_type not in SHIP_TYPES:
            return jsonify({"error": "bad_request",
                            "message": f"Unknown ship type '{ship_type}'"}), 400

        if orientation not in ("H", "V"):
            return jsonify({"error": "bad_request",
                            "message": f"Ship orientation must be 'H' or 'V'"}), 400

        try:
            start_row = int(start_row)
            start_col = int(start_col)
        except (ValueError, TypeError):
            return jsonify({"error": "bad_request",
                            "message": f"Ship {i} missing or invalid start_row/start_col"}), 400

        length = SHIP_TYPES[ship_type]

        if orientation == "H":
            end_col = start_col + length - 1
            if not (0 <= start_row < game.grid_size and 0 <= start_col < game.grid_size and end_col < game.grid_size):
                return jsonify({"error": "bad_request",
                                "message": f"Ship '{ship_type}' goes out of bounds"}), 400
        else:
            end_row = start_row + length - 1
            if not (0 <= start_row < game.grid_size and 0 <= start_col < game.grid_size and end_row < game.grid_size):
                return jsonify({"error": "bad_request",
                                "message": f"Ship '{ship_type}' goes out of bounds"}), 400

        cells = []
        for n in range(length):
            if orientation == "H":
                cells.append((start_row, start_col + n))
            else:
                cells.append((start_row + n, start_col))

        for cell in cells:
            if cell in occupied_cells:
                return jsonify({"error": "bad_request",
                                "message": f"Ship '{ship_type}' overlaps another ship"}), 400
            occupied_cells.add(cell)

        validated.append({
            "ship_type":   ship_type,
            "length":      length,
            "orientation": orientation,
            "start_row":   start_row,
            "start_col":   start_col,
        })

    placed_types = {v["ship_type"] for v in validated}
    for required in REQUIRED_SHIPS:
        if required not in placed_types:
            return jsonify({"error": "bad_request",
                            "message": f"Missing required ship type: {required}"}), 400

    for v in validated:
        db.session.add(Ship(
            game_id     = game_id,
            player_id   = player_id,
            ship_type   = v["ship_type"],
            length      = v["length"],
            orientation = v["orientation"],
            start_row   = v["start_row"],
            start_col   = v["start_col"],
            row         = v["start_row"],
            col         = v["start_col"],
            hit_mask    = 0,
            is_sunk     = False,
        ))

    gp.ships_placed = True

    all_gps = GamePlayer.query.filter_by(game_id=game_id).all()
    if len(all_gps) >= 2 and all(g.ships_placed for g in all_gps):
        game.status             = "active"
        game.current_turn_index = 0

    db.session.commit()
    return jsonify({
        "status":    "placed",
        "message":   "ok",
        "game_id":   game_id,
        "player_id": player_id,
        "ships":     validated,
    }), 200


# ------------------------------------------------------------------
# POST /games/<id>/fire
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/fire", methods=["POST"])
def fire(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game does not exist"}), 404

    if game.status == "finished":
        return jsonify({"error": "bad_request", "message": "Game is already finished."}), 400

    if game.status not in ("active", "playing"):
        return jsonify({"error": "forbidden",
                        "message": "Game is not active. All players must place ships first."}), 403

    player_id = _pid(data)
    row       = data.get("row")
    col       = data.get("col")

    if player_id is None or row is None or col is None:
        return jsonify({"error": "bad_request",
                        "message": "player_id, row, and col are required"}), 400

    if not db.session.get(Player, player_id):
        return jsonify({"error": "forbidden", "message": "Invalid player_id"}), 403

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "Player is not in this game"}), 403

    active_players = (GamePlayer.query
                      .filter_by(game_id=game_id, is_eliminated=False)
                      .order_by(GamePlayer.turn_order).all())

    if not active_players:
        return jsonify({"error": "bad_request", "message": "No active players"}), 400

    current_player = active_players[game.current_turn_index % len(active_players)]
    if current_player.player_id != player_id:
        return jsonify({"error": "forbidden", "message": "Not your turn."}), 403

    try:
        row, col = int(row), int(col)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request", "message": "Invalid coordinates"}), 400

    if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
        return jsonify({"error": "bad_request", "message": "Coordinates out of bounds."}), 400

    if Move.query.filter_by(game_id=game_id, player_id=player_id, row=row, col=col).first():
        return jsonify({"error": "conflict", "message": "Cell already targeted."}), 409

    # Check all unsunk enemy ships for a hit
    enemy_ships = Ship.query.filter(
        Ship.game_id   == game_id,
        Ship.player_id != player_id,
        Ship.is_sunk   == False,
    ).all()

    hit_ship  = None
    ship_sunk = False
    for s in enemy_ships:
        if s.hit_cell(row, col):
            hit_ship  = s
            ship_sunk = s.is_sunk
            break

    result = "hit" if hit_ship else "miss"

    db.session.add(Move(
        game_id   = game_id,
        player_id = player_id,
        row       = row,
        col       = col,
        result    = result,
    ))

    player = db.session.get(Player, player_id)
    player.total_shots += 1
    if result == "hit":
        player.total_hits += 1

    for other_gp in active_players:
        if other_gp.player_id == player_id or other_gp.is_eliminated:
            continue
        all_sunk = Ship.query.filter_by(
            game_id   = game_id,
            player_id = other_gp.player_id,
            is_sunk   = False,
        ).count() == 0
        if all_sunk:
            other_gp.is_eliminated = True

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
        next_idx                = (current_idx + 1) % len(active_players)
        game.current_turn_index = active_players[next_idx].turn_order
        next_player_id          = active_players[next_idx].player_id

    db.session.commit()

    response = {
        "result":         result,
        "ship_sunk":      ship_sunk,
        "ship_type":      hit_ship.ship_type if hit_ship else None,
        "next_player_id": next_player_id,
        "nextPlayerId":   next_player_id,
        "game_status":    game.status,
        "gameStatus":     game.status,
        "status":         game.status,
        "playing":        game.status == "active",
        "active":         game.status == "active",
    }
    if game.status == "finished":
        response["winner_id"] = game.winner_id
        response["winnerId"]  = game.winner_id
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
    return jsonify([m.to_dict() for m in moves]), 200


# ------------------------------------------------------------------
# GET /games
# ------------------------------------------------------------------
@games_bp.route("/games", methods=["GET"])
def list_games():
    status_filter = request.args.get("status")
    q = Game.query
    if status_filter:
        q = q.filter(Game.status == status_filter)
    games = q.order_by(Game.id.desc()).limit(100).all()
    return jsonify([g.to_dict() for g in games]), 200


# ------------------------------------------------------------------
# GET /leaderboard
# ------------------------------------------------------------------
@games_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    players = (Player.query
               .order_by(Player.wins.desc(), Player.total_hits.desc())
               .limit(5).all())
    return jsonify([p.stats_dict() for p in players]), 200


# ------------------------------------------------------------------
# DELETE /games/<id>
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>", methods=["DELETE"])
def delete_game(game_id):
    player_id = request.args.get("player_id")
    if player_id is not None:
        try:
            player_id = int(player_id)
        except (ValueError, TypeError):
            player_id = None
    else:
        data      = request.get_json(silent=True) or {}
        player_id = _pid(data)

    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "You were not in this game"}), 403

    Move.query.filter_by(game_id=game_id).delete()
    Ship.query.filter_by(game_id=game_id).delete()
    GamePlayer.query.filter_by(game_id=game_id).delete()
    db.session.delete(game)
    db.session.commit()

    return jsonify({"deleted": True, "game_id": game_id}), 200


# ------------------------------------------------------------------
# REGISTER
# ------------------------------------------------------------------
def register_game_routes(app):
    app.register_blueprint(games_bp, url_prefix="/api")
    from flask import Blueprint as Bp
    bp2 = Bp("games2", __name__)
    bp2.add_url_rule("/games",                     "create_game2", create_game,  methods=["POST"])
    bp2.add_url_rule("/games",                     "list_games2",  list_games,   methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/join",  "join_game2",   join_game,    methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>",       "get_game2",    get_game,     methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/start", "start_game2",  start_game,   methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/place", "place_ships2", place_ships,  methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/fire",  "fire2",        fire,         methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/moves", "get_moves2",   get_moves,    methods=["GET"])
    bp2.add_url_rule("/leaderboard",               "leaderboard2", leaderboard,  methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>",       "delete_game2", delete_game,  methods=["DELETE"])
    app.register_blueprint(bp2)