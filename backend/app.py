from flask import Flask

from config import Config
from database import init_db
from routes.games import games_bp
from routes.players import players_bp
from routes.system import system_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    init_db(app)

    @app.route("/")
    def health():
        return {"status": "ok"}, 200

    # FIX: Register each blueprint ONCE with /api prefix only.
    # Original code registered each blueprint twice (with and without prefix),
    # causing Flask route conflicts -> all /api/* endpoints returned 404.
    app.register_blueprint(games_bp, url_prefix="/api")
    app.register_blueprint(players_bp, url_prefix="/api")
    app.register_blueprint(system_bp, url_prefix="/api")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
