from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Player(db.Model):
    """Persistent player accounts with lifetime stats."""
    __tablename__ = "players"

    playerId = db.Column(db.Integer, primary_key=True, autoincrement=True)
    displayName = db.Column(db.String(80), unique=True, nullable=False)
    createdAt = db.Column(
        db.String(30),
        nullable=False,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )
    totalGames = db.Column(db.Integer, nullable=False, default=0)
    totalWins = db.Column(db.Integer, nullable=False, default=0)
    totalLosses = db.Column(db.Integer, nullable=False, default=0)
    totalMoves = db.Column(db.Integer, nullable=False, default=0)

    game_players = db.relationship("GamePlayer", back_populates="player", lazy=True)

    def to_dict(self):
        return {
            "playerId": self.playerId,
            "displayName": self.displayName,
            "createdAt": self.createdAt,
            "totalGames": self.totalGames,
            "totalWins": self.totalWins,
            "totalLosses": self.totalLosses,
            "totalMoves": self.totalMoves,
        }


class Game(db.Model):
    """Game instances with status tracking."""
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    grid_size = db.Column(db.Integer, nullable=False, default=6)
    status = db.Column(db.String(20), nullable=False, default="waiting")
    current_turn_player_id = db.Column(db.Integer, db.ForeignKey("players.playerId"), nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey("players.playerId"), nullable=True)
    created_at = db.Column(
        db.String(30),
        nullable=False,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )

    game_players = db.relationship("GamePlayer", back_populates="game", lazy=True)
    board_cells = db.relationship("BoardCell", back_populates="game", lazy=True)
    moves = db.relationship("Move", back_populates="game", lazy=True, order_by="Move.id")
    current_turn_player = db.relationship("Player", foreign_keys=[current_turn_player_id])
    winner = db.relationship("Player", foreign_keys=[winner_id])

    def to_dict(self):
        return {
            "id": self.id,
            "grid_size": self.grid_size,
            "status": self.status,
            "current_turn_player_id": self.current_turn_player_id,
            "winner_id": self.winner_id,
            "created_at": self.created_at,
        }


class GamePlayer(db.Model):
    """Join table linking players to games. Composite primary key (gameId, playerId)."""
    __tablename__ = "game_players"

    gameId = db.Column(db.Integer, db.ForeignKey("games.id"), primary_key=True)
    playerId = db.Column(db.Integer, db.ForeignKey("players.playerId"), primary_key=True)
    turn_order = db.Column(db.Integer, nullable=False)
    is_eliminated = db.Column(db.Boolean, nullable=False, default=False)

    game = db.relationship("Game", back_populates="game_players")
    player = db.relationship("Player", back_populates="game_players")

    def to_dict(self):
        return {
            "gameId": self.gameId,
            "playerId": self.playerId,
            "turn_order": self.turn_order,
            "is_eliminated": self.is_eliminated,
        }


class BoardCell(db.Model):
    """Grid cells with ownership tracking."""
    __tablename__ = "board_cells"
    __table_args__ = (db.UniqueConstraint("game_id", "row", "col", name="uq_cell_position"),)

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    owner_player_id = db.Column(db.Integer, db.ForeignKey("players.playerId"), nullable=True)

    game = db.relationship("Game", back_populates="board_cells")
    owner = db.relationship("Player", foreign_keys=[owner_player_id])

    def to_dict(self):
        return {
            "id": self.id,
            "game_id": self.game_id,
            "row": self.row,
            "col": self.col,
            "owner_player_id": self.owner_player_id,
        }


class Move(db.Model):
    """Move log with timestamps for every action taken."""
    __tablename__ = "moves"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.playerId"), nullable=False)
    source_row = db.Column(db.Integer, nullable=False)
    source_col = db.Column(db.Integer, nullable=False)
    target_row = db.Column(db.Integer, nullable=False)
    target_col = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(
        db.String(30),
        nullable=False,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )

    game = db.relationship("Game", back_populates="moves")
    player = db.relationship("Player", foreign_keys=[player_id])

    def to_dict(self):
        return {
            "move_id": self.id,
            "game_id": self.game_id,
            "playerId": self.player_id,
            "source": [self.source_row, self.source_col],
            "target": [self.target_row, self.target_col],
            "timestamp": self.timestamp,
        }