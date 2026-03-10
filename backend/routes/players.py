from flask import Blueprint, jsonify, request

from models import Player, db

players_bp = Blueprint("players", __name__)


def build_player_payload(player):
    """Build player response with both camelCase and snake_case."""
    total_games = getattr(player, "totalGames", 0)
    total_wins = getattr(player, "totalWins", 0)
    total_losses = getattr(player, "totalLosses", 0)
    total_moves = getattr(player, "totalMoves", 0)

    return {
        "playerId": player.player_id,
        "player_id": player.player_id,
        "id": player.player_id,
        "displayName": player.displayName,
        "username": player.displayName,
        "name": player.displayName,
        "createdAt": player.createdAt,
        "totalGames": total_games,
        "totalWins": total_wins,
        "totalLosses": total_losses,
        "totalMoves": total_moves,
    }


@players_bp.route("/players", methods=["POST"])
def create_player():
    """Create a new player. Server generates playerId (INTEGER)."""
    data = request.get_json(silent=True) or {}

    # Reject if client supplies playerId
    if "playerId" in data or "id" in data or "player_id" in data:
        return jsonify({"error": "Client may not supply playerId"}), 400

    username = (
        data.get("username")
        or data.get("playerName")
        or data.get("displayName")
        or data.get("name")
        or ""
    )

    if not isinstance(username, str) or not username.strip():
        return jsonify({"error": "username is required"}), 400

    username = username.strip()

    existing = Player.query.filter_by(displayName=username).first()
    if existing:
        return jsonify({"error": "displayName already taken"}), 409

    player = Player(displayName=username)
    db.session.add(player)
    db.session.commit()

    return jsonify(build_player_payload(player)), 201


@players_bp.route("/players/<int:player_id>", methods=["GET"])
@players_bp.route("/players/<int:player_id>/stats", methods=["GET"])
def get_player(player_id):
    """Get a player's lifetime statistics."""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    return jsonify(build_player_payload(player)), 200