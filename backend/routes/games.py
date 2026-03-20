from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from config import Config
from models import Game, GamePlayer, Move, Player, Ship, db

games_bp = Blueprint("games", __name__)


# ------------------------------------------------------------------
# POST /games  — Create a new game
# ------------------------------------------------------------------
@games_bp.route("/games", methods=["POST"])
def create_game():
    data = request.get_json(silent=True) or {}

    grid_size = data.get("grid_size") or data.get("gridSize") or Config.DEFAULT_GRID_SIZE
    max_players = data.get("max_players") or data.get("maxPlayers") or 2

    if not isinstance(grid_size, int) or grid_size < Config.MIN_GRID_SIZE or grid_size > Config.MAX_GRID_SIZE:
        return jsonify({
            "error": f"grid_size must be between {Config.MIN_GRID_SIZE} and {Config.MAX_GRID_SIZE}"
        }), 400

    if not isinstance(max_players, int) or max_players < 1:
        return jsonify({"error": "max_players must be >= 1"}), 400

    creator_id = data.get("creator_id") or data.get("creatorId") or data.get("player_id") or data.get("playerId")

    if creator_id:
        creator = db.session.get(Player, creator_id)
        if not creator:
            return jsonify({"error": "Creator not found"}), 404

    game = Game(grid_size=grid_size, max_players=max_players)
    db.session.add(game)
    db.session.flush()

    # Creator auto-added with turn_order = 0
    if creator_id:
        gp = GamePlayer(game_id=game.id, player_id=creator_id, turn_order=0)
        db.session.add(gp)

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
        return jsonify({"error": "Game not found"}), 404

    if game.status != "waiting":
        return jsonify({"error": "Game is not accepting players"}), 400

    player_id = data.get("player_id") or data.get("playerId")
    if not player_id:
        return jsonify({"error": "player_id is required"}), 400

    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "Invalid player_id"}), 404

    existing = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if existing:
        return jsonify({"error": "Player already in this game"}), 400

    current_count = GamePlayer.query.filter_by(game_id=game_id).count()

    if current_count >= game.max_players:
        return jsonify({"error": "Game is full"}), 400

    gp = GamePlayer(game_id=game_id, player_id=player_id, turn_order=current_count)
    db.session.add(gp)
    db.session.commit()

    return jsonify(gp.to_dict()), 200


# ------------------------------------------------------------------
# GET /games/<id>
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    return jsonify(game.to_dict()), 200


# ------------------------------------------------------------------
# POST /games/<id>/place  — Place 3 ships
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player_id = data.get("player_id") or data.get("playerId")
    if not player_id:
        return jsonify({"error": "player_id is required"}), 400

    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "Invalid player_id"}), 403

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "Player is not in this game"}), 403

    if gp.ships_placed:
        return jsonify({"error": "Ships already placed"}), 400

    ships = data.get("ships") or []
    if not isinstance(ships, list) or len(ships) != 3:
        return jsonify({"error": "Must place exactly 3 ships"}), 400

    positions = set()
    for i, s in enumerate(ships):
        row, col = s.get("row"), s.get("col")
        if row is None or col is None:
            return jsonify({"error": f"Ship {i} missing row or col"}), 400
        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return jsonify({"error": f"Ship at ({row},{col}) out of bounds"}), 400
        if (row, col) in positions:
            return jsonify({"error": f"Duplicate position ({row},{col})"}), 400
        positions.add((row, col))

    # Check no overlap with own existing ships (shouldn't happen since ships_placed check above)
    for row, col in positions:
        existing = Ship.query.filter_by(game_id=game_id, player_id=player_id, row=row, col=col).first()
        if existing:
            return jsonify({"error": f"Overlap at ({row},{col})"}), 400

    placed = []
    for row, col in positions:
        ship = Ship(game_id=game_id, player_id=player_id, row=row, col=col)
        db.session.add(ship)
        placed.append({"row": row, "col": col})

    gp.ships_placed = True

    # Check if all players placed — if so, start the game
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
# POST /games/<id>/fire  — Fire a shot
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/fire", methods=["POST"])
def fire(game_id):
    data = request.get_json(silent=True) or {}

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    if game.status != "active":
        return jsonify({"error": "Game is not active. All players must place ships before firing."}), 400

    player_id = data.get("player_id") or data.get("playerId")
    row = data.get("row")
    col = data.get("col")

    if player_id is None or row is None or col is None:
        return jsonify({"error": "player_id, row, and col are required"}), 400

    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "Invalid player_id"}), 403

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "Player is not in this game"}), 403

    # Turn enforcement
    active_players = [
        g for g in GamePlayer.query.filter_by(game_id=game_id, is_eliminated=False)
        .order_by(GamePlayer.turn_order).all()
    ]

    if not active_players:
        return jsonify({"error": "No active players"}), 400

    current_player = active_players[game.current_turn_index % len(active_players)]
    if current_player.player_id != player_id:
        return jsonify({"error": "It is not your turn"}), 403

    # Bounds check
    if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
        return jsonify({"error": "Coordinates out of bounds"}), 400

    # Check for duplicate shot
    existing_move = Move.query.filter_by(
        game_id=game_id, player_id=player_id, row=row, col=col
    ).first()
    if existing_move:
        return jsonify({"error": "Already fired at this location"}), 400

    # Check if hit any opponent's ship
    hit_ship = Ship.query.filter(
        Ship.game_id == game_id,
        Ship.player_id != player_id,
        Ship.row == row,
        Ship.col == col,
        Ship.is_sunk == False,
    ).first()

    result = "miss"
    if hit_ship:
        result = "hit"
        hit_ship.is_sunk = True

    # Log the move
    move = Move(
        game_id=game_id,
        player_id=player_id,
        row=row,
        col=col,
        result=result,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    db.session.add(move)

    # Update player stats
    player.total_shots += 1
    if result == "hit":
        player.total_hits += 1

    # Check eliminations — a player is eliminated when all 3 of their ships are sunk
    eliminated_players = []
    for other_gp in active_players:
        if other_gp.player_id == player_id or other_gp.is_eliminated:
            continue
        remaining = Ship.query.filter_by(
            game_id=game_id, player_id=other_gp.player_id, is_sunk=False
        ).count()
        if remaining == 0:
            other_gp.is_eliminated = True
            eliminated_players.append(other_gp.player_id)

    # Refresh active players after eliminations
    active_players = [
        g for g in GamePlayer.query.filter_by(game_id=game_id, is_eliminated=False)
        .order_by(GamePlayer.turn_order).all()
    ]

    # Check for winner
    next_player_id = None
    if len(active_players) <= 1:
        game.status = "finished"
        if active_players:
            game.winner_id = active_players[0].player_id

        # Update stats for all players
        all_gps = GamePlayer.query.filter_by(game_id=game_id).all()
        for g in all_gps:
            p = db.session.get(Player, g.player_id)
            if p:
                p.games_played += 1
                if g.player_id == game.winner_id:
                    p.wins += 1
                else:
                    p.losses += 1
    else:
        # Advance turn
        current_idx = None
        for i, ap in enumerate(active_players):
            if ap.player_id == player_id:
                current_idx = i
                break
        if current_idx is not None:
            next_idx = (current_idx + 1) % len(active_players)
        else:
            next_idx = 0
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
# GET /games/<id>/moves
# ------------------------------------------------------------------
@games_bp.route("/games/<int:game_id>/moves", methods=["GET"])
def get_moves(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    moves = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()
    return jsonify([m.to_dict() for m in moves]), 200