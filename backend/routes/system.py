from flask import Blueprint, jsonify, request, current_app

from models import BoardCell, Game, GamePlayer, Move, Player, Ship, db
from game_logic import get_board_as_2d_array

system_bp = Blueprint("system", __name__)


@system_bp.route("/reset", methods=["POST"])
def reset():
    """Wipe all data from the database."""
    db.drop_all()
    db.create_all()
    return jsonify({"status": "reset"}), 200


def check_test_mode_header():
    """Verify X-Test-Mode header matches password."""
    test_password = current_app.config.get("TEST_PASSWORD")
    header_password = request.headers.get("X-Test-Mode")
    
    if not header_password or header_password != test_password:
        return False
    return True


@system_bp.route("/test/games/<int:game_id>/restart", methods=["POST"])
def restart_game(game_id):
    """Reset a game: clear board, clear moves, status back to waiting.
    Player statistics remain unchanged (transactional).
    Requires X-Test-Mode header.
    """
    if not check_test_mode_header():
        return jsonify({"error": "Unauthorized"}), 403

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Clear board state and moves
    BoardCell.query.filter_by(game_id=game_id).delete()
    Move.query.filter_by(game_id=game_id).delete()
    Ship.query.filter_by(game_id=game_id).delete()

    # Reset game players
    game_players = GamePlayer.query.filter_by(gameId=game_id).all()
    for gp in game_players:
        gp.is_eliminated = False
        gp.ships_placed = False

    game.status = "waiting"
    game.current_turn_player_id = None
    game.winner_id = None

    db.session.commit()

    return jsonify({
        "status": "restarted",
        "game_id": game_id,
        "gameId": game_id,
    }), 200


@system_bp.route("/test/games/<int:game_id>/ships", methods=["POST"])
def test_place_ships(game_id):
    """Deterministic ship placement for testing.
    Requires X-Test-Mode header.
    
    Request: { "playerId": <int>, "ships": [ {"row": r, "col": c}, ... ] }
    """
    if not check_test_mode_header():
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player_id = data.get("playerId") or data.get("player_id")
    if not player_id:
        return jsonify({"error": "playerId is required"}), 400

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Invalid playerId"}), 400

    game_player = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player_id
    ).first()
    if not game_player:
        return jsonify({"error": "Player is not in this game"}), 400

    ships = data.get("ships") or data.get("cells") or []
    if not ships:
        return jsonify({"error": "ships array is required"}), 400

    placed_cells = []

    for ship in ships:
        row = ship.get("row")
        col = ship.get("col")

        if row is None or col is None:
            return jsonify({"error": "Each ship needs row and col"}), 400

        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return jsonify({
                "error": f"Position ({row},{col}) is out of bounds for grid size {game.grid_size}"
            }), 400

        ship_obj = Ship(
            game_id=game_id,
            player_id=player_id,
            row=row,
            col=col,
        )
        db.session.add(ship_obj)
        placed_cells.append({"row": row, "col": col})

    game_player.ships_placed = True
    db.session.commit()

    return jsonify({
        "status": "placed",
        "game_id": game_id,
        "gameId": game_id,
        "player_id": player_id,
        "playerId": player_id,
        "cells": placed_cells,
        "ships": placed_cells,
    }), 200


@system_bp.route("/test/games/<int:game_id>/board/<int:player_id>", methods=["GET"])
def test_get_board(game_id, player_id):
    """Reveal board state for a specific player (test mode only).
    Requires X-Test-Mode header.
    """
    if not check_test_mode_header():
        return jsonify({"error": "Unauthorized"}), 403

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    game_player = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player_id
    ).first()
    if not game_player:
        return jsonify({"error": "Player is not in this game"}), 404

    player_cells = BoardCell.query.filter_by(
        game_id=game_id, owner_player_id=player_id
    ).all()

    cells = [{"row": c.row, "col": c.col} for c in player_cells]
    board = get_board_as_2d_array(game) if game.status != "waiting" else None

    return jsonify({
        "game_id": game_id,
        "gameId": game_id,
        "player_id": player_id,
        "playerId": player_id,
        "cells": cells,
        "cell_count": len(cells),
        "board": board,
    }), 200