from flask import Blueprint, jsonify, request

from config import Config
from models import BoardCell, Game, GamePlayer, Move, Player, Ship, db
from game_logic import (
    advance_turn,
    assign_starting_cells,
    check_eliminations,
    check_winner,
    create_board,
    execute_move,
    get_board_as_2d_array,
    validate_move,
    validate_ship_placement,
)

games_bp = Blueprint("games", __name__)


@games_bp.route("/games", methods=["POST"])
def create_game():
    """Create a new game."""
    data = request.get_json(silent=True) or {}

    grid_size = data.get("grid_size") or data.get("gridSize") or Config.DEFAULT_GRID_SIZE

    if not isinstance(grid_size, int) or grid_size < Config.MIN_GRID_SIZE or grid_size > Config.MAX_GRID_SIZE:
        return jsonify({
            "error": f"grid_size must be an integer between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"
        }), 400

    creator_id = (
        data.get("creator_id")
        or data.get("creatorId")
        or data.get("player_id")
        or data.get("playerId")
    )

    if creator_id:
        creator = Player.query.get(creator_id)
        if not creator:
            return jsonify({"error": "Creator not found"}), 404

    game = Game(grid_size=grid_size)
    db.session.add(game)
    db.session.flush()

    if creator_id:
        game_player = GamePlayer(
            gameId=game.id,
            playerId=creator_id,
            turn_order=0,
        )
        db.session.add(game_player)

    db.session.commit()

    payload = game.to_dict()
    return jsonify(payload), 201


@games_bp.route("/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    """Join an existing game."""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    if game.status != "waiting":
        return jsonify({"error": "Game is not accepting players"}), 400

    player = None

    incoming_player_id = data.get("playerId") or data.get("player_id")
    if incoming_player_id:
        player = Player.query.get(incoming_player_id)
        if not player:
            return jsonify({"error": "Invalid playerId"}), 403
    else:
        name = (
            data.get("playerName")
            or data.get("displayName")
            or data.get("username")
            or data.get("name")
            or ""
        )
        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "playerId or playerName is required"}), 400

        name = name.strip()
        player = Player.query.filter_by(displayName=name).first()
        if not player:
            player = Player(displayName=name)
            db.session.add(player)
            db.session.flush()

    existing = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player.player_id
    ).first()
    if existing:
        return jsonify({"error": "Player already joined this game"}), 400

    current_count = GamePlayer.query.filter_by(gameId=game_id).count()
    
    turn_order = current_count + 1

    game_player = GamePlayer(
        gameId=game_id,
        playerId=player.player_id,
        turn_order=turn_order,
    )
    db.session.add(game_player)
    db.session.commit()

    result = game_player.to_dict()
    result["displayName"] = player.displayName
    result["game_id"] = game_id
    result["gameId"] = game_id
    result["player_id"] = player.player_id
    result["playerId"] = player.player_id
    result["username"] = player.displayName
    return jsonify(result), 200


@games_bp.route("/games/<int:game_id>/start", methods=["POST"])
def start_game(game_id):
    """Start a game. Requires at least 2 players."""
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    if game.status != "waiting":
        return jsonify({"error": "Game is not in waiting status"}), 400

    game_players = (
        GamePlayer.query.filter_by(gameId=game_id)
        .order_by(GamePlayer.turn_order)
        .all()
    )

    if len(game_players) < Config.MIN_PLAYERS_TO_START:
        return jsonify({
            "error": f"Need at least {Config.MIN_PLAYERS_TO_START} players to start"
        }), 400

    create_board(game)
    positions = assign_starting_cells(game, game_players)

    game.status = "active"
    game.current_turn_player_id = game_players[0].playerId

    db.session.commit()

    players_info = []
    for gp, (_, row, col) in zip(game_players, positions):
        player_payload = {
            "playerId": gp.playerId,
            "turn_order": gp.turn_order,
            "starting_cell": [row, col],
        }
        players_info.append(player_payload)

    payload = {
        "id": game.id,
        "game_id": game.id,
        "gameId": game.id,
        "status": game.status,
        "grid_size": game.grid_size,
        "current_turn_player_id": game.current_turn_player_id,
        "players": players_info,
    }
    return jsonify(payload), 200


@games_bp.route("/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    """Place ships (3 per player, 1 cell each)."""
    data = request.get_json(silent=True) or {}

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player_id = data.get("playerId") or data.get("player_id")
    if not player_id:
        return jsonify({"error": "playerId is required"}), 400

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Invalid playerId"}), 403

    game_player = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player_id
    ).first()
    if not game_player:
        return jsonify({"error": "Player is not in this game"}), 403

    ships = data.get("ships") or []

    is_valid, error_msg = validate_ship_placement(game, player_id, ships)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    placed = []
    for ship in ships:
        row = ship.get("row")
        col = ship.get("col")

        ship_obj = Ship(
            game_id=game_id,
            player_id=player_id,
            row=row,
            col=col,
        )
        db.session.add(ship_obj)
        placed.append({"row": row, "col": col})

    game_player.ships_placed = True
    db.session.commit()

    return jsonify({
        "status": "placed",
        "game_id": game_id,
        "gameId": game_id,
        "player_id": player_id,
        "playerId": player_id,
        "ships": placed,
    }), 200


@games_bp.route("/games/<int:game_id>/move", methods=["POST"])
def make_move(game_id):
    """Make a territorial control move (expand from owned cell)."""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    player_id = data.get("playerId") if data.get("playerId") is not None else data.get("player_id")
    source_row = data.get("source_row") if data.get("source_row") is not None else data.get("sourceRow")
    source_col = data.get("source_col") if data.get("source_col") is not None else data.get("sourceCol")
    target_row = data.get("target_row") if data.get("target_row") is not None else data.get("targetRow")
    target_col = data.get("target_col") if data.get("target_col") is not None else data.get("targetCol")

    required_values = {
        "playerId": player_id,
        "source_row": source_row,
        "source_col": source_col,
        "target_row": target_row,
        "target_col": target_col,
    }
    for field, value in required_values.items():
        if value is None:
            return jsonify({"error": f"{field} is required"}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Invalid playerId"}), 403

    game_player = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player_id
    ).first()
    if not game_player:
        return jsonify({"error": "Player is not in this game"}), 403

    if game.status != "active":
        return jsonify({"error": "Game is not active"}), 403

    is_valid, error_msg = validate_move(
        game, player_id, source_row, source_col, target_row, target_col
    )
    if not is_valid:
        return jsonify({"error": error_msg}), 403

    result = execute_move(
        game, player_id, source_row, source_col, target_row, target_col
    )
    db.session.commit()

    if isinstance(result, dict):
        result.setdefault("player_id", player_id)
        result.setdefault("playerId", player_id)
        result.setdefault("game_id", game_id)
        result.setdefault("gameId", game_id)

    return jsonify(result), 200


@games_bp.route("/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    """Get full game state including board and players."""
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    game_players = (
        GamePlayer.query.filter_by(gameId=game_id)
        .order_by(GamePlayer.turn_order)
        .all()
    )

    current_turn_index = None
    players_info = []
    for i, gp in enumerate(game_players):
        player = Player.query.get(gp.playerId)
        cell_count = BoardCell.query.filter_by(
            game_id=game_id, owner_player_id=gp.playerId
        ).count()

        player_payload = {
            "playerId": gp.playerId,
            "displayName": player.displayName if player else None,
            "turn_order": gp.turn_order,
            "is_eliminated": gp.is_eliminated,
            "cell_count": cell_count,
        }
        players_info.append(player_payload)

        if gp.playerId == game.current_turn_player_id:
            current_turn_index = i

    active_players = sum(1 for gp in game_players if not gp.is_eliminated)
    board = get_board_as_2d_array(game) if game.status != "waiting" else None
    moves = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()

    payload = {
        "id": game.id,
        "game_id": game.id,
        "gameId": game.id,
        "grid_size": game.grid_size,
        "status": game.status,
        "current_turn_player_id": game.current_turn_player_id,
        "current_turn_index": current_turn_index,
        "active_players": active_players,
        "winner_id": game.winner_id,
        "players": players_info,
        "board": board,
        "moves": [m.to_dict() for m in moves],
    }
    return jsonify(payload), 200


@games_bp.route("/games/<int:game_id>/moves", methods=["GET"])
def get_moves(game_id):
    """Get chronological move history for a game."""
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    moves = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()
    move_payloads = [m.to_dict() for m in moves]

    return jsonify(move_payloads), 200