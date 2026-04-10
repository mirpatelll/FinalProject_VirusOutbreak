from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _now():
    return datetime.now(timezone.utc).isoformat()


class Player(db.Model):
    __tablename__ = "players"

    player_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.String(30), nullable=False, default=_now)
    games_played = db.Column(db.Integer, nullable=False, default=0)
    wins = db.Column(db.Integer, nullable=False, default=0)
    losses = db.Column(db.Integer, nullable=False, default=0)
    total_shots = db.Column(db.Integer, nullable=False, default=0)
    total_hits = db.Column(db.Integer, nullable=False, default=0)

    game_players = db.relationship("GamePlayer", back_populates="player", lazy=True)

    def stats_dict(self):
        accuracy = 0.0
        if self.total_shots > 0:
            accuracy = round(self.total_hits / self.total_shots, 4)
        return {
            "player_id": self.player_id,
            "playerId": self.player_id,
            "id": self.player_id,
            "username": self.username,
            "playerName": self.username,
            "displayName": self.username,
            "name": self.username,
            "created_at": self.created_at,
            "games_played": self.games_played,
            "games": self.games_played,
            "totalGames": self.games_played,
            "wins": self.wins,
            "totalWins": self.wins,
            "losses": self.losses,
            "totalLosses": self.losses,
            "total_shots": self.total_shots,
            "shots": self.total_shots,
            "totalShots": self.total_shots,
            "total_hits": self.total_hits,
            "hits": self.total_hits,
            "totalHits": self.total_hits,
            "accuracy": accuracy,
        }


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    grid_size = db.Column(db.Integer, nullable=False, default=8)
    max_players = db.Column(db.Integer, nullable=False, default=2)
    status = db.Column(db.String(20), nullable=False, default="waiting_setup")
    current_turn_index = db.Column(db.Integer, nullable=False, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=True)
    created_at = db.Column(db.String(30), nullable=False, default=_now)

    game_players = db.relationship(
        "GamePlayer", back_populates="game", lazy=True,
        order_by="GamePlayer.turn_order",
    )
    ships = db.relationship("Ship", back_populates="game", lazy=True)
    moves = db.relationship("Move", back_populates="game", lazy=True, order_by="Move.id")

    def _current_turn_player_id(self):
        if self.status not in ("playing", "active"):
            return None
        active = [gp for gp in self.game_players if not gp.is_eliminated]
        if not active:
            return None
        return active[self.current_turn_index % len(active)].player_id

    def to_dict(self):
        total_moves = len(self.moves)
        player_ids = [gp.player_id for gp in self.game_players]
        active_count = sum(1 for gp in self.game_players if not gp.is_eliminated)

        players_detail = []
        for gp in self.game_players:
            remaining = sum(1 for s in self.ships
                            if s.player_id == gp.player_id and not s.is_sunk)
            players_detail.append({
                "player_id": gp.player_id,
                "ships_remaining": remaining,
            })

        return {
            "game_id": self.id,
            "id": self.id,
            "gameId": self.id,
            "grid_size": self.grid_size,
            "gridSize": self.grid_size,
            "status": self.status,
            "players": players_detail,
            "current_turn_player_id": self._current_turn_player_id(),
            "total_moves": total_moves,
            "totalMoves": total_moves,
            "max_players": self.max_players,
            "maxPlayers": self.max_players,
            "current_turn_index": self.current_turn_index,
            "active_players": active_count,
            "player_ids": player_ids,
            "playerIds": player_ids,
            "winner_id": self.winner_id,
            "winnerId": self.winner_id,
            "created_at": self.created_at,
            "createdAt": self.created_at,
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
            "status": "joined",
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
    result = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.String(30), nullable=False, default=_now)

    game = db.relationship("Game", back_populates="moves")

    def to_dict(self):
        return {
            "move_id": self.id,
            "move_number": self.id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "row": self.row,
            "col": self.col,
            "result": self.result,
            "timestamp": self.timestamp,
        }