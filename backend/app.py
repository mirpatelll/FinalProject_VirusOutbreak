from flask import Flask

from config import Config
from database import init_db
from routes.games import games_bp
from routes.players import players_bp
from routes.system import system_bp


def create_app(config_class=Config):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    init_db(app)

    app.register_blueprint(games_bp)
    app.register_blueprint(players_bp)
    app.register_blueprint(system_bp)

    app.register_blueprint(games_bp, url_prefix="/api", name="games_api")
    app.register_blueprint(players_bp, url_prefix="/api", name="players_api")
    app.register_blueprint(system_bp, url_prefix="/api", name="system_api")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)