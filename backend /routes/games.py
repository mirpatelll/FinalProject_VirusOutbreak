from flask import Blueprint, jsonify, request
from config import Config
from models import Game, GamePlayer, Move, Player, Ship, ChatMessage, RematchRequest, db

games_bp = Blueprint("games", __name__)

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
    data        = request.get_json(silent=True) or {}
    grid_size   = data.get("grid_size") or data.get("gridSize") or Config.DEFAULT_GRID_SIZE
    max_players = data.get("max_players") or data.get("maxPlayers") or 2

    try:
        grid_size = int(grid_size)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request", "message": f"grid_size must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"}), 400

    if not (Config.MIN_GRID_SIZE <= grid_size <= Config.MAX_GRID_SIZE):
        return jsonify({"error": "bad_request", "message": f"grid_size must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"}), 400

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
    data      = request.get_json(silent=True) or {}
    game      = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404
    if game.status not in ("waiting_setup", "placing"):
        return jsonify({"error": "conflict", "message": "Game already started or finished"}), 409

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    if not db.session.get(Player, player_id):
        return jsonify({"error": "not_found", "message": "Player not found."}), 404

    if GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first():
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
        return jsonify({"error": "bad_request", "message": "Must place exactly 4 ships"}), 400

    occupied_cells = set()
    validated      = []

    for i, s in enumerate(ships_data):
        if not isinstance(s, dict):
            return jsonify({"error": "bad_request", "message": f"Ship {i} invalid format"}), 400

        ship_type   = s.get("ship_type", "").lower()
        orientation = s.get("orientation", "H").upper()
        start_row   = s.get("start_row") if s.get("start_row") is not None else s.get("row")
        start_col   = s.get("start_col") if s.get("start_col") is not None else s.get("col")

        if ship_type not in SHIP_TYPES:
            return jsonify({"error": "bad_request", "message": f"Unknown ship type '{ship_type}'"}), 400
        if orientation not in ("H", "V"):
            return jsonify({"error": "bad_request", "message": "Ship orientation must be H or V"}), 400

        try:
            start_row = int(start_row)
            start_col = int(start_col)
        except (ValueError, TypeError):
            return jsonify({"error": "bad_request", "message": f"Ship {i} missing or invalid coords"}), 400

        length = SHIP_TYPES[ship_type]

        if orientation == "H":
            if not (0 <= start_row < game.grid_size and 0 <= start_col < game.grid_size and start_col + length - 1 < game.grid_size):
                return jsonify({"error": "bad_request", "message": f"Ship '{ship_type}' out of bounds"}), 400
        else:
            if not (0 <= start_row < game.grid_size and 0 <= start_col < game.grid_size and start_row + length - 1 < game.grid_size):
                return jsonify({"error": "bad_request", "message": f"Ship '{ship_type}' out of bounds"}), 400

        cells = []
        for n in range(length):
            cells.append((start_row, start_col + n) if orientation == "H" else (start_row + n, start_col))

        for cell in cells:
            if cell in occupied_cells:
                return jsonify({"error": "bad_request", "message": f"Ship '{ship_type}' overlaps another ship"}), 400
            occupied_cells.add(cell)

        validated.append({"ship_type": ship_type, "length": length, "orientation": orientation, "start_row": start_row, "start_col": start_col})

    placed_types = {v["ship_type"] for v in validated}
    for required in REQUIRED_SHIPS:
        if required not in placed_types:
            return jsonify({"error": "bad_request", "message": f"Missing ship type: {required}"}), 400

    for v in validated:
        db.session.add(Ship(
            game_id=game_id, player_id=player_id,
            ship_type=v["ship_type"], length=v["length"],
            orientation=v["orientation"], start_row=v["start_row"], start_col=v["start_col"],
            row=v["start_row"], col=v["start_col"], hit_mask=0, is_sunk=False,
        ))

    gp.ships_placed = True
    all_gps = GamePlayer.query.filter_by(game_id=game_id).all()
    if len(all_gps) >= 2 and all(g.ships_placed for g in all_gps):
        game.status             = "active"
        game.current_turn_index = 0

    db.session.commit()
    return jsonify({"status": "placed", "message": "ok", "game_id": game_id, "player_id": player_id, "ships": validated}), 200


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
        return jsonify({"error": "forbidden", "message": "Game is not active."}), 403

    player_id = _pid(data)
    row       = data.get("row")
    col       = data.get("col")
    if player_id is None or row is None or col is None:
        return jsonify({"error": "bad_request", "message": "player_id, row, and col are required"}), 400
    if not db.session.get(Player, player_id):
        return jsonify({"error": "forbidden", "message": "Invalid player_id"}), 403

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "Player is not in this game"}), 403

    active_players = GamePlayer.query.filter_by(game_id=game_id, is_eliminated=False).order_by(GamePlayer.turn_order).all()
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

    enemy_ships = Ship.query.filter(Ship.game_id == game_id, Ship.player_id != player_id, Ship.is_sunk == False).all()
    hit_ship  = None
    ship_sunk = False
    for s in enemy_ships:
        if s.hit_cell(row, col):
            hit_ship  = s
            ship_sunk = s.is_sunk
            break

    result = "hit" if hit_ship else "miss"
    db.session.add(Move(game_id=game_id, player_id=player_id, row=row, col=col, result=result))

    player = db.session.get(Player, player_id)
    player.total_shots += 1
    if result == "hit":
        player.total_hits += 1

    for other_gp in active_players:
        if other_gp.player_id == player_id or other_gp.is_eliminated:
            continue
        if Ship.query.filter_by(game_id=game_id, player_id=other_gp.player_id, is_sunk=False).count() == 0:
            other_gp.is_eliminated = True

    active_players = GamePlayer.query.filter_by(game_id=game_id, is_eliminated=False).order_by(GamePlayer.turn_order).all()
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
        current_idx             = next((i for i, ap in enumerate(active_players) if ap.player_id == player_id), 0)
        next_idx                = (current_idx + 1) % len(active_players)
        game.current_turn_index = active_players[next_idx].turn_order
        next_player_id          = active_players[next_idx].player_id

    db.session.commit()

    response = {
        "result": result, "ship_sunk": ship_sunk,
        "ship_type": hit_ship.ship_type if hit_ship else None,
        "next_player_id": next_player_id, "nextPlayerId": next_player_id,
        "game_status": game.status, "status": game.status,
        "playing": game.status == "active", "active": game.status == "active",
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
    return jsonify([m.to_dict() for m in Move.query.filter_by(game_id=game_id).order_by(Move.id).all()]), 200


# ------------------------------------------------------------------
# GET /games/<id>/spectate  — full board state for spectators
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/spectate", methods=["GET"])
def spectate_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    game_dict = game.to_dict()

    # Include all moves so spectators can see every shot
    game_dict["moves"] = [m.to_dict() for m in game.moves]

    # Include player usernames
    players_with_names = []
    for gp in game.game_players:
        player    = db.session.get(Player, gp.player_id)
        remaining = sum(1 for s in game.ships if s.player_id == gp.player_id and not s.is_sunk)
        players_with_names.append({
            "player_id":       gp.player_id,
            "username":        player.username if player else f"Player {gp.player_id}",
            "ships_remaining": remaining,
            "is_eliminated":   gp.is_eliminated,
        })
    game_dict["players"] = players_with_names

    return jsonify(game_dict), 200


# ------------------------------------------------------------------
# GET/POST /games/<id>/chat
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/chat", methods=["GET"])
def get_chat(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    player_id = request.args.get("player_id")
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400
    try:
        player_id = int(player_id)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request", "message": "Invalid player_id"}), 400

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "You are not in this game"}), 403

    messages = ChatMessage.query.filter_by(game_id=game_id).order_by(ChatMessage.id).all()
    return jsonify([m.to_dict() for m in messages]), 200


@games_bp.route("/games/<int:game_id>/chat", methods=["POST"])
def send_chat(game_id):
    data = request.get_json(silent=True) or {}
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "You are not in this game"}), 403

    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "bad_request", "message": "Message cannot be empty"}), 400
    if len(message) > 300:
        return jsonify({"error": "bad_request", "message": "Message too long (300 chars max)"}), 400

    msg = ChatMessage(game_id=game_id, player_id=player_id, message=message)
    db.session.add(msg)
    db.session.commit()
    return jsonify(msg.to_dict()), 201


# ------------------------------------------------------------------
# POST /games/<id>/rematch  — request a rematch
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/rematch", methods=["POST"])
def request_rematch(game_id):
    data = request.get_json(silent=True) or {}
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "not_found", "message": "Game not found"}), 404
    if game.status != "finished":
        return jsonify({"error": "bad_request", "message": "Game is not finished"}), 400

    player_id = _pid(data)
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "forbidden", "message": "You were not in this game"}), 403

    player_ids  = [g.player_id for g in GamePlayer.query.filter_by(game_id=game_id).all()]
    opponent_id = next((pid for pid in player_ids if pid != player_id), None)
    if not opponent_id:
        return jsonify({"error": "bad_request", "message": "No opponent found"}), 400

    # Check if request already exists
    existing = RematchRequest.query.filter_by(
        original_game_id=game_id, requester_id=player_id, status="pending"
    ).first()
    if existing:
        return jsonify(existing.to_dict()), 200

    rematch = RematchRequest(
        original_game_id=game_id,
        requester_id=player_id,
        opponent_id=opponent_id,
        status="pending",
    )
    db.session.add(rematch)
    db.session.commit()
    return jsonify(rematch.to_dict()), 201


# ------------------------------------------------------------------
# GET /games/<id>/rematch  — poll rematch status
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/rematch", methods=["GET"])
def get_rematch(game_id):
    player_id = request.args.get("player_id")
    if not player_id:
        return jsonify({"error": "bad_request", "message": "player_id is required"}), 400
    try:
        player_id = int(player_id)
    except (ValueError, TypeError):
        return jsonify({"error": "bad_request", "message": "Invalid player_id"}), 400

    rematch = RematchRequest.query.filter(
        RematchRequest.original_game_id == game_id,
        (RematchRequest.requester_id == player_id) | (RematchRequest.opponent_id == player_id)
    ).order_by(RematchRequest.id.desc()).first()

    if not rematch:
        return jsonify(None), 200
    return jsonify(rematch.to_dict()), 200


# ------------------------------------------------------------------
# POST /rematch/<id>/respond  — accept or decline
# ------------------------------------------------------------------
@games_bp.route("/rematch/<int:rematch_id>/respond", methods=["POST"])
def respond_rematch(rematch_id):
    data    = request.get_json(silent=True) or {}
    rematch = db.session.get(RematchRequest, rematch_id)
    if not rematch:
        return jsonify({"error": "not_found", "message": "Rematch request not found"}), 404

    player_id = _pid(data)
    if player_id != rematch.opponent_id:
        return jsonify({"error": "forbidden", "message": "Only the opponent can respond"}), 403

    action = (data.get("action") or "").lower()
    if action not in ("accept", "decline"):
        return jsonify({"error": "bad_request", "message": "action must be accept or decline"}), 400

    if action == "decline":
        rematch.status = "declined"
        db.session.commit()
        return jsonify(rematch.to_dict()), 200

    # Accept — create new game with same settings
    original_game = db.session.get(Game, rematch.original_game_id)
    new_game      = Game(
        grid_size   = original_game.grid_size,
        max_players = original_game.max_players,
        status      = "waiting_setup",
    )
    db.session.add(new_game)
    db.session.flush()

    db.session.add(GamePlayer(game_id=new_game.id, player_id=rematch.requester_id,  turn_order=0))
    db.session.add(GamePlayer(game_id=new_game.id, player_id=rematch.opponent_id, turn_order=1))

    rematch.status      = "accepted"
    rematch.new_game_id = new_game.id
    db.session.commit()
    return jsonify(rematch.to_dict()), 200


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
    players = Player.query.order_by(Player.wins.desc(), Player.total_hits.desc()).limit(5).all()
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

    ChatMessage.query.filter_by(game_id=game_id).delete()
    RematchRequest.query.filter_by(original_game_id=game_id).delete()
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
    bp2.add_url_rule("/games",                          "create_game2",    create_game,     methods=["POST"])
    bp2.add_url_rule("/games",                          "list_games2",     list_games,      methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/join",       "join_game2",      join_game,       methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>",            "get_game2",       get_game,        methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/start",      "start_game2",     start_game,      methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/place",      "place_ships2",    place_ships,     methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/fire",       "fire2",           fire,            methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/moves",      "get_moves2",      get_moves,       methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/spectate",   "spectate_game2",  spectate_game,   methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/chat",       "get_chat2",       get_chat,        methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>/chat",       "send_chat2",      send_chat,       methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/rematch",    "request_rematch2",request_rematch, methods=["POST"])
    bp2.add_url_rule("/games/<int:game_id>/rematch",    "get_rematch2",    get_rematch,     methods=["GET"])
    bp2.add_url_rule("/rematch/<int:rematch_id>/respond","respond_rematch2",respond_rematch,methods=["POST"])
    bp2.add_url_rule("/leaderboard",                    "leaderboard2",    leaderboard,     methods=["GET"])
    bp2.add_url_rule("/games/<int:game_id>",            "delete_game2",    delete_game,     methods=["DELETE"])
    app.register_blueprint(bp2)