/* ============================================================
   BATTLESHIP — app.js
   ============================================================ */

const API_BASE         = "https://finalproject-battleship.onrender.com/api";
const POLL_INTERVAL_MS = 2000;

// Ship definitions — must match backend SHIP_TYPES
const SHIP_DEFS = [
  { type: "submarine",  length: 1, label: "Submarine",  blockClass: "sub"  },
  { type: "destroyer",  length: 2, label: "Destroyer",  blockClass: "dest" },
  { type: "cruiser",    length: 3, label: "Cruiser",    blockClass: "crui" },
  { type: "battleship", length: 4, label: "Battleship", blockClass: "batt" },
];

// ============================================================
// STATE
// ============================================================
const state = {
  player:            null,
  view:              "login",
  games:             [],
  currentGame:       null,
  moves:             [],
  myShips:           [],          // confirmed placed ships [{type,startRow,startCol,orientation,length}]
  placementShips:    [],          // ships placed so far this session (same format)
  selectedShipType:  "submarine", // which ship is being placed
  orientation:       "H",        // current orientation H or V
  selectedOpponent:  null,
  pollHandle:        null,
  gameStartShots:    0,
  gameStartHits:     0,
  hitStreak:         0,
  usernameCache:     {},
  pastGamesOpen:     false,
  theme:             "dark",
};

// ============================================================
// THEME
// ============================================================
function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme === "light" ? "light" : "");
  localStorage.setItem("battleship_theme", theme);
  // Update all toggle buttons
  document.querySelectorAll(".btn-theme").forEach(btn => {
    btn.textContent = theme === "light" ? "🌙" : "☀️";
    btn.title       = theme === "light" ? "Switch to dark mode" : "Switch to light mode";
  });
}

function toggleTheme() {
  applyTheme(state.theme === "dark" ? "light" : "dark");
}

function loadTheme() {
  const saved = localStorage.getItem("battleship_theme") || "dark";
  applyTheme(saved);
}

// ============================================================
// API
// ============================================================
const api = {
  async request(method, path, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body) opts.body = JSON.stringify(body);
    let res, data;
    try {
      res = await fetch(`${API_BASE}${path}`, opts);
    } catch (e) {
      throw new Error("Cannot reach server. Check your connection.");
    }
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) {
      const msg = data.message || data.error || `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.data   = data;
      throw err;
    }
    return data;
  },
  createPlayer:   (username)                   => api.request("POST",   "/players",               { username }),
  getPlayer:      (id)                         => api.request("GET",    `/players/${id}`),
  listGames:      ()                           => api.request("GET",    "/games"),
  createGame:     (gridSize, maxPlayers, cid)  => api.request("POST",   "/games",                 { grid_size: gridSize, max_players: maxPlayers, creator_id: cid }),
  getGame:        (id)                         => api.request("GET",    `/games/${id}`),
  joinGame:       (gameId, playerId)           => api.request("POST",   `/games/${gameId}/join`,  { player_id: playerId }),
  startGame:      (gameId)                     => api.request("POST",   `/games/${gameId}/start`),
  placeShips:     (gameId, playerId, ships)    => api.request("POST",   `/games/${gameId}/place`, { player_id: playerId, ships }),
  fire:           (gameId, playerId, row, col) => api.request("POST",   `/games/${gameId}/fire`,  { player_id: playerId, row, col }),
  getMoves:       (gameId)                     => api.request("GET",    `/games/${gameId}/moves`),
  getLeaderboard: ()                           => api.request("GET",    "/leaderboard"),
  deleteGame:     (gameId, playerId)           => api.request("DELETE", `/games/${gameId}?player_id=${playerId}`),
};

// ============================================================
// USERNAME CACHE
// ============================================================
async function resolveUsername(playerId) {
  if (!playerId) return `Player ${playerId}`;
  if (state.usernameCache[playerId]) return state.usernameCache[playerId];
  try {
    const p = await api.getPlayer(playerId);
    state.usernameCache[playerId] = p.username || `Player ${playerId}`;
  } catch (_) {
    state.usernameCache[playerId] = `Player ${playerId}`;
  }
  return state.usernameCache[playerId];
}
function getUsername(playerId) {
  return state.usernameCache[playerId] || `Player ${playerId}`;
}

// ============================================================
// TOASTS
// ============================================================
function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const el        = document.createElement("div");
  el.className    = `toast ${type}`;
  el.textContent  = message;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add("fading");
    setTimeout(() => el.remove(), 250);
  }, 3500);
}

// ============================================================
// VIEW MANAGEMENT
// ============================================================
function showView(name) {
  state.view = name;
  document.getElementById("view-login").classList.toggle("hidden", name !== "login");
  document.getElementById("view-lobby").classList.toggle("hidden", name !== "lobby");
  document.getElementById("view-game" ).classList.toggle("hidden", name !== "game");
  document.getElementById("topbar").classList.toggle("hidden", name === "login");
  stopPolling();
  if (name === "lobby") startPolling(refreshLobby);
  if (name === "game")  startPolling(refreshGame);
}

function startPolling(fn) { fn(); state.pollHandle = setInterval(fn, POLL_INTERVAL_MS); }
function stopPolling()    { if (state.pollHandle) clearInterval(state.pollHandle); state.pollHandle = null; }

// ============================================================
// LOGIN
// ============================================================
async function handleLogin() {
  const input    = document.getElementById("username-input");
  const username = input.value.trim();
  if (!username) { toast("Enter a callsign first.", "error"); return; }
  if (!/^[A-Za-z0-9_]+$/.test(username)) { toast("Letters, numbers, and underscores only.", "error"); return; }

  const btn       = document.getElementById("btn-login");
  btn.disabled    = true;
  btn.textContent = "Signing in...";
  try {
    const player = await api.createPlayer(username);
    state.player  = player;
    state.usernameCache[player.player_id] = player.username;
    localStorage.setItem("battleship_player", JSON.stringify(player));
    document.getElementById("user-label").textContent = `⚓ ${player.username}`;
    showView("lobby");
    toast(`Welcome, ${player.username}.`, "success");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled    = false;
    btn.textContent = "Continue";
  }
}

function handleLogout() {
  localStorage.removeItem("battleship_player");
  state.player      = null;
  state.currentGame = null;
  document.getElementById("username-input").value = "";
  showView("login");
}

function tryAutoLogin() {
  const saved = localStorage.getItem("battleship_player");
  if (!saved) return false;
  try {
    state.player = JSON.parse(saved);
    state.usernameCache[state.player.player_id] = state.player.username;
    document.getElementById("user-label").textContent = `⚓ ${state.player.username}`;
    showView("lobby");
    return true;
  } catch (e) {
    localStorage.removeItem("battleship_player");
    return false;
  }
}

// ============================================================
// LOBBY
// ============================================================
async function refreshLobby() {
  try {
    const [games, me] = await Promise.all([
      api.listGames(),
      api.getPlayer(state.player.player_id),
    ]);
    state.games  = games;
    state.player = { ...state.player, ...me };

    const ids = new Set();
    games.forEach(g => (g.player_ids || []).forEach(id => ids.add(id)));
    await Promise.all([...ids].map(id => resolveUsername(id)));

    renderGamesList();
    renderMyStats();
    renderPastGames();
  } catch (e) {
    if (!state.games.length) toast(e.message, "error");
  }
}

function renderGamesList() {
  const container   = document.getElementById("games-list");
  const activeGames = state.games.filter(g => g.status !== "finished");

  if (!activeGames.length) {
    container.innerHTML = `<p class="empty">No open games. Create one to get started.</p>`;
    return;
  }

  const myId = state.player.player_id;
  container.innerHTML = activeGames.map(g => {
    const inGame      = (g.player_ids || []).includes(myId);
    const playerCount = (g.player_ids || []).length;
    const canJoin     = !inGame && (g.status === "waiting_setup" || g.status === "placing") && playerCount < g.max_players;
    const btnLabel    = inGame ? "Resume" : (canJoin ? "Join" : "View");
    const btnDisabled = !inGame && !canJoin;
    const otherNames  = (g.player_ids || []).filter(id => id !== myId).map(id => getUsername(id)).join(", ");
    const playerMeta  = inGame && otherNames ? `vs ${otherNames}` : `${playerCount}/${g.max_players} players`;

    return `
      <div class="game-card ${inGame ? "mine" : ""}">
        <div class="game-card-info">
          <span class="game-card-id">Game #${g.id}</span>
          <span class="game-card-meta">
            ${g.grid_size}×${g.grid_size} • ${playerMeta} •
            <span class="status-pill status-${g.status}">${g.status.replace("_", " ")}</span>
          </span>
        </div>
        <div class="game-card-actions">
          <button class="${inGame ? "primary" : "ghost"} small"
                  ${btnDisabled ? "disabled" : ""}
                  data-game-id="${g.id}"
                  data-action="${inGame ? "resume" : (canJoin ? "join" : "view")}">
            ${btnLabel}
          </button>
          ${inGame ? `<button class="btn-delete" data-delete-id="${g.id}">Delete</button>` : ""}
        </div>
      </div>
    `;
  }).join("");

  container.querySelectorAll("button[data-game-id]").forEach(btn => {
    btn.addEventListener("click", () => {
      const gameId = parseInt(btn.dataset.gameId, 10);
      if (btn.dataset.action === "join") joinGame(gameId);
      else enterGame(gameId);
    });
  });
  container.querySelectorAll("button[data-delete-id]").forEach(btn => {
    btn.addEventListener("click", () => handleDeleteGame(parseInt(btn.dataset.deleteId, 10)));
  });
}

async function handleDeleteGame(gameId) {
  if (!confirm(`Delete Game #${gameId}? This cannot be undone.`)) return;
  try {
    await api.deleteGame(gameId, state.player.player_id);
    toast(`Game #${gameId} deleted.`, "success");
    refreshLobby();
  } catch (e) {
    toast(e.message, "error");
  }
}

function renderMyStats() {
  const p        = state.player;
  const accuracy = p.total_shots ? Math.round((p.total_hits / p.total_shots) * 100) : 0;
  document.getElementById("my-stats").innerHTML = `
    <div class="stat-item"><span class="stat-val">${p.wins || 0}</span><span class="stat-label">Wins</span></div>
    <div class="stat-item"><span class="stat-val">${p.losses || 0}</span><span class="stat-label">Losses</span></div>
    <div class="stat-item"><span class="stat-val">${p.total_shots || 0}</span><span class="stat-label">Shots</span></div>
    <div class="stat-item"><span class="stat-val">${accuracy}%</span><span class="stat-label">Accuracy</span></div>
  `;
}

function renderPastGames() {
  const section = document.getElementById("past-games-section");
  if (!section) return;
  const myId    = state.player.player_id;
  const finished = state.games.filter(g => g.status === "finished" && (g.player_ids || []).includes(myId));

  if (!finished.length) {
    section.innerHTML = `
      <div class="past-games-section">
        <div class="past-games-toggle"><h3>Past Games</h3><span class="toggle-arrow">▼</span></div>
        <p class="empty" style="padding:12px 0 0;font-size:12px">No finished games yet.</p>
      </div>`;
    return;
  }

  const rows = finished.map(g => {
    const won      = g.winner_id === myId;
    const cls      = won ? "win" : "loss";
    const oppNames = (g.player_ids || []).filter(id => id !== myId).map(id => getUsername(id)).join(", ") || "Unknown";
    return `
      <div class="past-game-row ${cls}">
        <div class="past-game-info">
          <span class="past-game-id">Game #${g.id}</span>
          <span class="past-game-vs">vs ${oppNames}</span>
        </div>
        <span class="past-game-result ${cls}">${won ? "WIN" : "LOSS"}</span>
      </div>`;
  }).join("");

  const isOpen = state.pastGamesOpen;
  section.innerHTML = `
    <div class="past-games-section">
      <div class="past-games-toggle ${isOpen ? "open" : ""}" id="past-games-toggle">
        <h3>Past Games (${finished.length})</h3>
        <span class="toggle-arrow">▼</span>
      </div>
      ${isOpen ? `<div class="past-games-list">${rows}</div>` : ""}
    </div>`;

  document.getElementById("past-games-toggle").addEventListener("click", () => {
    state.pastGamesOpen = !state.pastGamesOpen;
    renderPastGames();
  });
}

async function handleCreateGame() {
  const gridSize   = parseInt(document.getElementById("grid-size").value, 10);
  const maxPlayers = parseInt(document.getElementById("max-players").value, 10);
  if (gridSize < 5 || gridSize > 15)     { toast("Grid size must be 5 to 15.", "error"); return; }
  if (maxPlayers < 2 || maxPlayers > 10) { toast("Max players must be 2 to 10.", "error"); return; }
  try {
    const game = await api.createGame(gridSize, maxPlayers, state.player.player_id);
    toast(`Game #${game.id} created.`, "success");
    enterGame(game.id);
  } catch (e) {
    toast(e.message, "error");
  }
}

async function joinGame(gameId) {
  try {
    await api.joinGame(gameId, state.player.player_id);
    toast(`Joined game #${gameId}.`, "success");
    enterGame(gameId);
  } catch (e) {
    toast(e.message, "error");
  }
}

// ============================================================
// GAME ENTRY
// ============================================================
async function enterGame(gameId) {
  state.gameStartShots  = state.player.total_shots || 0;
  state.gameStartHits   = state.player.total_hits  || 0;
  state.hitStreak       = 0;
  state.currentGame     = { id: gameId };
  state.myShips         = [];
  state.placementShips  = [];
  state.selectedShipType = "submarine";
  state.orientation     = "H";
  state.selectedOpponent = null;
  document.getElementById("game-id-label").textContent = `#${gameId}`;
  showView("game");
}

// ============================================================
// GAME POLLING
// ============================================================
async function refreshGame() {
  if (!state.currentGame) return;
  try {
    const [game, moves] = await Promise.all([
      api.getGame(state.currentGame.id),
      api.getMoves(state.currentGame.id),
    ]);
    const wasFinished = state.currentGame.status === "finished";
    state.currentGame = game;
    state.moves       = moves;

    await Promise.all((game.player_ids || []).map(id => resolveUsername(id)));

    renderGameView();

    if (game.status === "finished" && !wasFinished) {
      try {
        const freshMe = await api.getPlayer(state.player.player_id);
        state.player  = { ...state.player, ...freshMe };
      } catch (_) {}
      showPostGameModal(game);
    }
  } catch (e) {
    toast(e.message, "error");
  }
}

// ============================================================
// GAME VIEW
// ============================================================
function renderGameView() {
  const g = state.currentGame;
  if (!g || !g.status) return;

  const statusEl       = document.getElementById("game-status-label");
  statusEl.className   = `status-pill status-${g.status}`;
  statusEl.textContent = g.status.replace("_", " ");

  const turnEl = document.getElementById("turn-label");
  turnEl.classList.remove("my-turn");
  if (g.status === "active") {
    if (g.current_turn_player_id === state.player.player_id) {
      turnEl.textContent = "🎯 Your turn";
      turnEl.classList.add("my-turn");
    } else {
      turnEl.textContent = `Waiting for ${getUsername(g.current_turn_player_id)}...`;
    }
  } else if (g.status === "finished") {
    turnEl.textContent = "Game over";
  } else if (g.status === "placing") {
    turnEl.textContent = "Place your ships";
  } else {
    turnEl.textContent = `Waiting for players (${(g.player_ids||[]).length}/${g.max_players})`;
  }

  renderPhaseBanner(g);
  renderMyBoard(g);
  renderOpponentBoard(g);
  renderMoveHistory();
  renderPlayersList(g);
  renderStreakBanner();
}

// ============================================================
// PHASE BANNER
// ============================================================
function renderPhaseBanner(g) {
  const banner = document.getElementById("phase-banner");
  const myId   = state.player.player_id;
  const inGame = (g.player_ids || []).includes(myId);

  if (!inGame) { banner.classList.add("hidden"); return; }

  if (g.status === "waiting_setup") {
    const need = g.max_players - (g.player_ids || []).length;
    if ((g.player_ids || []).length >= 2) {
      banner.innerHTML = `Waiting for more players (or click below to start).
        <button id="banner-start" class="primary small" style="margin-left:12px">Start Game</button>`;
      banner.classList.remove("hidden");
      const startBtn = document.getElementById("banner-start");
      if (startBtn) startBtn.onclick = handleStartGame;
    } else {
      banner.textContent = `Waiting for ${need} more player${need !== 1 ? "s" : ""} to join...`;
      banner.classList.remove("hidden");
    }
  } else if (g.status === "placing") {
    if (state.myShips.length === 4) {
      banner.textContent = "All ships placed. Waiting for other players...";
    } else {
      const remaining = 4 - state.placementShips.length;
      if (state.placementShips.length === 4) {
        banner.innerHTML = `All 4 ships placed!
          <button id="banner-confirm" class="primary small" style="margin-left:12px">Confirm Placement</button>
          <button id="banner-clear" class="ghost small" style="margin-left:6px">Clear All</button>`;
        const cBtn = document.getElementById("banner-confirm");
        const xBtn = document.getElementById("banner-clear");
        if (cBtn) cBtn.onclick = handleConfirmPlacement;
        if (xBtn) xBtn.onclick = clearPlacements;
      } else {
        banner.textContent = `Place ${remaining} more ship${remaining !== 1 ? "s" : ""}. Click on your board.`;
      }
    }
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

async function handleStartGame() {
  try {
    await api.startGame(state.currentGame.id);
    toast("Game started. Place your ships.", "success");
    refreshGame();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function handleConfirmPlacement() {
  const ships = state.placementShips.map(s => ({
    ship_type:   s.type,
    start_row:   s.startRow,
    start_col:   s.startCol,
    orientation: s.orientation,
  }));
  try {
    await api.placeShips(state.currentGame.id, state.player.player_id, ships);
    state.myShips        = [...state.placementShips];
    state.placementShips = [];
    toast("Ships locked in. Battle begins!", "success");
    refreshGame();
  } catch (e) {
    toast(e.message, "error");
  }
}

function clearPlacements() {
  state.placementShips = [];
  renderGameView();
}

// ============================================================
// SHIP PLACEMENT LOGIC
// ============================================================

// Returns all (row,col) cells a ship would occupy
function getShipCells(type, startRow, startCol, orientation) {
  const def    = SHIP_DEFS.find(d => d.type === type);
  const length = def ? def.length : 1;
  const cells  = [];
  for (let i = 0; i < length; i++) {
    if (orientation === "H") cells.push([startRow, startCol + i]);
    else                     cells.push([startRow + i, startCol]);
  }
  return cells;
}

// Returns true if cells fit within grid and don't overlap existing placements
function isValidPlacement(type, startRow, startCol, orientation, gridSize, existingShips) {
  const cells = getShipCells(type, startRow, startCol, orientation);
  for (const [r, c] of cells) {
    if (r < 0 || r >= gridSize || c < 0 || c >= gridSize) return false;
  }
  const occupied = new Set();
  existingShips.forEach(s => {
    getShipCells(s.type, s.startRow, s.startCol, s.orientation).forEach(([r, c]) => {
      occupied.add(`${r},${c}`);
    });
  });
  for (const [r, c] of cells) {
    if (occupied.has(`${r},${c}`)) return false;
  }
  return true;
}

// Which ship type should be placed next
function nextShipToBePlaced() {
  const placedTypes = new Set(state.placementShips.map(s => s.type));
  return SHIP_DEFS.find(d => !placedTypes.has(d.type))?.type || null;
}

// ============================================================
// MY BOARD — placement + display
// ============================================================
function renderMyBoard(g) {
  const boardEl  = document.getElementById("my-board");
  const size     = g.grid_size;
  const cells    = makeBoardGrid(boardEl, size);
  const myId     = state.player.player_id;
  const inGame   = (g.player_ids || []).includes(myId);
  const placing  = g.status === "placing" && state.myShips.length === 0;

  // Paint confirmed ships
  state.myShips.forEach(s => paintShipOnBoard(cells, s));

  // Paint pending placements
  state.placementShips.forEach(s => paintShipOnBoard(cells, s));

  // Paint opponent shots against me
  state.moves.filter(m => m.player_id !== myId).forEach(m => {
    if (!cells[m.row]?.[m.col]) return;
    const cell = cells[m.row][m.col];
    cell.classList.remove("ship-submarine","ship-destroyer","ship-cruiser","ship-battleship",
                          "ship-head-h","ship-tail-h","ship-head-v","ship-tail-v","ship-mid","ship-single");
    cell.classList.add(m.result === "hit" ? "hit" : "miss");
  });

  // Render ship selector during placement phase
  renderShipSelector(g);

  // Make cells clickable for placement
  if (inGame && placing && state.myShips.length === 0) {
    cells.forEach(row => row.forEach(cell => {
      if (cell.classList.contains("hit") || cell.classList.contains("miss")) return;
      cell.classList.add("placeable");
      cell.addEventListener("mouseenter", () => showPlacementPreview(cells, parseInt(cell.dataset.row), parseInt(cell.dataset.col), size));
      cell.addEventListener("mouseleave", () => clearPreview(cells));
      cell.addEventListener("click", () => handlePlacementClick(parseInt(cell.dataset.row), parseInt(cell.dataset.col), size, cells));
    }));
  }
}

function paintShipOnBoard(cells, ship) {
  const shipCells = getShipCells(ship.type, ship.startRow, ship.startCol, ship.orientation);
  const len       = shipCells.length;
  shipCells.forEach(([r, c], i) => {
    if (!cells[r]?.[c]) return;
    const cell = cells[r][c];
    cell.classList.add(`ship-${ship.type}`);
    if (len === 1) {
      cell.classList.add("ship-single");
    } else if (i === 0) {
      cell.classList.add(ship.orientation === "H" ? "ship-head-h" : "ship-head-v");
    } else if (i === len - 1) {
      cell.classList.add(ship.orientation === "H" ? "ship-tail-h" : "ship-tail-v");
    } else {
      cell.classList.add("ship-mid");
    }
  });
}

function showPlacementPreview(cells, row, col, gridSize) {
  clearPreview(cells);
  const type    = state.selectedShipType || nextShipToBePlaced();
  if (!type) return;
  const placed  = state.placementShips;
  const valid   = isValidPlacement(type, row, col, state.orientation, gridSize, placed);
  const shipCells = getShipCells(type, row, col, state.orientation);
  shipCells.forEach(([r, c]) => {
    if (!cells[r]?.[c]) return;
    cells[r][c].classList.add("placement-preview");
    cells[r][c].style.opacity = valid ? "0.8" : "0.4";
  });
}

function clearPreview(cells) {
  cells.forEach(row => row.forEach(cell => {
    cell.classList.remove("placement-preview");
    cell.style.opacity = "";
  }));
}

function handlePlacementClick(row, col, gridSize, cells) {
  const type = nextShipToBePlaced();
  if (!type) return;

  // Check if already placed all 4
  if (state.placementShips.length >= 4) return;

  if (!isValidPlacement(type, row, col, state.orientation, gridSize, state.placementShips)) {
    toast("Can't place ship there — out of bounds or overlapping.", "error");
    return;
  }

  state.placementShips.push({
    type,
    startRow:    row,
    startCol:    col,
    orientation: state.orientation,
    length:      SHIP_DEFS.find(d => d.type === type).length,
  });

  // Auto-advance to next ship type
  const next = nextShipToBePlaced();
  if (next) {
    state.selectedShipType = next;
    toast(`${type.charAt(0).toUpperCase() + type.slice(1)} placed! Now place your ${next}.`, "success");
  } else {
    toast("All ships placed! Confirm when ready.", "success");
  }

  clearPreview(cells);
  renderGameView();
}

// ============================================================
// SHIP SELECTOR UI
// ============================================================
function renderShipSelector(g) {
  // Remove any existing selector
  const existing = document.getElementById("ship-selector");
  if (existing) existing.remove();

  const myId   = state.player.player_id;
  const inGame = (g.player_ids || []).includes(myId);
  if (!inGame || g.status !== "placing" || state.myShips.length === 4) return;

  const placedTypes = new Set(state.placementShips.map(s => s.type));
  const boardWrap   = document.getElementById("my-board").parentElement;

  const selector = document.createElement("div");
  selector.id    = "ship-selector";
  selector.className = "ship-selector";
  selector.innerHTML = `
    <div class="ship-selector-title">Fleet</div>
    <div class="ship-tray">
      ${SHIP_DEFS.map(def => {
        const isPlaced   = placedTypes.has(def.type);
        const isSelected = state.selectedShipType === def.type && !isPlaced;
        const blocks     = Array.from({length: def.length}, () =>
          `<div class="ship-block ${def.blockClass}"></div>`).join("");
        return `
          <div class="ship-option ${isSelected ? "selected" : ""} ${isPlaced ? "placed" : ""}"
               data-type="${def.type}">
            <div class="ship-icon">${blocks}</div>
            <div class="ship-info">
              <div class="ship-name">${def.label}</div>
              <div class="ship-size">${def.length} cell${def.length > 1 ? "s" : ""}</div>
            </div>
            ${isPlaced
              ? `<span class="ship-placed-badge">✓ PLACED</span>`
              : `<button class="rotate-btn" data-type="${def.type}" title="Rotate">↺</button>
                 <span class="orientation-badge">${isSelected ? state.orientation : "H"}</span>`
            }
          </div>
        `;
      }).join("")}
    </div>
  `;

  boardWrap.insertBefore(selector, document.getElementById("my-board"));

  // Ship selection click
  selector.querySelectorAll(".ship-option:not(.placed)").forEach(el => {
    el.addEventListener("click", e => {
      if (e.target.closest(".rotate-btn")) return;
      state.selectedShipType = el.dataset.type;
      renderGameView();
    });
  });

  // Rotate click
  selector.querySelectorAll(".rotate-btn").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      state.orientation      = state.orientation === "H" ? "V" : "H";
      state.selectedShipType = btn.dataset.type;
      renderGameView();
      toast(`Rotated to ${state.orientation === "H" ? "Horizontal" : "Vertical"}`, "info");
    });
  });
}

// ============================================================
// OPPONENT BOARD
// ============================================================
function renderOpponentBoard(g) {
  const tabsEl    = document.getElementById("opp-tabs");
  const boardEl   = document.getElementById("opp-board");
  const myId      = state.player.player_id;
  const opponents = (g.players || []).filter(p => p.player_id !== myId);

  if (opponents.length === 0) {
    tabsEl.innerHTML  = "";
    boardEl.innerHTML = `<p class="empty" style="grid-column:1/-1">No opponents yet.</p>`;
    return;
  }

  if (!state.selectedOpponent || !opponents.find(p => p.player_id === state.selectedOpponent)) {
    state.selectedOpponent = opponents[0].player_id;
  }

  if (opponents.length > 1) {
    tabsEl.innerHTML = opponents.map(p => `
      <button class="opp-tab ${p.player_id === state.selectedOpponent ? "active" : ""}
                            ${p.ships_remaining === 0 ? "eliminated" : ""}"
              data-pid="${p.player_id}">
        ${getUsername(p.player_id)} (${p.ships_remaining} ships)
      </button>`).join("");
    tabsEl.querySelectorAll("button[data-pid]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.selectedOpponent = parseInt(btn.dataset.pid, 10);
        renderGameView();
      });
    });
  } else {
    tabsEl.innerHTML = "";
  }

  const oppName = getUsername(state.selectedOpponent);
  document.getElementById("opp-title").textContent =
    opponents.length > 1 ? `Targeting ${oppName}` : `${oppName}'s Board`;

  const cells = makeBoardGrid(boardEl, g.grid_size);

  state.moves.filter(m => m.player_id === myId).forEach(m => {
    if (!cells[m.row]?.[m.col]) return;
    cells[m.row][m.col].classList.add(m.result === "hit" ? "hit" : "miss");
  });

  const myTurn = g.status === "active" && g.current_turn_player_id === myId;
  if (myTurn) {
    cells.forEach(row => row.forEach(cell => {
      if (cell.classList.contains("hit") || cell.classList.contains("miss")) return;
      cell.classList.add("clickable");
      cell.addEventListener("click", () => handleFire(
        parseInt(cell.dataset.row, 10), parseInt(cell.dataset.col, 10)
      ));
    }));
  }
}

async function handleFire(row, col) {
  try {
    const result = await api.fire(state.currentGame.id, state.player.player_id, row, col);

    if (result.result === "hit") {
      state.hitStreak += 1;
      let msg = state.hitStreak >= 3
        ? `🔥 x${state.hitStreak} STREAK! ON FIRE!`
        : `🎯 HIT! Streak x${state.hitStreak}`;
      if (result.ship_sunk) {
        const typeName = result.ship_type
          ? result.ship_type.charAt(0).toUpperCase() + result.ship_type.slice(1)
          : "Ship";
        msg += ` — ${typeName} SUNK! 💀`;
      }
      toast(msg, "success");
    } else {
      if (state.hitStreak > 0) toast(`Streak broken at x${state.hitStreak}. Miss.`, "info");
      else toast("Splash. Miss.", "info");
      state.hitStreak = 0;
    }

    refreshGame();
  } catch (e) {
    toast(e.message, "error");
  }
}

// ============================================================
// BOARD GRID FACTORY
// ============================================================
function makeBoardGrid(boardEl, size) {
  boardEl.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
  boardEl.style.gridTemplateRows    = `repeat(${size}, 1fr)`;
  boardEl.innerHTML = "";
  const cells = [];
  for (let r = 0; r < size; r++) {
    cells[r] = [];
    for (let c = 0; c < size; c++) {
      const cell        = document.createElement("div");
      cell.className    = "cell";
      cell.dataset.row  = r;
      cell.dataset.col  = c;
      boardEl.appendChild(cell);
      cells[r][c] = cell;
    }
  }
  return cells;
}

// ============================================================
// MOVE HISTORY + PLAYERS
// ============================================================
function renderMoveHistory() {
  const el = document.getElementById("move-history");
  if (!state.moves.length) { el.innerHTML = `<p class="empty">No moves yet.</p>`; return; }
  el.innerHTML = state.moves.slice().reverse().map(m => {
    const isMe = m.player_id === state.player.player_id;
    return `
      <div class="move-row">
        <span class="move-num">#${m.move_number}</span>
        <span class="move-player">${isMe ? "You" : getUsername(m.player_id)}</span>
        <span class="move-coords">(${m.row},${m.col})</span>
        <span class="move-result ${m.result}">${m.result.toUpperCase()}</span>
      </div>`;
  }).join("");
}

function renderPlayersList(g) {
  const el = document.getElementById("players-list");
  el.innerHTML = (g.players || []).map(p => {
    const isMe       = p.player_id === state.player.player_id;
    const isCurrent  = g.current_turn_player_id === p.player_id;
    const eliminated = p.ships_remaining === 0;
    return `
      <div class="player-row ${isCurrent ? "current" : ""} ${eliminated ? "eliminated" : ""}">
        <span class="player-name">${isMe ? "You" : getUsername(p.player_id)}${isCurrent ? " 🎯" : ""}</span>
        <span class="player-ships">${p.ships_remaining} ships</span>
      </div>`;
  }).join("");
}

// ============================================================
// SNIPER STREAK BANNER
// ============================================================
function renderStreakBanner() {
  const banner = document.getElementById("streak-banner");
  if (!banner) return;
  const streak = state.hitStreak;
  if (streak === 0) {
    banner.className = "";
    banner.id        = "streak-banner";
    banner.innerHTML = `<span class="streak-label">Sniper Streak</span>`;
    return;
  }
  const isHot      = streak >= 3;
  banner.className = isHot ? "hot" : "active";
  banner.id        = "streak-banner";
  banner.innerHTML = `
    <span class="streak-count">${"🎯".repeat(Math.min(streak, 5))}</span>
    <span class="streak-label">x${streak} STREAK${isHot ? " 🔥" : ""}</span>
  `;
}

// ============================================================
// POST-GAME MODAL
// ============================================================
function showPostGameModal(g) {
  const modal = document.getElementById("win-modal");
  const won   = g.winner_id === state.player.player_id;
  document.getElementById("win-title").textContent = won ? "🏆 Victory!" : "💀 Defeated";
  document.getElementById("win-text").textContent  = won
    ? `You sunk every ship. Game #${g.id} is yours.`
    : `${getUsername(g.winner_id)} wins Game #${g.id}. Better luck next time.`;

  const p          = state.player;
  const gameShots  = Math.max(0, (p.total_shots || 0) - state.gameStartShots);
  const gameHits   = Math.max(0, (p.total_hits  || 0) - state.gameStartHits);
  const gameMisses = Math.max(0, gameShots - gameHits);
  const gameAcc    = gameShots > 0 ? Math.round((gameHits / gameShots) * 100) : 0;

  document.getElementById("postgame-this-game").innerHTML = statGrid([
    { val: gameShots,      label: "Shots"    },
    { val: gameHits,       label: "Hits"     },
    { val: gameMisses,     label: "Misses"   },
    { val: `${gameAcc}%`, label: "Accuracy" },
  ]);

  const lifeAcc = p.total_shots ? Math.round((p.total_hits / p.total_shots) * 100) : 0;
  document.getElementById("postgame-lifetime").innerHTML = statGrid([
    { val: p.wins        || 0, label: "Wins"     },
    { val: p.losses      || 0, label: "Losses"   },
    { val: p.total_shots || 0, label: "Shots"    },
    { val: `${lifeAcc}%`,     label: "Accuracy" },
  ]);

  modal.classList.remove("hidden");
}

function statGrid(items) {
  return items.map(i => `
    <div class="stat-item">
      <span class="stat-val">${i.val}</span>
      <span class="stat-label">${i.label}</span>
    </div>`).join("");
}

// ============================================================
// LEADERBOARD
// ============================================================
async function showLeaderboard() {
  const modal = document.getElementById("leaderboard-modal");
  const body  = document.getElementById("leaderboard-body");
  modal.classList.remove("hidden");
  body.innerHTML = `<p class="empty">Loading...</p>`;
  try {
    const players = await api.getLeaderboard();
    if (!players.length) { body.innerHTML = `<p class="empty">No players yet.</p>`; return; }
    body.innerHTML = players.slice(0, 5).map((p, i) => {
      const rank   = i + 1;
      const podium = rank <= 3 ? `podium-${rank}` : "";
      const acc    = p.total_shots ? Math.round((p.total_hits / p.total_shots) * 100) : 0;
      const medal  = rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : "";
      return `
        <div class="lb-row ${podium}">
          <span class="lb-rank">${medal || `#${rank}`}</span>
          <span class="lb-name">${p.username}</span>
          <span class="lb-stat">${p.wins}W</span>
          <span class="lb-stat">${p.losses}L</span>
          <span class="lb-stat">${acc}%</span>
        </div>`;
    }).join("");
  } catch (e) {
    body.innerHTML = `<p class="empty">Could not load leaderboard.</p>`;
  }
}

// ============================================================
// EVENT WIRING
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  loadTheme();

  // Theme toggles
  document.querySelectorAll(".btn-theme").forEach(btn => {
    btn.addEventListener("click", toggleTheme);
  });

  // Login
  document.getElementById("btn-login").addEventListener("click", handleLogin);
  document.getElementById("username-input").addEventListener("keydown", e => {
    if (e.key === "Enter") handleLogin();
  });

  // Topbar
  document.getElementById("btn-logout").addEventListener("click", handleLogout);
  document.getElementById("btn-leaderboard").addEventListener("click", showLeaderboard);
  document.getElementById("btn-close-lb").addEventListener("click", () => {
    document.getElementById("leaderboard-modal").classList.add("hidden");
  });

  // Lobby
  document.getElementById("btn-refresh").addEventListener("click", refreshLobby);
  document.getElementById("btn-create").addEventListener("click", handleCreateGame);

  // Game
  document.getElementById("btn-back").addEventListener("click", () => {
    state.currentGame = null;
    state.hitStreak   = 0;
    showView("lobby");
  });

  // Post-game modal
  document.getElementById("btn-win-close").addEventListener("click", () => {
    document.getElementById("win-modal").classList.add("hidden");
    state.currentGame = null;
    state.hitStreak   = 0;
    showView("lobby");
  });

  if (!tryAutoLogin()) showView("login");
});