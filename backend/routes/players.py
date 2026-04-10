import re
from flask import Blueprint, jsonify, request

from models import Player, db

players_bp = Blueprint("players", __name__)

USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')


@players_bp.route("/players", methods=["POST"])
def create_player():
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or data.get("playerName")
                or data.get("displayName") or data.get("name") or "")

    if not isinstance(username, str) or not username.strip():
        return jsonify({"error": "bad_request",
                        "message": "Missing required field: username"}), 400

    username = username.strip()

    if len(username) > 30:
        return jsonify({"error": "bad_request",
                        "message": "Username must be 30 characters or fewer"}), 400

    if not USERNAME_RE.match(username):
        return jsonify({"error": "bad_request",
                        "message": "Username must be alphanumeric with underscores only"}), 400

    existing = Player.query.filter_by(username=username).first()
    if existing:
        return jsonify({"error": "conflict",
                        "message": "Username already taken",
                        **existing.stats_dict()}), 409

    player = Player(username=username)
    db.session.add(player)
    db.session.commit()

    return jsonify(player.stats_dict()), 201


@players_bp.route("/players/<int:player_id>/stats", methods=["GET"])
@players_bp.route("/players/<int:player_id>", methods=["GET"])
def get_player_stats(player_id):
    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"error": "not_found",
                        "message": "Player not found"}), 404
    return jsonify(player.stats_dict()), 200


def register_player_routes(app):
    app.register_blueprint(players_bp, url_prefix="/api")
    # Create a second blueprint with same view functions for no-prefix routes
    bp2 = Blueprint("players2", __name__)
    bp2.add_url_rule("/players", "create_player", create_player, methods=["POST"])
    bp2.add_url_rule("/players/<int:player_id>/stats", "get_player_stats_s", get_player_stats, methods=["GET"])
    bp2.add_url_rule("/players/<int:player_id>", "get_player_stats_p", get_player_stats, methods=["GET"])
    app.register_blueprint(bp2)