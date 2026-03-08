from flask import Blueprint, jsonify, request

from models import Player, db

players_bp = Blueprint("players", __name__)


@players_bp.route("/players", methods=["POST"])
def create_player():
    """Create a new player. Server generates playerId."""
    data = request.get_json(silent=True) or {}

    if "playerId" in data or "id" in data or "player_id" in data:
        return jsonify({"error": "Client may not supply playerId"}), 400

    player_name = (
        data.get("playerName")
        or data.get("displayName")
        or data.get("username")
        or data.get("name")
        or ""
    )

    if not isinstance(player_name, str) or not player_name.strip():
        return jsonify({"error": "playerName is required"}), 400

    player_name = player_name.strip()

    existing = Player.query.filter_by(displayName=player_name).first()
    if existing:
        return jsonify({"error": "displayName already taken"}), 409

    player = Player(displayName=player_name)
    db.session.add(player)
    db.session.commit()

    payload = player.to_dict()
    payload["id"] = payload.get("playerId")
    payload["player_id"] = payload.get("playerId")
    payload["username"] = payload.get("displayName")
    payload["name"] = payload.get("displayName")

    if "totalGames" not in payload:
        payload["totalGames"] = payload.get("gamesPlayed", 0)
    if "totalWins" not in payload:
        payload["totalWins"] = payload.get("wins", 0)
    if "totalLosses" not in payload:
        payload["totalLosses"] = payload.get("losses", 0)
    if "totalMoves" not in payload:
        payload["totalMoves"] = payload.get("moves", 0)

    return jsonify(payload), 201


@players_bp.route("/players/<player_id>", methods=["GET"])
def get_player(player_id):
    """Get a player's lifetime statistics."""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    payload = player.to_dict()
    payload["id"] = payload.get("playerId")
    payload["player_id"] = payload.get("playerId")
    payload["username"] = payload.get("displayName")
    payload["name"] = payload.get("displayName")

    if "totalGames" not in payload:
        payload["totalGames"] = payload.get("gamesPlayed", 0)
    if "totalWins" not in payload:
        payload["totalWins"] = payload.get("wins", 0)
    if "totalLosses" not in payload:
        payload["totalLosses"] = payload.get("losses", 0)
    if "totalMoves" not in payload:
        payload["totalMoves"] = payload.get("moves", 0)

    return jsonify(payload), 200