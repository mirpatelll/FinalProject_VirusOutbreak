from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Player(db.Model):
    __tablename__ = "players"

    player_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(
        db.String(30), nullable=False,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )
    games_played = db.Column(db.Integer, nullable=False, default=0)
    wins = db.Column(db.Integer, nullable=False, default=0)
    losses = db.Column(db.Integer, nullable=False, default=0)
    total_shots = db.Column(db.Integer, nullable=False, default=0)
    total_hits = db.Column(db.Integer, nullable=False, default=0)

    game_players = db.relationship("GamePlayer", back_populates="player", lazy=True)

    def stats_dict(self):
        accuracy = 0.0
        if self.total_shots > 0:
            accuracy = round(self.total_hits / self.total_shots, 3)
        return {
            "player_id": self.player_id,
            "username": self.username,
            "games_played": self.games_played,
            "wins": self.wins,
            "losses": self.losses,
            "total_shots": self.total_shots,
            "total_hits": self.total_hits,
            "accuracy": accuracy,
        }


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    grid_size = db.Column(db.Integer, nullable=False, default=8)
    max_players = db.Column(db.Integer, nullable=False, default=2)
    status = db.Column(db.String(20), nullable=False, default="waiting")
    current_turn_index = db.Column(db.Integer, nullable=False, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=True)
    created_at = db.Column(
        db.String(30), nullable=False,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )

    game_players = db.relationship(
        "GamePlayer", back_populates="game", lazy=True,
        order_by="GamePlayer.turn_order",
    )
    ships = db.relationship("Ship", back_populates="game", lazy=True)
    moves = db.relationship("Move", back_populates="game", lazy=True, order_by="Move.id")

    def to_dict(self):
        active = sum(1 for gp in self.game_players if not gp.is_eliminated)
        return {
            "game_id": self.id,
            "id": self.id,
            "grid_size": self.grid_size,
            "max_players": self.max_players,
            "status": self.status,
            "current_turn_index": self.current_turn_index,
            "active_players": active,
            "winner_id": self.winner_id,
            "created_at": self.created_at,
        }


class GamePlayer(db.Model):
    __tablename__ = "game_players"

    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.player_id"), primary_key=True)
    turn_order = db.Column(db.Integer, nullable=False)
    is_eliminated = db.Column(db.Boolean, nullable=False, default=False)
    ships_placed = db.Column(db.Boolean, nullable=False, default=False)

    game = db.relationship("Game", back_populates="game_players")
    player = db.relationship("Player", back_populates="game_players")

    def to_dict(self):
        return {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "turn_order": self.turn_order,
            "is_eliminated": self.is_eliminated,
            "ships_placed": self.ships_placed,
        }


class Ship(db.Model):
    __tablename__ = "ships"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    is_sunk = db.Column(db.Boolean, nullable=False, default=False)

    game = db.relationship("Game", back_populates="ships")

    def to_dict(self):
        return {
            "id": self.id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "row": self.row,
            "col": self.col,
            "is_sunk": self.is_sunk,
        }


class Move(db.Model):
    __tablename__ = "moves"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    result = db.Column(db.String(10), nullable=False)  # "hit" or "miss"
    timestamp = db.Column(
        db.String(30), nullable=False,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )

    game = db.relationship("Game", back_populates="moves")

    def to_dict(self):
        return {
            "move_id": self.id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "row": self.row,
            "col": self.col,
            "result": self.result,
            "timestamp": self.timestamp,
        }