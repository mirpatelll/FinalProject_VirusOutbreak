from flask import Blueprint, jsonify, request, current_app

from models import BoardCell, Game, GamePlayer, Move, Player, db
from game_logic import assign_starting_cells, create_board, get_board_as_2d_array

system_bp = Blueprint("system", __name__)


# ============================================================
# PRODUCTION ENDPOINT
# ============================================================


@system_bp.route("/reset", methods=["POST"])
def reset():
    """Wipe all data from the database."""
    db.drop_all()
    db.create_all()
    return jsonify({"status": "reset"}), 200


# ============================================================
# TEST MODE ENDPOINTS
# ============================================================


def check_test_mode():
    """Check if test mode is enabled and password is correct.
    Returns (allowed, error_response) tuple.
    """
    if not current_app.config.get("TEST_MODE", False):
        return False, (jsonify({"error": "Test mode is not enabled"}), 403)

    password = request.headers.get("X-Test-Password")
    if password != current_app.config.get("TEST_PASSWORD"):
        return False, (jsonify({"error": "Invalid or missing test password"}), 403)

    return True, None


@system_bp.route("/test/games/<int:game_id>/restart", methods=["POST"])
def restart_game(game_id):
    """Reset a game: clear board, clear moves, status back to waiting.
    Player statistics remain unchanged.
    """
    allowed, error = check_test_mode()
    if not allowed:
        return error

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Clear all board cells for this game
    BoardCell.query.filter_by(game_id=game_id).delete()

    # Clear all moves for this game
    Move.query.filter_by(game_id=game_id).delete()

    # Reset all players in this game (un-eliminate them)
    game_players = GamePlayer.query.filter_by(gameId=game_id).all()
    for gp in game_players:
        gp.is_eliminated = False

    # Reset game status
    game.status = "waiting"
    game.current_turn_player_id = None
    game.winner_id = None

    db.session.commit()

    return jsonify({"status": "restarted", "game_id": game_id}), 200


@system_bp.route("/test/games/<int:game_id>/ships", methods=["POST"])
def test_place_starting_cells(game_id):
    """Deterministic starting cell placement for testing.
    Allows the grader to place a player's starting cell at a specific position.
    """
    allowed, error = check_test_mode()
    if not allowed:
        return error

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    player_id = data.get("playerId") or data.get("player_id")
    if not player_id:
        return jsonify({"error": "playerId is required"}), 400

    # Verify player is in this game
    game_player = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player_id
    ).first()
    if not game_player:
        return jsonify({"error": "Player is not in this game"}), 404

    ships = data.get("ships", [])
    if not ships:
        return jsonify({"error": "ships array is required"}), 400

    # Place the cells
    for ship in ships:
        row = ship.get("row")
        col = ship.get("col")

        if row is None or col is None:
            return jsonify({"error": "Each ship needs row and col"}), 400

        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return jsonify({"error": f"Position ({row},{col}) is out of bounds"}), 400

        # Find or create the cell
        cell = BoardCell.query.filter_by(
            game_id=game_id, row=row, col=col
        ).first()

        if cell:
            cell.owner_player_id = player_id
        else:
            cell = BoardCell(
                game_id=game_id,
                row=row,
                col=col,
                owner_player_id=player_id,
            )
            db.session.add(cell)

    db.session.commit()

    return jsonify({
        "status": "placed",
        "playerId": player_id,
        "cells": ships,
    }), 200


@system_bp.route("/test/games/<int:game_id>/board/<player_id>", methods=["GET"])
def test_get_board(game_id, player_id):
    """Reveal board state for a specific player (test mode only)."""
    allowed, error = check_test_mode()
    if not allowed:
        return error

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Verify player is in this game
    game_player = GamePlayer.query.filter_by(
        gameId=game_id, playerId=player_id
    ).first()
    if not game_player:
        return jsonify({"error": "Player is not in this game"}), 404

    # Get all cells owned by this player
    player_cells = BoardCell.query.filter_by(
        game_id=game_id, owner_player_id=player_id
    ).all()

    cells = [{"row": c.row, "col": c.col} for c in player_cells]

    # Also return the full board
    board = get_board_as_2d_array(game) if game.status != "waiting" else None

    return jsonify({
        "game_id": game_id,
        "playerId": player_id,
        "cells": cells,
        "cell_count": len(cells),
        "board": board,
    }), 200