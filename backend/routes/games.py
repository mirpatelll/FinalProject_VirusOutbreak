from flask import Blueprint, jsonify, request

from config import Config
from models import BoardCell, Game, GamePlayer, Move, Player, db
from game_logic import (
    assign_starting_cells,
    create_board,
    execute_move,
    get_board_as_2d_array,
    validate_move,
)

games_bp = Blueprint("games", __name__)


@games_bp.route("/games", methods=["POST"])
def create_game():
    """Create a new game. Creator auto-joins with turn_order = 0."""
    data = request.get_json() or {}
    grid_size = data.get("grid_size", Config.DEFAULT_GRID_SIZE)

    if not isinstance(grid_size, int) or grid_size < Config.MIN_GRID_SIZE or grid_size > Config.MAX_GRID_SIZE:
        return jsonify({
            "error": f"grid_size must be an integer between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"
        }), 400

    # If creator_id is provided, auto-add them to the game
    creator_id = data.get("creator_id")
    if creator_id:
        creator = Player.query.get(creator_id)
        if not creator:
            return jsonify({"error": "Creator not found"}), 404

    game = Game(grid_size=grid_size)
    db.session.add(game)
    db.session.flush()  # Get game ID

    # Auto-join creator if provided
    if creator_id:
        game_player = GamePlayer(
            gameId=game.id,
            playerId=creator_id,
            turn_order=0,
        )
        db.session.add(game_player)

    db.session.commit()

    return jsonify(game.to_dict()), 201


@games_bp.route("/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    """Join an existing game. Reuses player identity if displayName already exists."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    # Game must exist
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Game must be in waiting status
    if game.status != "waiting":
        return jsonify({"error": "Game is not accepting players"}), 400

    # Support joining by playerId or by playerName
    player = None

    if "playerId" in data:
        player = Player.query.get(data["playerId"])
        if not player:
            return jsonify({"error": "Invalid playerId"}), 403

    elif "playerName" in data or "displayName" in data:
        name = (data.get("playerName") or data.get("displayName", "")).strip()
        if not name:
            return jsonify({"error": "playerName is required"}), 400

        player = Player.query.filter_by(displayName=name).first()
        if not player:
            player = Player(displayName=name)
            db.session.add(player)
            db.session.flush()
    else:
        return jsonify({"error": "playerId or playerName is required"}), 400

    # Check if player already joined this game
    existing = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player.playerId
    ).first()
    if existing:
        return jsonify({"error": "Player already joined this game"}), 400

    # Check max players
    current_count = GamePlayer.query.filter_by(gameId=game_id).count()
    max_players = (game.grid_size * game.grid_size) // 4
    if current_count >= max_players:
        return jsonify({"error": f"Game is full (max {max_players} players)"}), 400

    # Assign turn order
    turn_order = current_count + 1

    game_player = GamePlayer(
        gameId=game_id,
        playerId=player.playerId,
        turn_order=turn_order,
    )
    db.session.add(game_player)
    db.session.commit()

    result = game_player.to_dict()
    result["displayName"] = player.displayName
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

    # Create the board
    create_board(game)

    # Assign starting cells
    positions = assign_starting_cells(game, game_players)

    # Set game to active
    game.status = "active"
    game.current_turn_player_id = game_players[0].playerId

    db.session.commit()

    # Build response
    players_info = []
    for gp, pos in zip(game_players, positions):
        players_info.append({
            "playerId": gp.playerId,
            "turn_order": gp.turn_order,
            "starting_cell": list(pos),
        })

    return jsonify({
        "id": game.id,
        "status": game.status,
        "grid_size": game.grid_size,
        "current_turn_player_id": game.current_turn_player_id,
        "players": players_info,
    }), 200


@games_bp.route("/games/<int:game_id>/move", methods=["POST"])
def make_move(game_id):
    """Make a move in the game."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    required_fields = ["playerId", "source_row", "source_col", "target_row", "target_col"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"{field} is required"}), 400

    # Game must exist
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Player must exist (reject fake playerId)
    player = Player.query.get(data["playerId"])
    if not player:
        return jsonify({"error": "Invalid playerId"}), 403

    # Player must be in this game (reject valid playerId but wrong game)
    game_player = GamePlayer.query.filter_by(
        gameId=game_id, playerId=data["playerId"]
    ).first()
    if not game_player:
        return jsonify({"error": "Player is not in this game"}), 403

    # Game must be active
    if game.status != "active":
        return jsonify({"error": "Game is not active"}), 403

    # Validate the move
    is_valid, error_msg = validate_move(
        game,
        data["playerId"],
        data["source_row"],
        data["source_col"],
        data["target_row"],
        data["target_col"],
    )
    if not is_valid:
        return jsonify({"error": error_msg}), 403

    # Execute the move
    result = execute_move(
        game,
        data["playerId"],
        data["source_row"],
        data["source_col"],
        data["target_row"],
        data["target_col"],
    )
    db.session.commit()

    return jsonify(result), 200


@games_bp.route("/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    """Get full game state including board and players."""
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Get players with cell counts
    game_players = (
        GamePlayer.query.filter_by(gameId=game_id)
        .order_by(GamePlayer.turn_order)
        .all()
    )

    # Calculate current_turn_index
    current_turn_index = None
    players_info = []
    for i, gp in enumerate(game_players):
        player = Player.query.get(gp.playerId)
        cell_count = BoardCell.query.filter_by(
            game_id=game_id, owner_player_id=gp.playerId
        ).count()
        players_info.append({
            "playerId": gp.playerId,
            "displayName": player.displayName if player else None,
            "turn_order": gp.turn_order,
            "is_eliminated": gp.is_eliminated,
            "cell_count": cell_count,
        })
        if gp.playerId == game.current_turn_player_id:
            current_turn_index = i

    # Count active players
    active_players = sum(1 for gp in game_players if not gp.is_eliminated)

    # Get board (only if game has started)
    board = get_board_as_2d_array(game) if game.status != "waiting" else None

    # Get moves
    moves = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()

    return jsonify({
        "id": game.id,
        "grid_size": game.grid_size,
        "status": game.status,
        "current_turn_player_id": game.current_turn_player_id,
        "current_turn_index": current_turn_index,
        "active_players": active_players,
        "winner_id": game.winner_id,
        "players": players_info,
        "board": board,
        "moves": [m.to_dict() for m in moves],
    }), 200


@games_bp.route("/games/<int:game_id>/moves", methods=["GET"])
def get_moves(game_id):
    """Get chronological move history for a game."""
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    moves = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()

    return jsonify([m.to_dict() for m in moves]), 200