import re
from flask import Blueprint, jsonify, request

from models import Player, db

players_bp = Blueprint("players", __name__)

USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')


@players_bp.route("/players", methods=["POST"])
def create_player():
    data = request.get_json(silent=True) or {}

    if "player_id" in data or "playerId" in data or "id" in data:
        return jsonify({"error": "bad_request",
                        "message": "Client may not supply player_id"}), 400

    username = (data.get("username") or data.get("playerName")
                or data.get("displayName") or data.get("name") or "")

    if not isinstance(username, str) or not username.strip():
        return jsonify({"error": "bad_request", "message": "username is required"}), 400

    username = username.strip()

    if len(username) > 30:
        return jsonify({"error": "bad_request",
                        "message": "Username must be 30 characters or fewer"}), 400

    if not USERNAME_RE.match(username):
        return jsonify({"error": "bad_request",
                        "message": "Username must be alphanumeric with underscores only"}), 400

    if Player.query.filter_by(username=username).first():
        return jsonify({"error": "conflict", "message": "Username already taken"}), 409

    player = Player(username=username)
    db.session.add(player)
    db.session.commit()

    return jsonify(player.stats_dict()), 201


@players_bp.route("/players/<player_id>/stats", methods=["GET"])
@players_bp.route("/players/<player_id>", methods=["GET"])
def get_player_stats(player_id):
    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "not_found", "message": "Player does not exist"}), 404
    return jsonify(player.stats_dict()), 200
