from datetime import datetime, timezone

from models import BoardCell, GamePlayer, Move, Player, Ship, db


def get_starting_positions(grid_size, num_players):
    """Return a list of (row, col) starting positions for N players.

    Strategy:
    - 2 players: opposite corners
    - 3 players: three corners
    - 4 players: all four corners
    - 5+ players: corners first, then evenly spaced along edges
    """
    n = grid_size - 1

    corners = [(0, 0), (n, n), (0, n), (n, 0)]

    if num_players <= 4:
        return corners[:num_players]

    positions = list(corners)
    edge_positions = []

    for c in range(1, n):
        edge_positions.append((0, c))
    for r in range(1, n):
        edge_positions.append((r, n))
    for c in range(n - 1, 0, -1):
        edge_positions.append((n, c))
    for r in range(n - 1, 0, -1):
        edge_positions.append((r, 0))

    needed = num_players - 4
    if needed > 0 and len(edge_positions) > 0:
        step = len(edge_positions) / needed
        for i in range(needed):
            idx = int(i * step)
            positions.append(edge_positions[idx])

    return positions[:num_players]


def create_board(game):
    """Create all board cells for a game (all empty)."""
    for r in range(game.grid_size):
        for c in range(game.grid_size):
            cell = BoardCell(game_id=game.id, row=r, col=c, owner_player_id=None)
            db.session.add(cell)


def assign_starting_cells(game, game_players):
    """Assign one starting cell to each player. Returns list of (player_id, row, col)."""
    positions = get_starting_positions(game.grid_size, len(game_players))

    result = []
    for gp, (row, col) in zip(game_players, positions):
        # Query or create the cell at this position
        cell = BoardCell.query.filter_by(
            game_id=game.id, row=row, col=col
        ).first()
        
        if not cell:
            # This shouldn't happen if create_board was called, but handle it
            cell = BoardCell(game_id=game.id, row=row, col=col)
            db.session.add(cell)
        
        # Assign ownership to this player
        cell.owner_player_id = gp.playerId
        result.append((gp.playerId, row, col))

    return result


def validate_move(game, player_id, source_row, source_col, target_row, target_col):
    """Validate a territorial control move.
    
    Rules:
    1. Game must be active.
    2. It must be this player's turn.
    3. Source cell must be owned by this player.
    4. Target must be adjacent (up/down/left/right only).
    5. Target must be within grid boundaries.
    6. Target must NOT already be owned by this player.
    """
    # Rule 1: Game must be active
    if game.status != "active":
        return False, "Game is not active"

    # Rule 2: Must be this player's turn
    if game.current_turn_player_id != player_id:
        return False, "It is not your turn"

    # Rule 5: Target must be within bounds
    if not (0 <= target_row < game.grid_size and 0 <= target_col < game.grid_size):
        return False, "Target cell is out of bounds"

    # Rule 5 also for source
    if not (0 <= source_row < game.grid_size and 0 <= source_col < game.grid_size):
        return False, "Source cell is out of bounds"

    # Rule 4: Must be adjacent (Manhattan distance = 1, no diagonals)
    row_diff = abs(target_row - source_row)
    col_diff = abs(target_col - source_col)
    if not (row_diff + col_diff == 1):
        return False, "Target cell is not adjacent to source cell"

    # Rule 3: Source must be owned by player
    source_cell = BoardCell.query.filter_by(
        game_id=game.id, row=source_row, col=source_col
    ).first()
    if not source_cell or source_cell.owner_player_id != player_id:
        return False, "Source cell is not owned by you"

    # Rule 6: Target must not be owned by this player
    target_cell = BoardCell.query.filter_by(
        game_id=game.id, row=target_row, col=target_col
    ).first()
    if target_cell and target_cell.owner_player_id == player_id:
        return False, "Target cell is already owned by you"

    return True, None


def execute_move(game, player_id, source_row, source_col, target_row, target_col):
    """Execute a validated territorial control move."""
    # Get target cell and record who owned it before
    target_cell = BoardCell.query.filter_by(
        game_id=game.id, row=target_row, col=target_col
    ).first()
    captured_from = target_cell.owner_player_id if target_cell else None

    # Transfer ownership
    if target_cell:
        target_cell.owner_player_id = player_id
    else:
        target_cell = BoardCell(
            game_id=game.id,
            row=target_row,
            col=target_col,
            owner_player_id=player_id,
        )
        db.session.add(target_cell)

    # Log the move with timestamp
    move = Move(
        game_id=game.id,
        player_id=player_id,
        source_row=source_row,
        source_col=source_col,
        target_row=target_row,
        target_col=target_col,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    db.session.add(move)

    # Update totalMoves on the player
    player = Player.query.get(player_id)
    if player:
        player.totalMoves += 1

    # Check for eliminations
    eliminated_players = check_eliminations(game, player_id)

    # Check for winner (this also updates stats on game completion)
    game_status = check_winner(game)

    # Advance turn (only if game is still active)
    next_turn_player_id = None
    if game.status == "active":
        next_turn_player_id = advance_turn(game)

    db.session.flush()

    return {
        "move_id": move.id,
        "source": [source_row, source_col],
        "target": [target_row, target_col],
        "captured_from": captured_from,
        "timestamp": move.timestamp,
        "eliminated_players": eliminated_players,
        "next_turn_player_id": next_turn_player_id,
        "game_status": game.status,
    }


def check_eliminations(game, current_player_id):
    """Check if any opponents have 0 cells remaining."""
    eliminated = []
    game_players = GamePlayer.query.filter_by(gameId=game.id).all()

    for gp in game_players:
        if gp.playerId == current_player_id or gp.is_eliminated:
            continue

        cell_count = BoardCell.query.filter_by(
            game_id=game.id, owner_player_id=gp.playerId
        ).count()

        if cell_count == 0:
            gp.is_eliminated = True
            eliminated.append(gp.playerId)

    return eliminated


def check_winner(game):
    """Check if only one player remains. If so, end the game and update stats."""
    active_players = GamePlayer.query.filter_by(
        gameId=game.id, is_eliminated=False
    ).all()

    if len(active_players) == 1:
        winner_gp = active_players[0]
        game.status = "finished"
        game.winner_id = winner_gp.playerId

        # Update stats for ALL players in this game (on game completion)
        all_game_players = GamePlayer.query.filter_by(gameId=game.id).all()
        for gp in all_game_players:
            player = Player.query.get(gp.playerId)
            if player:
                player.totalGames += 1
                if gp.playerId == winner_gp.playerId:
                    player.totalWins += 1
                else:
                    player.totalLosses += 1

        return "finished"

    return "active"


def advance_turn(game):
    """Advance to the next non-eliminated player."""
    active_players = (
        GamePlayer.query.filter_by(gameId=game.id, is_eliminated=False)
        .order_by(GamePlayer.turn_order)
        .all()
    )

    if not active_players:
        return None

    current_idx = None
    for i, gp in enumerate(active_players):
        if gp.playerId == game.current_turn_player_id:
            current_idx = i
            break

    if current_idx is not None:
        next_idx = (current_idx + 1) % len(active_players)
    else:
        next_idx = 0

    next_player_id = active_players[next_idx].playerId
    game.current_turn_player_id = next_player_id

    return next_player_id


def get_board_as_2d_array(game):
    """Return the board as a 2D array of playerIds (None for empty cells)."""
    board = [[None for _ in range(game.grid_size)] for _ in range(game.grid_size)]

    cells = BoardCell.query.filter_by(game_id=game.id).all()
    for cell in cells:
        board[cell.row][cell.col] = cell.owner_player_id

    return board


def validate_ship_placement(game, player_id, ships):
    """Validate ship placement for a player.
    
    Rules:
    - Exactly 3 ships
    - Each ship at valid coordinates
    - No overlapping ships for this player
    - Within grid bounds
    """
    if not isinstance(ships, list):
        return False, "ships must be a list"

    if len(ships) != 3:
        return False, f"Must place exactly 3 ships, got {len(ships)}"

    # Check if player already placed ships
    existing_ships = Ship.query.filter_by(
        game_id=game.id, player_id=player_id
    ).all()
    if existing_ships:
        return False, "Ships already placed for this player"

    positions = set()
    for i, ship in enumerate(ships):
        row = ship.get("row")
        col = ship.get("col")

        if row is None or col is None:
            return False, f"Ship {i} missing row or col"

        if not isinstance(row, int) or not isinstance(col, int):
            return False, f"Ship {i} row and col must be integers"

        if not (0 <= row < game.grid_size and 0 <= col < game.grid_size):
            return False, f"Ship {i} at ({row},{col}) is out of bounds"

        if (row, col) in positions:
            return False, f"Duplicate ship position ({row},{col})"

        positions.add((row, col))

    return True, None