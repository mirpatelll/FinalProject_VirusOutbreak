from flask import Blueprint, jsonify, request

from models import Player, db

players_bp = Blueprint("players", __name__)


@players_bp.route("/players", methods=["POST"])
def create_player():
    data = request.get_json(silent=True) or {}

    # Reject client-supplied player_id
    if "player_id" in data or "playerId" in data or "id" in data:
        return jsonify({"error": "Client may not supply player_id"}), 400

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

    existing = Player.query.filter_by(username=username).first()
    if existing:
        return jsonify({"error": "username already taken"}), 409

    player = Player(username=username)
    db.session.add(player)
    db.session.commit()

    return jsonify({"player_id": player.player_id}), 201


@players_bp.route("/players/<int:player_id>/stats", methods=["GET"])
@players_bp.route("/players/<int:player_id>", methods=["GET"])
def get_player_stats(player_id):
    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    return jsonify(player.stats_dict()), 200