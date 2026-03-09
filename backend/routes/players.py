from flask import Blueprint, jsonify, request

from models import Player, db

players_bp = Blueprint("players", __name__)


@players_bp.route("/players", methods=["POST"])
def create_player():
    """Create a new player."""
    data = request.get_json(silent=True) or {}

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

    return jsonify({
        "playerId": player.playerId,
        "player_id": player.playerId,
        "id": player.playerId,
        "displayName": player.displayName,
        "username": player.displayName,
        "name": player.displayName,
        "createdAt": player.createdAt,
        "totalGames": player.totalGames,
        "totalWins": player.totalWins,
        "totalLosses": player.totalLosses,
        "totalMoves": player.totalMoves,
    }), 201


@players_bp.route("/players/<int:player_id>", methods=["GET"])
@players_bp.route("/players/<int:player_id>/stats", methods=["GET"])
def get_player(player_id):
    """Get a player's lifetime statistics."""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    return jsonify({
        "playerId": player.playerId,
        "player_id": player.playerId,
        "id": player.playerId,
        "displayName": player.displayName,
        "username": player.displayName,
        "name": player.displayName,
        "createdAt": player.createdAt,
        "totalGames": player.totalGames,
        "totalWins": player.totalWins,
        "totalLosses": player.totalLosses,
        "totalMoves": player.totalMoves,
    }), 200