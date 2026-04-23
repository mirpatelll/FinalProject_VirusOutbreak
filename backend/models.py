from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _now():
    return datetime.now(timezone.utc).isoformat()


class Player(db.Model):
    __tablename__ = "players"

    player_id    = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username     = db.Column(db.String(80), unique=True, nullable=False)
    created_at   = db.Column(db.String(30), nullable=False, default=_now)
    games_played = db.Column(db.Integer, nullable=False, default=0)
    wins         = db.Column(db.Integer, nullable=False, default=0)
    losses       = db.Column(db.Integer, nullable=False, default=0)
    total_shots  = db.Column(db.Integer, nullable=False, default=0)
    total_hits   = db.Column(db.Integer, nullable=False, default=0)

    game_players = db.relationship("GamePlayer", back_populates="player", lazy=True)

    def stats_dict(self):
        accuracy = 0.0
        if self.total_shots > 0:
            accuracy = round(self.total_hits / self.total_shots, 4)
        win_rate = 0.0
        if self.games_played > 0:
            win_rate = round(self.wins / self.games_played, 4)
        return {
            "player_id":    self.player_id,
            "playerId":     self.player_id,
            "id":           self.player_id,
            "username":     self.username,
            "playerName":   self.username,
            "displayName":  self.username,
            "name":         self.username,
            "created_at":   self.created_at,
            "games_played": self.games_played,
            "games":        self.games_played,
            "totalGames":   self.games_played,
            "wins":         self.wins,
            "totalWins":    self.wins,
            "losses":       self.losses,
            "totalLosses":  self.losses,
            "total_shots":  self.total_shots,
            "shots":        self.total_shots,
            "totalShots":   self.total_shots,
            "total_hits":   self.total_hits,
            "hits":         self.total_hits,
            "totalHits":    self.total_hits,
            "accuracy":     accuracy,
            "win_rate":     win_rate,
        }


class Game(db.Model):
    __tablename__ = "games"

    id                  = db.Column(db.Integer, primary_key=True)
    grid_size           = db.Column(db.Integer, nullable=False, default=8)
    max_players         = db.Column(db.Integer, nullable=False, default=2)
    status              = db.Column(db.String(20), nullable=False, default="waiting_setup")
    current_turn_index  = db.Column(db.Integer, nullable=False, default=0)
    winner_id           = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=True)
    created_at          = db.Column(db.String(30), nullable=False, default=_now)

    game_players = db.relationship(
        "GamePlayer", back_populates="game", lazy=True,
        order_by="GamePlayer.turn_order",
    )
    ships    = db.relationship("Ship", back_populates="game", lazy=True)
    moves    = db.relationship("Move", back_populates="game", lazy=True, order_by="Move.id")
    messages = db.relationship("ChatMessage", back_populates="game", lazy=True, order_by="ChatMessage.id")

    def _current_turn_player_id(self):
        if self.status not in ("active", "playing"):
            return None
        active = [gp for gp in self.game_players if not gp.is_eliminated]
        if not active:
            return None
        return active[self.current_turn_index % len(active)].player_id

    def to_dict(self):
        total_moves  = len(self.moves)
        player_ids   = [gp.player_id for gp in self.game_players]
        active_count = sum(1 for gp in self.game_players if not gp.is_eliminated)

        players_detail = []
        for gp in self.game_players:
            remaining = sum(1 for s in self.ships
                            if s.player_id == gp.player_id and not s.is_sunk)
            players_detail.append({
                "player_id":       gp.player_id,
                "ships_remaining": remaining,
            })

        status = self.status
        return {
            "game_id":                self.id,
            "id":                     self.id,
            "gameId":                 self.id,
            "grid_size":              self.grid_size,
            "gridSize":               self.grid_size,
            "status":                 status,
            "waiting":                status in ("waiting_setup",),
            "waiting_setup":          status in ("waiting_setup",),
            "playing":                status in ("active",),
            "active":                 status in ("active",),
            "players":                players_detail,
            "current_turn_player_id": self._current_turn_player_id(),
            "total_moves":            total_moves,
            "totalMoves":             total_moves,
            "max_players":            self.max_players,
            "maxPlayers":             self.max_players,
            "current_turn_index":     self.current_turn_index,
            "active_players":         active_count,
            "player_ids":             player_ids,
            "playerIds":              player_ids,
            "winner_id":              self.winner_id,
            "winnerId":               self.winner_id,
            "created_at":             self.created_at,
            "createdAt":              self.created_at,
        }


class GamePlayer(db.Model):
    __tablename__ = "game_players"

    game_id       = db.Column(db.Integer, db.ForeignKey("games.id"), primary_key=True)
    player_id     = db.Column(db.Integer, db.ForeignKey("players.player_id"), primary_key=True)
    turn_order    = db.Column(db.Integer, nullable=False)
    is_eliminated = db.Column(db.Boolean, nullable=False, default=False)
    ships_placed  = db.Column(db.Boolean, nullable=False, default=False)

    game   = db.relationship("Game", back_populates="game_players")
    player = db.relationship("Player", back_populates="game_players")


class Ship(db.Model):
    __tablename__ = "ships"

    id          = db.Column(db.Integer, primary_key=True)
    game_id     = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id   = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=False)
    start_row   = db.Column(db.Integer, nullable=False, default=0)
    start_col   = db.Column(db.Integer, nullable=False, default=0)
    length      = db.Column(db.Integer, nullable=False, default=1)
    orientation = db.Column(db.String(1), nullable=False, default="H")
    ship_type   = db.Column(db.String(20), nullable=False, default="submarine")
    hit_mask    = db.Column(db.Integer, nullable=False, default=0)
    is_sunk     = db.Column(db.Boolean, nullable=False, default=False)
    row         = db.Column(db.Integer, nullable=False, default=0)
    col         = db.Column(db.Integer, nullable=False, default=0)

    game = db.relationship("Game", back_populates="ships")

    def cells(self):
        result = []
        for i in range(self.length):
            if self.orientation == "H":
                result.append((self.start_row, self.start_col + i))
            else:
                result.append((self.start_row + i, self.start_col))
        return result

    def hit_cell(self, row, col):
        for i, (r, c) in enumerate(self.cells()):
            if r == row and c == col:
                self.hit_mask = self.hit_mask | (1 << i)
                if self.hit_mask == (2 ** self.length - 1):
                    self.is_sunk = True
                return True
        return False

    def occupies(self, row, col):
        return (row, col) in self.cells()

    def to_dict(self):
        return {
            "id":          self.id,
            "player_id":   self.player_id,
            "ship_type":   self.ship_type,
            "length":      self.length,
            "orientation": self.orientation,
            "start_row":   self.start_row,
            "start_col":   self.start_col,
            "cells":       self.cells(),
            "is_sunk":     self.is_sunk,
        }


class Move(db.Model):
    __tablename__ = "moves"

    id        = db.Column(db.Integer, primary_key=True)
    game_id   = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=False)
    row       = db.Column(db.Integer, nullable=False)
    col       = db.Column(db.Integer, nullable=False)
    result    = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.String(30), nullable=False, default=_now)

    game = db.relationship("Game", back_populates="moves")

    def to_dict(self):
        return {
            "move_id":     self.id,
            "move_number": self.id,
            "game_id":     self.game_id,
            "player_id":   self.player_id,
            "row":         self.row,
            "col":         self.col,
            "result":      self.result,
            "timestamp":   self.timestamp,
        }


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id        = db.Column(db.Integer, primary_key=True)
    game_id   = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=False)
    message   = db.Column(db.String(300), nullable=False)
    timestamp = db.Column(db.String(30), nullable=False, default=_now)

    game = db.relationship("Game", back_populates="messages")

    def to_dict(self):
        player = db.session.get(Player, self.player_id)
        return {
            "id":        self.id,
            "game_id":   self.game_id,
            "player_id": self.player_id,
            "username":  player.username if player else f"Player {self.player_id}",
            "message":   self.message,
            "timestamp": self.timestamp,
        }


class RematchRequest(db.Model):
    __tablename__ = "rematch_requests"

    id              = db.Column(db.Integer, primary_key=True)
    original_game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    requester_id    = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=False)
    opponent_id     = db.Column(db.Integer, db.ForeignKey("players.player_id"), nullable=False)
    # status: pending, accepted, declined
    status          = db.Column(db.String(20), nullable=False, default="pending")
    new_game_id     = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=True)
    created_at      = db.Column(db.String(30), nullable=False, default=_now)

    def to_dict(self):
        return {
            "id":               self.id,
            "original_game_id": self.original_game_id,
            "requester_id":     self.requester_id,
            "opponent_id":      self.opponent_id,
            "status":           self.status,
            "new_game_id":      self.new_game_id,
            "created_at":       self.created_at,
        }