from flask import Flask

from config import Config
from database import init_db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    init_db(app)

    @app.route("/")
    def root_health():
        return {"status": "ok"}, 200

    from routes.games import register_game_routes
    from routes.players import register_player_routes
    from routes.system import register_system_routes

    register_game_routes(app)
    register_player_routes(app)
    register_system_routes(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)