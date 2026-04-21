/* ============================================================
   BATTLESHIP — app.js
   Vanilla JS client. Talks to Flask API on Render.
   State: localStorage for player identity, in-memory for game state.
   Sync: 2-second polling while in a game or on the lobby.
   ============================================================ */

// ============================================================
// CONFIG
// ============================================================
const API_BASE = "https://finalproject-battleship.onrender.com/api";
const POLL_INTERVAL_MS = 2000;
const SHIPS_PER_PLAYER = 3;

// ============================================================
// STATE
// ============================================================
const state = {
  player: null,           // { player_id, username, ... }
  view: "login",          // "login" | "lobby" | "game"
  games: [],              // lobby list
  currentGame: null,      // full game object
  moves: [],              // move history for current game
  myShips: [],            // ships I placed this game
  pendingPlacements: [],  // ships being placed before submission
  selectedOpponent: null, // player_id of opponent shown on right board
  pollHandle: null,
  gameStartMoves: 0,      // move count snapshot when we entered the game
  gameStartShots: 0,      // lifetime shots when we entered the game
  gameStartHits: 0,       // lifetime hits when we entered the game
};

// ============================================================
// API WRAPPER
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
    try {
      data = await res.json();
    } catch (e) {
      data = {};
    }
    if (!res.ok) {
      const msg = data.message || data.error || `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  },
  createPlayer:   (username)               => api.request("POST", "/players", { username }),
  getPlayer:      (id)                     => api.request("GET",  `/players/${id}`),
  listGames:      ()                       => api.request("GET",  "/games"),
  createGame:     (gridSize, maxPlayers, creatorId) =>
    api.request("POST", "/games", { grid_size: gridSize, max_players: maxPlayers, creator_id: creatorId }),
  getGame:        (id)                     => api.request("GET",  `/games/${id}`),
  joinGame:       (gameId, playerId)       => api.request("POST", `/games/${gameId}/join`, { player_id: playerId }),
  startGame:      (gameId)                 => api.request("POST", `/games/${gameId}/start`),
  placeShips:     (gameId, playerId, ships) =>
    api.request("POST", `/games/${gameId}/place`, { player_id: playerId, ships }),
  fire:           (gameId, playerId, row, col) =>
    api.request("POST", `/games/${gameId}/fire`, { player_id: playerId, row, col }),
  getMoves:       (gameId)                 => api.request("GET",  `/games/${gameId}/moves`),
  getLeaderboard: ()                       => api.request("GET",  "/leaderboard"),
  deleteGame:     (gameId, playerId)       =>
    api.request("DELETE", `/games/${gameId}`, { player_id: playerId }),
};

// ============================================================
// TOASTS
// ============================================================
function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
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

function startPolling(fn) {
  fn();
  state.pollHandle = setInterval(fn, POLL_INTERVAL_MS);
}
function stopPolling() {
  if (state.pollHandle) clearInterval(state.pollHandle);
  state.pollHandle = null;
}

// ============================================================
// LOGIN  —  username creates or retrieves existing account
// ============================================================
async function handleLogin() {
  const input = document.getElementById("username-input");
  const username = input.value.trim();
  if (!username) {
    toast("Enter a callsign first.", "error");
    return;
  }
  if (!/^[A-Za-z0-9_]+$/.test(username)) {
    toast("Letters, numbers, and underscores only.", "error");
    return;
  }

  const btn = document.getElementById("btn-login");
  btn.disabled = true;
  btn.textContent = "Signing in...";

  try {
    // Backend returns existing player if username already exists (201 either way)
    const player = await api.createPlayer(username);
    state.player = player;
    localStorage.setItem("battleship_player", JSON.stringify(player));
    document.getElementById("user-label").textContent = `⚓ ${player.username}`;
    showView("lobby");
    toast(`Welcome back, ${player.username}.`, "success");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Continue";
  }
}

function handleLogout() {
  localStorage.removeItem("battleship_player");
  state.player = null;
  state.currentGame = null;
  document.getElementById("username-input").value = "";
  showView("login");
}

function tryAutoLogin() {
  const saved = localStorage.getItem("battleship_player");
  if (!saved) return false;
  try {
    state.player = JSON.parse(saved);
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
    state.games = games;
    state.player = { ...state.player, ...me };
    renderGamesList();
    renderMyStats();
  } catch (e) {
    if (!state.games.length) toast(e.message, "error");
  }
}

function renderGamesList() {
  const container = document.getElementById("games-list");
  if (!state.games.length) {
    container.innerHTML = `<p class="empty">No games yet. Create one to get started.</p>`;
    return;
  }
  const myId = state.player.player_id;
  container.innerHTML = state.games.map(g => {
    const inGame      = (g.player_ids || []).includes(myId);
    const playerCount = (g.player_ids || []).length;
    const canJoin     = !inGame
      && (g.status === "waiting_setup" || g.status === "placing")
      && playerCount < g.max_players;
    const btnLabel    = inGame ? "Resume" : (canJoin ? "Join" : "View");
    const btnDisabled = !inGame && !canJoin && g.status !== "finished";
    const canDelete   = inGame; // any player who was in this game

    return `
      <div class="game-card ${inGame ? "mine" : ""}">
        <div class="game-card-info">
          <span class="game-card-id">Game #${g.id}</span>
          <span class="game-card-meta">
            ${g.grid_size}×${g.grid_size} grid •
            ${playerCount}/${g.max_players} players •
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
          ${canDelete ? `<button class="btn-delete" data-delete-id="${g.id}">Delete</button>` : ""}
        </div>
      </div>
    `;
  }).join("");

  container.querySelectorAll("button[data-game-id]").forEach(btn => {
    btn.addEventListener("click", () => {
      const gameId = parseInt(btn.dataset.gameId, 10);
      const action = btn.dataset.action;
      if (action === "join") joinGame(gameId);
      else enterGame(gameId);
    });
  });

  container.querySelectorAll("button[data-delete-id]").forEach(btn => {
    btn.addEventListener("click", () => {
      const gameId = parseInt(btn.dataset.deleteId, 10);
      handleDeleteGame(gameId);
    });
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
  const p = state.player;
  const accuracy = p.total_shots ? Math.round((p.total_hits / p.total_shots) * 100) : 0;
  document.getElementById("my-stats").innerHTML = `
    <div class="stat-item"><span class="stat-val">${p.wins || 0}</span><span class="stat-label">Wins</span></div>
    <div class="stat-item"><span class="stat-val">${p.losses || 0}</span><span class="stat-label">Losses</span></div>
    <div class="stat-item"><span class="stat-val">${p.total_shots || 0}</span><span class="stat-label">Shots</span></div>
    <div class="stat-item"><span class="stat-val">${accuracy}%</span><span class="stat-label">Accuracy</span></div>
  `;
}

async function handleCreateGame() {
  const gridSize   = parseInt(document.getElementById("grid-size").value, 10);
  const maxPlayers = parseInt(document.getElementById("max-players").value, 10);
  if (gridSize < 5 || gridSize > 15)   { toast("Grid size must be 5 to 15.", "error"); return; }
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
// GAME
// ============================================================
async function enterGame(gameId) {
  // Snapshot lifetime stats so we can diff them after the game ends
  const me = state.player;
  state.gameStartShots = me.total_shots || 0;
  state.gameStartHits  = me.total_hits  || 0;

  state.currentGame       = { id: gameId };
  state.pendingPlacements = [];
  state.myShips           = [];
  state.selectedOpponent  = null;
  document.getElementById("game-id-label").textContent = `#${gameId}`;
  showView("game");
}

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

    renderGameView();

    if (game.status === "finished" && !wasFinished) {
      // Fetch fresh player stats before showing modal
      try {
        const freshMe = await api.getPlayer(state.player.player_id);
        state.player = { ...state.player, ...freshMe };
      } catch (_) {}
      showPostGameModal(game);
    }
  } catch (e) {
    toast(e.message, "error");
  }
}

function renderGameView() {
  const g = state.currentGame;
  if (!g || !g.status) return;

  const statusEl = document.getElementById("game-status-label");
  statusEl.className = `status-pill status-${g.status}`;
  statusEl.textContent = g.status.replace("_", " ");

  const turnEl = document.getElementById("turn-label");
  turnEl.classList.remove("my-turn");
  if (g.status === "active") {
    if (g.current_turn_player_id === state.player.player_id) {
      turnEl.textContent = "🎯 Your turn";
      turnEl.classList.add("my-turn");
    } else {
      turnEl.textContent = "Waiting for opponent...";
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
}

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
    const placed    = state.myShips.length;
    if (placed >= SHIPS_PER_PLAYER) {
      banner.textContent = "Ships placed. Waiting for other players...";
    } else {
      const remaining = SHIPS_PER_PLAYER - state.pendingPlacements.length;
      if (state.pendingPlacements.length === SHIPS_PER_PLAYER) {
        banner.innerHTML = `All ${SHIPS_PER_PLAYER} ships placed.
          <button id="banner-confirm" class="primary small" style="margin-left:12px">Confirm Placement</button>
          <button id="banner-clear" class="ghost small" style="margin-left:6px">Clear</button>`;
        const cBtn = document.getElementById("banner-confirm");
        const xBtn = document.getElementById("banner-clear");
        if (cBtn) cBtn.onclick = handleConfirmPlacement;
        if (xBtn) xBtn.onclick = () => { state.pendingPlacements = []; renderGameView(); };
      } else {
        banner.textContent = `Click your board to place ${remaining} more ship${remaining !== 1 ? "s" : ""}.`;
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
  try {
    await api.placeShips(
      state.currentGame.id,
      state.player.player_id,
      state.pendingPlacements
    );
    state.myShips           = [...state.pendingPlacements];
    state.pendingPlacements = [];
    toast("Ships locked in.", "success");
    refreshGame();
  } catch (e) {
    toast(e.message, "error");
  }
}

// ============================================================
// BOARD RENDERING
// ============================================================
function makeBoardGrid(boardEl, size) {
  boardEl.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
  boardEl.style.gridTemplateRows    = `repeat(${size}, 1fr)`;
  boardEl.innerHTML = "";
  const cells = [];
  for (let r = 0; r < size; r++) {
    cells[r] = [];
    for (let c = 0; c < size; c++) {
      const cell = document.createElement("div");
      cell.className    = "cell";
      cell.dataset.row  = r;
      cell.dataset.col  = c;
      boardEl.appendChild(cell);
      cells[r][c] = cell;
    }
  }
  return cells;
}

function renderMyBoard(g) {
  const boardEl = document.getElementById("my-board");
  const size    = g.grid_size;
  const cells   = makeBoardGrid(boardEl, size);
  const myId    = state.player.player_id;
  const inGame  = (g.player_ids || []).includes(myId);

  state.myShips.forEach(s => {
    if (cells[s.row] && cells[s.row][s.col]) cells[s.row][s.col].classList.add("ship");
  });

  state.pendingPlacements.forEach(s => {
    if (cells[s.row] && cells[s.row][s.col]) cells[s.row][s.col].classList.add("placement-preview");
  });

  state.moves.filter(m => m.player_id !== myId).forEach(m => {
    if (!cells[m.row] || !cells[m.row][m.col]) return;
    const cell = cells[m.row][m.col];
    cell.classList.remove("ship", "placement-preview");
    cell.classList.add(m.result === "hit" ? "hit" : "miss");
  });

  if (inGame && g.status === "placing" && state.myShips.length === 0) {
    cells.forEach(row => row.forEach(cell => {
      if (cell.classList.contains("hit") || cell.classList.contains("miss")) return;
      cell.classList.add("placeable");
      cell.addEventListener("click", () => handlePlacementClick(
        parseInt(cell.dataset.row, 10),
        parseInt(cell.dataset.col, 10)
      ));
    }));
  }
}

function handlePlacementClick(row, col) {
  const idx = state.pendingPlacements.findIndex(s => s.row === row && s.col === col);
  if (idx >= 0) {
    state.pendingPlacements.splice(idx, 1);
  } else {
    if (state.pendingPlacements.length >= SHIPS_PER_PLAYER) {
      toast(`Only ${SHIPS_PER_PLAYER} ships allowed. Click a placed ship to remove it.`, "error");
      return;
    }
    state.pendingPlacements.push({ row, col });
  }
  renderGameView();
}

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
        Player ${p.player_id} (${p.ships_remaining} ships)
      </button>
    `).join("");
    tabsEl.querySelectorAll("button[data-pid]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.selectedOpponent = parseInt(btn.dataset.pid, 10);
        renderGameView();
      });
    });
  } else {
    tabsEl.innerHTML = "";
  }

  document.getElementById("opp-title").textContent =
    opponents.length > 1
      ? `Targeting Player ${state.selectedOpponent}`
      : `Opponent's Board (Player ${state.selectedOpponent})`;

  const cells = makeBoardGrid(boardEl, g.grid_size);

  state.moves.filter(m => m.player_id === myId).forEach(m => {
    if (!cells[m.row] || !cells[m.row][m.col]) return;
    cells[m.row][m.col].classList.add(m.result === "hit" ? "hit" : "miss");
  });

  const myTurn = g.status === "active" && g.current_turn_player_id === myId;
  if (myTurn) {
    cells.forEach(row => row.forEach(cell => {
      if (cell.classList.contains("hit") || cell.classList.contains("miss")) return;
      cell.classList.add("clickable");
      cell.addEventListener("click", () => handleFire(
        parseInt(cell.dataset.row, 10),
        parseInt(cell.dataset.col, 10)
      ));
    }));
  }
}

async function handleFire(row, col) {
  try {
    const result = await api.fire(state.currentGame.id, state.player.player_id, row, col);
    toast(result.result === "hit" ? "🔥 HIT!" : "Splash. Miss.",
          result.result === "hit" ? "success" : "info");
    refreshGame();
  } catch (e) {
    toast(e.message, "error");
  }
}

// ============================================================
// MOVE HISTORY + PLAYERS
// ============================================================
function renderMoveHistory() {
  const el = document.getElementById("move-history");
  if (!state.moves.length) {
    el.innerHTML = `<p class="empty">No moves yet.</p>`;
    return;
  }
  el.innerHTML = state.moves.slice().reverse().map(m => {
    const time = new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const isMe = m.player_id === state.player.player_id;
    return `
      <div class="move-row">
        <span class="move-num">#${m.move_number}</span>
        <span class="move-player">${isMe ? "You" : `Player ${m.player_id}`}</span>
        <span class="move-coords">(${m.row}, ${m.col})</span>
        <span class="move-result ${m.result}">${m.result.toUpperCase()}</span>
      </div>
    `;
  }).join("");
}

function renderPlayersList(g) {
  const el      = document.getElementById("players-list");
  const players = g.players || [];
  el.innerHTML  = players.map(p => {
    const isMe       = p.player_id === state.player.player_id;
    const isCurrent  = g.current_turn_player_id === p.player_id;
    const eliminated = p.ships_remaining === 0;
    return `
      <div class="player-row ${isCurrent ? "current" : ""} ${eliminated ? "eliminated" : ""}">
        <span class="player-name">${isMe ? "You" : `Player ${p.player_id}`}${isCurrent ? " 🎯" : ""}</span>
        <span class="player-ships">${p.ships_remaining} ships</span>
      </div>
    `;
  }).join("");
}

// ============================================================
// POST-GAME MODAL  —  this game stats + lifetime stats
// ============================================================
function showPostGameModal(g) {
  const modal = document.getElementById("win-modal");
  const title = document.getElementById("win-title");
  const text  = document.getElementById("win-text");
  const won   = g.winner_id === state.player.player_id;

  title.textContent = won ? "🏆 Victory!" : "💀 Defeated";
  text.textContent  = won
    ? `You sunk every opposing ship. Game #${g.id} is yours.`
    : `Player ${g.winner_id} wins game #${g.id}. Better luck next time.`;

  // This game stats — diff against snapshot taken when we entered
  const p             = state.player;
  const gameShotsRaw  = (p.total_shots || 0) - state.gameStartShots;
  const gameHitsRaw   = (p.total_hits  || 0) - state.gameStartHits;
  const gameShots     = Math.max(0, gameShotsRaw);
  const gameHits      = Math.max(0, gameHitsRaw);
  const gameMisses    = Math.max(0, gameShots - gameHits);
  const gameAccuracy  = gameShots > 0 ? Math.round((gameHits / gameShots) * 100) : 0;

  document.getElementById("postgame-this-game").innerHTML = statGrid([
    { val: gameShots,          label: "Shots"    },
    { val: gameHits,           label: "Hits"     },
    { val: gameMisses,         label: "Misses"   },
    { val: `${gameAccuracy}%`, label: "Accuracy" },
  ]);

  // Lifetime stats
  const lifetimeAcc = p.total_shots
    ? Math.round((p.total_hits / p.total_shots) * 100)
    : 0;

  document.getElementById("postgame-lifetime").innerHTML = statGrid([
    { val: p.wins          || 0,   label: "Wins"      },
    { val: p.losses        || 0,   label: "Losses"    },
    { val: p.total_shots   || 0,   label: "Shots"     },
    { val: `${lifetimeAcc}%`,      label: "Accuracy"  },
  ]);

  modal.classList.remove("hidden");
}

function statGrid(items) {
  return items.map(item => `
    <div class="stat-item">
      <span class="stat-val">${item.val}</span>
      <span class="stat-label">${item.label}</span>
    </div>
  `).join("");
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
    if (!players.length) {
      body.innerHTML = `<p class="empty">No players yet.</p>`;
      return;
    }
    body.innerHTML = players.map((p, i) => {
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
        </div>
      `;
    }).join("");
  } catch (e) {
    body.innerHTML = `<p class="empty">Could not load leaderboard.</p>`;
  }
}

// ============================================================
// EVENT WIRING
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
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
    showView("lobby");
  });

  // Post-game modal close
  document.getElementById("btn-win-close").addEventListener("click", () => {
    document.getElementById("win-modal").classList.add("hidden");
    state.currentGame = null;
    showView("lobby");
  });

  // Auto-login if we have a saved player
  if (!tryAutoLogin()) showView("login");
});