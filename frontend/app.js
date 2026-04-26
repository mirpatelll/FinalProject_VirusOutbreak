/* ============================================================
   BATTLESHIP — app.js
   ============================================================ */

/* ============================================================
   SERVER CONFIGURATION (CPSC 3750 Phase 1 interoperability)
   Always defaults to OUR server on page load. The grader can
   switch with the "Join different server" button on login.
   ============================================================ */
const DEFAULT_SERVER_URL = "https://finalproject-battleship.onrender.com/api";

let API_BASE = DEFAULT_SERVER_URL;
const POLL_INTERVAL_MS = 2000;

function normalizeServerUrl(raw) {
  if (!raw) return null;
  let url = raw.trim();
  if (!url) return null;
  // Add https:// if missing a scheme
  if (!/^https?:\/\//i.test(url)) url = "https://" + url;
  // Strip trailing slash
  url = url.replace(/\/+$/, "");
  return url;
}

async function setServer(rawUrl) {
  const url = normalizeServerUrl(rawUrl);
  if (!url) { toast("Enter a server URL.", "error"); return; }
  if (url === API_BASE) { toast("Already on this server.", "info"); return; }

  toast("Testing connection...", "info");
  const useBtn = document.getElementById("btn-server-login");
  if (useBtn) { useBtn.disabled = true; useBtn.textContent = "Testing..."; }

  // Try the URL as-is, then with /api appended, then stripping /api,
  // then root domain. We probe GET <base>/games as a cheap reachability test.
  const candidates = [];
  const stripped = url.replace(/\/+$/, "");
  candidates.push(stripped);
  if (!/\/api(\/|$)/i.test(stripped)) candidates.push(stripped + "/api");
  if (/\/api$/i.test(stripped)) candidates.push(stripped.replace(/\/api$/i, ""));
  // De-duplicate
  const tried = [...new Set(candidates)];

  let workingBase = null;
  let lastNetworkError = false;
  let last404 = false;
  for (const base of tried) {
    try {
      const res = await fetch(`${base}/games`, { method: "GET" });
      if (res.status === 404) { last404 = true; continue; }
      // Any other response (200, 401, 500, etc.) means we found the right path
      workingBase = base;
      break;
    } catch (_) {
      // Network-level failure (CORS, DNS, offline)
      lastNetworkError = true;
    }
  }

  if (useBtn) { useBtn.disabled = false; useBtn.textContent = "Use This Server"; }

  if (!workingBase) {
    if (lastNetworkError) {
      toast("Cannot reach that server (likely CORS or wrong host).", "error");
    } else if (last404) {
      toast(`No /games endpoint found at ${url}. Check the path.`, "error");
    } else {
      toast(`Couldn't connect to ${url}.`, "error");
    }
    return;
  }

  API_BASE = workingBase;
  clearToasts();  // wipe any stale error toasts from previous server
  // Reset state when switching servers
  localStorage.removeItem("battleship_player");
  state.player = null;
  state.currentGame = null;
  state.usernameCache = {};
  stopPolling();
  document.getElementById("username-input").value = "";
  toast(`Connected to ${workingBase}. Please sign in.`, "success");
  updateServerStatusDisplay();
  hideServerSwitcher();
  showView("login");
}

function resetToHomeServer() {
  if (API_BASE === DEFAULT_SERVER_URL) { toast("Already on home server.", "info"); return; }
  API_BASE = DEFAULT_SERVER_URL;
  clearToasts();
  localStorage.removeItem("battleship_player");
  state.player = null;
  state.currentGame = null;
  state.usernameCache = {};
  stopPolling();
  document.getElementById("username-input").value = "";
  toast("Switched back to home server.", "success");
  updateServerStatusDisplay();
  hideServerSwitcher();
  showView("login");
}

function updateServerStatusDisplay() {
  const isHome = API_BASE === DEFAULT_SERVER_URL;
  const label = document.getElementById("server-status-label");
  const resetBtn = document.getElementById("btn-reset-server");
  if (label) {
    label.textContent = isHome
      ? "Connected to our server (home)"
      : `Connected to: ${API_BASE}`;
    label.classList.toggle("server-status-away", !isHome);
  }
  if (resetBtn) resetBtn.classList.toggle("hidden", isHome);
}

function showServerSwitcher() {
  document.getElementById("server-switcher-collapsed")?.classList.add("hidden");
  document.getElementById("server-switcher-expanded")?.classList.remove("hidden");
  const input = document.getElementById("server-input-login");
  if (input) {
    input.value = "";  // start clean each time, no stale browser autofill
    setTimeout(() => input.focus(), 0);
  }
}

function hideServerSwitcher() {
  document.getElementById("server-switcher-collapsed")?.classList.remove("hidden");
  document.getElementById("server-switcher-expanded")?.classList.add("hidden");
}

const SHIP_DEFS = [
  { type: "submarine",  length: 1, label: "Submarine",  blockClass: "sub"  },
  { type: "destroyer",  length: 2, label: "Destroyer",  blockClass: "dest" },
  { type: "cruiser",    length: 3, label: "Cruiser",    blockClass: "crui" },
  { type: "battleship", length: 4, label: "Battleship", blockClass: "batt" },
];

const state = {
  player:            null,
  view:              "login",
  games:             [],
  currentGame:       null,
  isSpectator:       false,
  moves:             [],
  myShips:           [],
  placementShips:    [],
  selectedShipType:  "submarine",
  orientation:       "H",
  selectedOpponent:  null,
  pollHandle:        null,
  gameStartShots:    0,
  gameStartHits:     0,
  hitStreak:         0,
  usernameCache:     {},
  pastGamesOpen:     false,
  theme:             "dark",
  chatMessages:      [],
  rematchId:         null,
  rematchStatus:     null,
};

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme === "light" ? "light" : "");
  localStorage.setItem("battleship_theme", theme);
  document.querySelectorAll(".btn-theme").forEach(btn => {
    btn.textContent = theme === "light" ? "🌙" : "☀️";
    btn.title       = theme === "light" ? "Switch to dark mode" : "Switch to light mode";
  });
}
function toggleTheme() { applyTheme(state.theme === "dark" ? "light" : "dark"); }
function loadTheme()   { applyTheme(localStorage.getItem("battleship_theme") || "dark"); }

const api = {
  async request(method, path, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body) opts.body = JSON.stringify(body);
    // Capture the API_BASE at request time. If it changed by the time the
    // response comes back, the user switched servers — drop this response silently.
    const baseAtRequestTime = API_BASE;
    let res, data;
    try { res = await fetch(`${baseAtRequestTime}${path}`, opts); }
    catch (e) {
      if (baseAtRequestTime !== API_BASE) throw new Error("__stale__");
      throw new Error("Cannot reach server.");
    }
    if (baseAtRequestTime !== API_BASE) throw new Error("__stale__");
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) {
      const msg = data.message || data.error || `Error ${res.status}`;
      const err = new Error(msg);
      err.status = res.status; err.data = data; err.path = path; throw err;
    }
    return data;
  },
  createPlayer:   (username)           => api.request("POST",   "/players",                  { username }),
  getPlayer:      (id)                 => api.request("GET",    `/players/${id}`),
  listGames:      ()                   => api.request("GET",    "/games"),
  createGame:     (gs, mp, cid)        => api.request("POST",   "/games",                    { grid_size: gs, max_players: mp, creator_id: cid }),
  getGame:        (id)                 => api.request("GET",    `/games/${id}`),
  spectateGame:   (id)                 => api.request("GET",    `/games/${id}/spectate`),
  joinGame:       (gid, pid)           => api.request("POST",   `/games/${gid}/join`,        { player_id: pid }),
  startGame:      (gid)               => api.request("POST",   `/games/${gid}/start`),
  placeShips:     (gid, pid, ships)    => api.request("POST",   `/games/${gid}/place`,       { player_id: pid, ships }),
  fire:           (gid, pid, row, col) => api.request("POST",   `/games/${gid}/fire`,        { player_id: pid, row, col }),
  getMoves:       (gid)               => api.request("GET",    `/games/${gid}/moves`),
  getLeaderboard: ()                  => api.request("GET",    "/leaderboard"),
  deleteGame:     (gid, pid)          => api.request("DELETE", `/games/${gid}?player_id=${pid}`),
  getChat:        (gid, pid)          => api.request("GET",    `/games/${gid}/chat?player_id=${pid}`),
  sendChat:       (gid, pid, msg)     => api.request("POST",   `/games/${gid}/chat`,        { player_id: pid, message: msg }),
  requestRematch: (gid, pid)          => api.request("POST",   `/games/${gid}/rematch`,     { player_id: pid }),
  getRematch:     (gid, pid)          => api.request("GET",    `/games/${gid}/rematch?player_id=${pid}`),
  respondRematch: (rid, pid, action)  => api.request("POST",   `/rematch/${rid}/respond`,   { player_id: pid, action }),
};

async function resolveUsername(playerId) {
  if (!playerId) return `Player ${playerId}`;
  if (state.usernameCache[playerId]) return state.usernameCache[playerId];
  try {
    const p = await api.getPlayer(playerId);
    state.usernameCache[playerId] = p.username || `Player ${playerId}`;
  } catch (_) { state.usernameCache[playerId] = `Player ${playerId}`; }
  return state.usernameCache[playerId];
}
function getUsername(pid) { return state.usernameCache[pid] || `Player ${pid}`; }

function toast(message, type = "info") {
  if (message === "__stale__" || !message) return;  // suppress dropped/stale request errors
  const el = document.createElement("div");
  el.className = `toast ${type}`; el.textContent = message;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => { el.classList.add("fading"); setTimeout(() => el.remove(), 250); }, 3500);
}

function clearToasts() {
  document.querySelectorAll("#toast-container .toast").forEach(t => t.remove());
}

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

function closeWinModal() {
  document.getElementById("win-modal").classList.add("hidden");
  state.currentGame = null;
  state.hitStreak   = 0;
  showView("lobby");
}

// Normalize player objects across different server conventions
function normalizePlayer(p) {
  if (!p || typeof p !== "object") return null;
  const player_id = p.player_id ?? p.playerId ?? p.id ?? p.playerld;
  const username  = p.username ?? p.displayName ?? p.playerName ?? p.name;
  if (player_id == null) return null;
  return { ...p, player_id, username };
}

async function handleLogin() {
  const input    = document.getElementById("username-input");
  const username = input.value.trim();
  if (!username) { toast("Enter a callsign first.", "error"); return; }
  if (!/^[A-Za-z0-9_]+$/.test(username)) { toast("Letters, numbers, underscores only.", "error"); return; }
  const btn = document.getElementById("btn-login");
  btn.disabled = true; btn.textContent = "Signing in...";
  try {
    let raw;
    try {
      raw = await api.createPlayer(username);
    } catch (e) {
      // Some servers return 409 on duplicate username — treat as login.
      // The existing player may be in e.data, otherwise fall back to listing.
      if (e.status === 409) {
        if (e.data && (e.data.player_id ?? e.data.playerId ?? e.data.id) != null) {
          raw = e.data;
        } else {
          throw new Error("Username taken on this server. Try a different callsign.");
        }
      } else {
        throw e;
      }
    }
    const player = normalizePlayer(raw);
    if (!player) { throw new Error("Server returned an unexpected player format."); }
    state.player = player;
    state.usernameCache[player.player_id] = player.username;
    localStorage.setItem("battleship_player", JSON.stringify(player));
    document.getElementById("user-label").textContent = `⚓ ${player.username}`;
    showView("lobby");
    toast(`Welcome, ${player.username}.`, "success");
  } catch (e) { toast(e.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "Continue"; }
}

function handleLogout() {
  localStorage.removeItem("battleship_player");
  state.player = null; state.currentGame = null;
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
  } catch (e) { localStorage.removeItem("battleship_player"); return false; }
}

async function refreshLobby() {
  try {
    const [games, me] = await Promise.all([api.listGames(), api.getPlayer(state.player.player_id)]);
    state.games  = games;
    state.player = { ...state.player, ...me };
    const ids = new Set();
    games.forEach(g => (g.player_ids || []).forEach(id => ids.add(id)));
    await Promise.all([...ids].map(id => resolveUsername(id)));
    renderGamesList();
    renderMyStats();
    renderPastGames();
  } catch (e) { if (!state.games.length) toast(e.message, "error"); }
}

function renderGamesList() {
  const container   = document.getElementById("games-list");
  const activeGames = state.games.filter(g => g.status !== "finished");
  if (!activeGames.length) { container.innerHTML = `<p class="empty">No open games. Create one!</p>`; return; }
  const myId = state.player.player_id;
  container.innerHTML = activeGames.map(g => {
    const inGame      = (g.player_ids || []).includes(myId);
    const playerCount = (g.player_ids || []).length;
    const canJoin     = !inGame && (g.status === "waiting_setup" || g.status === "placing") && playerCount < g.max_players;
    const canSpectate = !inGame && (g.status === "playing" || g.status === "active");
    const btnLabel    = inGame ? "Resume" : (canJoin ? "Join" : (canSpectate ? "Watch" : "View"));
    const btnDisabled = !inGame && !canJoin && !canSpectate;
    const otherNames  = (g.player_ids || []).filter(id => id !== myId).map(id => getUsername(id)).join(", ");
    const playerMeta  = inGame && otherNames ? `vs ${otherNames}` : `${playerCount}/${g.max_players} players`;
    return `
      <div class="game-card ${inGame ? "mine" : ""}">
        <div class="game-card-info">
          <span class="game-card-id">Game #${g.id}</span>
          <span class="game-card-meta">${g.grid_size}×${g.grid_size} • ${playerMeta} • <span class="status-pill status-${g.status}">${g.status.replace("_"," ")}</span></span>
        </div>
        <div class="game-card-actions">
          <button class="${inGame ? "primary" : "ghost"} small" ${btnDisabled ? "disabled" : ""}
                  data-game-id="${g.id}" data-action="${inGame ? "resume" : (canJoin ? "join" : (canSpectate ? "spectate" : "view"))}">
            ${btnLabel}
          </button>
          ${inGame ? `<button class="btn-delete" data-delete-id="${g.id}">Delete</button>` : ""}
        </div>
      </div>`;
  }).join("");
  container.querySelectorAll("button[data-game-id]").forEach(btn => {
    btn.addEventListener("click", () => {
      const gid = parseInt(btn.dataset.gameId, 10);
      if (btn.dataset.action === "join") joinGame(gid);
      else if (btn.dataset.action === "spectate") enterSpectator(gid);
      else enterGame(gid);
    });
  });
  container.querySelectorAll("button[data-delete-id]").forEach(btn => {
    btn.addEventListener("click", () => handleDeleteGame(parseInt(btn.dataset.deleteId, 10)));
  });
}

async function handleDeleteGame(gameId) {
  if (!confirm(`Delete Game #${gameId}? This cannot be undone.`)) return;
  try { await api.deleteGame(gameId, state.player.player_id); toast(`Game #${gameId} deleted.`, "success"); refreshLobby(); }
  catch (e) { toast(e.message, "error"); }
}

function renderMyStats() {
  const p = state.player;
  const accuracy = p.total_shots ? Math.round((p.total_hits / p.total_shots) * 100) : 0;
  document.getElementById("my-stats").innerHTML = `
    <div class="stat-item"><span class="stat-val">${p.wins||0}</span><span class="stat-label">Wins</span></div>
    <div class="stat-item"><span class="stat-val">${p.losses||0}</span><span class="stat-label">Losses</span></div>
    <div class="stat-item"><span class="stat-val">${p.total_shots||0}</span><span class="stat-label">Shots</span></div>
    <div class="stat-item"><span class="stat-val">${accuracy}%</span><span class="stat-label">Accuracy</span></div>`;
}

function renderPastGames() {
  const section  = document.getElementById("past-games-section");
  if (!section) return;
  const myId     = state.player.player_id;
  const finished = state.games.filter(g => g.status === "finished" && (g.player_ids||[]).includes(myId));
  if (!finished.length) {
    section.innerHTML = `<div class="past-games-section"><div class="past-games-toggle"><h3>Past Games</h3><span class="toggle-arrow">▼</span></div><p class="empty" style="padding:12px 0 0;font-size:12px">No finished games yet.</p></div>`;
    return;
  }
  const rows = finished.map(g => {
    const won = g.winner_id === myId; const cls = won ? "win" : "loss";
    const oppNames = (g.player_ids||[]).filter(id => id !== myId).map(id => getUsername(id)).join(", ") || "Unknown";
    return `<div class="past-game-row ${cls}"><div class="past-game-info"><span class="past-game-id">Game #${g.id}</span><span class="past-game-vs">vs ${oppNames}</span></div><span class="past-game-result ${cls}">${won?"WIN":"LOSS"}</span></div>`;
  }).join("");
  const isOpen = state.pastGamesOpen;
  section.innerHTML = `<div class="past-games-section"><div class="past-games-toggle ${isOpen?"open":""}" id="past-games-toggle"><h3>Past Games (${finished.length})</h3><span class="toggle-arrow">▼</span></div>${isOpen?`<div class="past-games-list">${rows}</div>`:""}</div>`;
  document.getElementById("past-games-toggle").addEventListener("click", () => { state.pastGamesOpen = !state.pastGamesOpen; renderPastGames(); });
}

async function handleCreateGame() {
  const gs = parseInt(document.getElementById("grid-size").value, 10);
  const mp = parseInt(document.getElementById("max-players").value, 10);
  if (gs < 5 || gs > 15)  { toast("Grid size must be 5 to 15.", "error"); return; }
  if (mp < 2 || mp > 10)  { toast("Max players must be 2 to 10.", "error"); return; }
  try { const game = await api.createGame(gs, mp, state.player.player_id); toast(`Game #${game.id} created.`, "success"); enterGame(game.id); }
  catch (e) { toast(e.message, "error"); }
}

async function joinGame(gameId) {
  try { await api.joinGame(gameId, state.player.player_id); toast(`Joined game #${gameId}.`, "success"); enterGame(gameId); }
  catch (e) { toast(e.message, "error"); }
}

async function enterSpectator(gameId) {
  state.isSpectator = true; state.currentGame = { id: gameId }; state.hitStreak = 0;
  document.getElementById("game-id-label").textContent = `#${gameId}`;
  document.getElementById("spectator-banner").classList.remove("hidden");
  document.getElementById("chat-panel").classList.add("hidden");
  document.getElementById("phase-banner").classList.add("hidden");
  showView("game");
}

async function enterGame(gameId) {
  state.isSpectator = false; state.gameStartShots = state.player.total_shots||0; state.gameStartHits = state.player.total_hits||0;
  state.hitStreak = 0; state.currentGame = { id: gameId }; state.myShips = []; state.placementShips = [];
  state.selectedShipType = "submarine"; state.orientation = "H"; state.selectedOpponent = null;
  state.chatMessages = []; state.rematchId = null; state.rematchStatus = null;
  document.getElementById("spectator-banner").classList.add("hidden");
  document.getElementById("game-id-label").textContent = `#${gameId}`;
  showView("game");
}

async function refreshGame() {
  if (!state.currentGame) return;
  try {
    if (state.isSpectator) {
      const game = await api.spectateGame(state.currentGame.id);
      state.currentGame = game; state.moves = game.moves || [];
      await Promise.all((game.player_ids||[]).map(id => resolveUsername(id)));
      renderSpectatorView(game); return;
    }
    const [game, moves] = await Promise.all([api.getGame(state.currentGame.id), api.getMoves(state.currentGame.id)]);
    const wasFinished = state.currentGame.status === "finished";
    state.currentGame = game; state.moves = moves;
    await Promise.all((game.player_ids||[]).map(id => resolveUsername(id)));
    renderGameView();
    if ((game.status === "playing" || game.status === "active") || game.status === "placing") pollChat();
    if (game.status === "finished" && !wasFinished) {
      try { const freshMe = await api.getPlayer(state.player.player_id); state.player = { ...state.player, ...freshMe }; } catch (_) {}
      showPostGameModal(game);
    }
    if (game.status === "finished") pollRematch();
  } catch (e) { toast(e.message, "error"); }
}

function renderSpectatorView(game) {
  const statusEl = document.getElementById("game-status-label");
  statusEl.className = `status-pill status-${game.status}`; statusEl.textContent = game.status.replace("_"," ");
  const turnEl = document.getElementById("turn-label"); turnEl.classList.remove("my-turn");
  if ((game.status === "playing" || game.status === "active")) turnEl.textContent = `${getUsername(game.current_turn_player_id)}'s turn`;
  else turnEl.textContent = game.status === "finished" ? "Game over" : game.status;
  const players = game.players || [];
  if (players.length < 2) return;
  const p1 = players[0]; const p2 = players[1];
  const boardEl1 = document.getElementById("my-board"); const cells1 = makeBoardGrid(boardEl1, game.grid_size);
  document.querySelector(".board-wrap h3").textContent = getUsername(p1.player_id);
  const boardEl2 = document.getElementById("opp-board"); const cells2 = makeBoardGrid(boardEl2, game.grid_size);
  document.getElementById("opp-title").textContent = getUsername(p2.player_id);
  document.getElementById("opp-tabs").innerHTML = "";
  state.moves.forEach(m => {
    if (m.player_id === p2.player_id && cells1[m.row]?.[m.col]) cells1[m.row][m.col].classList.add(m.result==="hit"?"hit":"miss");
    if (m.player_id === p1.player_id && cells2[m.row]?.[m.col]) cells2[m.row][m.col].classList.add(m.result==="hit"?"hit":"miss");
  });
  renderMoveHistory(); renderPlayersList(game); renderStreakBanner();
}

function renderGameView() {
  const g = state.currentGame;
  if (!g || !g.status) return;
  const statusEl = document.getElementById("game-status-label");
  statusEl.className = `status-pill status-${g.status}`; statusEl.textContent = g.status.replace("_"," ");
  const turnEl = document.getElementById("turn-label"); turnEl.classList.remove("my-turn");
  if ((g.status === "playing" || g.status === "active")) {
    if (g.current_turn_player_id === state.player.player_id) { turnEl.textContent = "🎯 Your turn"; turnEl.classList.add("my-turn"); }
    else turnEl.textContent = `Waiting for ${getUsername(g.current_turn_player_id)}...`;
  } else if (g.status === "finished") { turnEl.textContent = "Game over"; }
  else if (g.status === "placing")    { turnEl.textContent = "Place your ships"; }
  else { turnEl.textContent = `Waiting (${(g.player_ids||[]).length}/${g.max_players})`; }
  const inGame = (g.player_ids||[]).includes(state.player.player_id);
  if (inGame && ((g.status === "playing" || g.status === "active") || g.status === "placing" || g.status === "finished")) {
    document.getElementById("chat-panel").classList.remove("hidden");
  }
  renderPhaseBanner(g); renderMyBoard(g); renderOpponentBoard(g);
  renderMoveHistory(); renderPlayersList(g); renderStreakBanner(); renderChatMessages();
}

function renderPhaseBanner(g) {
  const banner = document.getElementById("phase-banner");
  const myId = state.player.player_id; const inGame = (g.player_ids||[]).includes(myId);
  if (!inGame) { banner.classList.add("hidden"); return; }
  if (g.status === "waiting_setup") {
    const need = g.max_players - (g.player_ids||[]).length;
    if ((g.player_ids||[]).length >= 2) {
      banner.innerHTML = `Waiting for more players. <button id="banner-start" class="primary small" style="margin-left:12px">Start Game</button>`;
      banner.classList.remove("hidden");
      const btn = document.getElementById("banner-start"); if (btn) btn.onclick = handleStartGame;
    } else { banner.textContent = `Waiting for ${need} more player${need!==1?"s":""}...`; banner.classList.remove("hidden"); }
  } else if (g.status === "placing") {
    if (state.myShips.length === 4) { banner.textContent = "All ships placed. Waiting for opponent..."; }
    else if (state.placementShips.length === 4) {
      banner.innerHTML = `All 4 ships placed! <button id="banner-confirm" class="primary small" style="margin-left:12px">Confirm</button> <button id="banner-clear" class="ghost small" style="margin-left:6px">Clear</button>`;
      const cBtn = document.getElementById("banner-confirm"); const xBtn = document.getElementById("banner-clear");
      if (cBtn) cBtn.onclick = handleConfirmPlacement; if (xBtn) xBtn.onclick = () => { state.placementShips = []; renderGameView(); };
    } else { const rem = 4 - state.placementShips.length; banner.textContent = `Place ${rem} more ship${rem!==1?"s":""}. Click your board.`; }
    banner.classList.remove("hidden");
  } else { banner.classList.add("hidden"); }
}

async function handleStartGame() {
  try { await api.startGame(state.currentGame.id); toast("Game started. Place your ships.", "success"); refreshGame(); }
  catch (e) { toast(e.message, "error"); }
}

async function handleConfirmPlacement() {
  const ships = state.placementShips.map(s => ({ ship_type: s.type, start_row: s.startRow, start_col: s.startCol, orientation: s.orientation }));
  try {
    await api.placeShips(state.currentGame.id, state.player.player_id, ships);
    state.myShips = [...state.placementShips]; state.placementShips = [];
    toast("Ships locked in!", "success"); refreshGame();
  } catch (e) { toast(e.message, "error"); }
}

function getShipCells(type, startRow, startCol, orientation) {
  const def = SHIP_DEFS.find(d => d.type === type); const length = def ? def.length : 1; const cells = [];
  for (let i = 0; i < length; i++) cells.push(orientation === "H" ? [startRow, startCol+i] : [startRow+i, startCol]);
  return cells;
}

function isValidPlacement(type, startRow, startCol, orientation, gridSize, existing) {
  const cells = getShipCells(type, startRow, startCol, orientation);
  const occupied = new Set();
  existing.forEach(s => getShipCells(s.type, s.startRow, s.startCol, s.orientation).forEach(([r,c]) => occupied.add(`${r},${c}`)));
  for (const [r,c] of cells) { if (r<0||r>=gridSize||c<0||c>=gridSize) return false; if (occupied.has(`${r},${c}`)) return false; }
  return true;
}

function nextShipToBePlaced() {
  const placed = new Set(state.placementShips.map(s => s.type));
  return SHIP_DEFS.find(d => !placed.has(d.type))?.type || null;
}

function renderMyBoard(g) {
  const boardEl = document.getElementById("my-board"); const cells = makeBoardGrid(boardEl, g.grid_size);
  const myId = state.player.player_id; const inGame = (g.player_ids||[]).includes(myId);
  state.myShips.forEach(s => paintShipOnBoard(cells, s));
  state.placementShips.forEach(s => paintShipOnBoard(cells, s));
  state.moves.filter(m => m.player_id !== myId).forEach(m => {
    if (!cells[m.row]?.[m.col]) return;
    const cell = cells[m.row][m.col]; cell.className = "cell";
    cell.classList.add(m.result==="hit"?"hit":"miss");
  });
  renderShipSelector(g);
  if (inGame && g.status === "placing" && state.myShips.length === 0) {
    cells.forEach(row => row.forEach(cell => {
      if (cell.classList.contains("hit")||cell.classList.contains("miss")) return;
      cell.classList.add("placeable");
      cell.addEventListener("mouseenter", () => showPlacementPreview(cells, +cell.dataset.row, +cell.dataset.col, g.grid_size));
      cell.addEventListener("mouseleave", () => clearPreview(cells));
      cell.addEventListener("click", () => handlePlacementClick(+cell.dataset.row, +cell.dataset.col, g.grid_size, cells));
    }));
  }
}

function paintShipOnBoard(cells, ship) {
  const shipCells = getShipCells(ship.type, ship.startRow, ship.startCol, ship.orientation); const len = shipCells.length;
  shipCells.forEach(([r,c], i) => {
    if (!cells[r]?.[c]) return; const cell = cells[r][c];
    cell.classList.add(`ship-${ship.type}`);
    if (len === 1)        cell.classList.add("ship-single");
    else if (i === 0)     cell.classList.add(ship.orientation==="H"?"ship-head-h":"ship-head-v");
    else if (i === len-1) cell.classList.add(ship.orientation==="H"?"ship-tail-h":"ship-tail-v");
    else                  cell.classList.add(ship.orientation==="H"?"ship-mid":"ship-mid-v");
  });
}

function showPlacementPreview(cells, row, col, gridSize) {
  clearPreview(cells); const type = nextShipToBePlaced(); if (!type) return;
  const valid = isValidPlacement(type, row, col, state.orientation, gridSize, state.placementShips);
  getShipCells(type, row, col, state.orientation).forEach(([r,c]) => {
    if (!cells[r]?.[c]) return; cells[r][c].classList.add("placement-preview"); cells[r][c].style.opacity = valid?"0.8":"0.4";
  });
}

function clearPreview(cells) {
  cells.forEach(row => row.forEach(cell => { cell.classList.remove("placement-preview"); cell.style.opacity = ""; }));
}

function handlePlacementClick(row, col, gridSize, cells) {
  const type = nextShipToBePlaced(); if (!type || state.placementShips.length >= 4) return;
  if (!isValidPlacement(type, row, col, state.orientation, gridSize, state.placementShips)) { toast("Can't place there.", "error"); return; }
  state.placementShips.push({ type, startRow: row, startCol: col, orientation: state.orientation, length: SHIP_DEFS.find(d => d.type===type).length });
  const next = nextShipToBePlaced();
  if (next) { state.selectedShipType = next; toast(`${type.charAt(0).toUpperCase()+type.slice(1)} placed! Now place your ${next}.`, "success"); }
  else { toast("All ships placed! Confirm when ready.", "success"); }
  clearPreview(cells); renderGameView();
}

function renderShipSelector(g) {
  const existing = document.getElementById("ship-selector"); if (existing) existing.remove();
  const myId = state.player.player_id; const inGame = (g.player_ids||[]).includes(myId);
  if (!inGame || g.status !== "placing" || state.myShips.length === 4) return;
  const placedTypes = new Set(state.placementShips.map(s => s.type));
  const boardWrap = document.getElementById("my-board").parentElement;
  const selector = document.createElement("div"); selector.id = "ship-selector"; selector.className = "ship-selector";
  selector.innerHTML = `<div class="ship-selector-title">Fleet</div><div class="ship-tray">${SHIP_DEFS.map(def => {
    const isPlaced = placedTypes.has(def.type); const isSelected = state.selectedShipType === def.type && !isPlaced;
    const blocks = Array.from({length: def.length}, () => `<div class="ship-block ${def.blockClass}"></div>`).join("");
    return `<div class="ship-option ${isSelected?"selected":""} ${isPlaced?"placed":""}" data-type="${def.type}">
      <div class="ship-icon">${blocks}</div>
      <div class="ship-info"><div class="ship-name">${def.label}</div><div class="ship-size">${def.length} cell${def.length>1?"s":""}</div></div>
      ${isPlaced?`<span class="ship-placed-badge">✓ PLACED</span>`:`<button class="rotate-btn" data-type="${def.type}" title="Rotate">↺</button><span class="orientation-badge">${isSelected?state.orientation:"H"}</span>`}
    </div>`;
  }).join("")}</div>`;
  boardWrap.insertBefore(selector, document.getElementById("my-board"));
  selector.querySelectorAll(".ship-option:not(.placed)").forEach(el => {
    el.addEventListener("click", e => { if (e.target.closest(".rotate-btn")) return; state.selectedShipType = el.dataset.type; renderGameView(); });
  });
  selector.querySelectorAll(".rotate-btn").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation(); state.orientation = state.orientation==="H"?"V":"H"; state.selectedShipType = btn.dataset.type;
      renderGameView(); toast(`Rotated to ${state.orientation==="H"?"Horizontal":"Vertical"}`, "info");
    });
  });
}

function renderOpponentBoard(g) {
  const tabsEl = document.getElementById("opp-tabs"); const boardEl = document.getElementById("opp-board");
  const myId = state.player.player_id; const opponents = (g.players||[]).filter(p => p.player_id !== myId);
  if (opponents.length === 0) { tabsEl.innerHTML = ""; boardEl.innerHTML = `<p class="empty">No opponents yet.</p>`; return; }
  if (!state.selectedOpponent || !opponents.find(p => p.player_id === state.selectedOpponent)) state.selectedOpponent = opponents[0].player_id;
  if (opponents.length > 1) {
    tabsEl.innerHTML = opponents.map(p => `<button class="opp-tab ${p.player_id===state.selectedOpponent?"active":""} ${p.ships_remaining===0?"eliminated":""}" data-pid="${p.player_id}">${getUsername(p.player_id)} (${p.ships_remaining})</button>`).join("");
    tabsEl.querySelectorAll("button[data-pid]").forEach(btn => { btn.addEventListener("click", () => { state.selectedOpponent = parseInt(btn.dataset.pid,10); renderGameView(); }); });
  } else { tabsEl.innerHTML = ""; }
  const oppName = getUsername(state.selectedOpponent);
  document.getElementById("opp-title").textContent = opponents.length>1 ? `Targeting ${oppName}` : `${oppName}'s Board`;
  const cells = makeBoardGrid(boardEl, g.grid_size);
  state.moves.filter(m => m.player_id === myId).forEach(m => { if (!cells[m.row]?.[m.col]) return; cells[m.row][m.col].classList.add(m.result==="hit"?"hit":"miss"); });
  if ((g.status === "playing" || g.status === "active") && g.current_turn_player_id === myId) {
    cells.forEach(row => row.forEach(cell => {
      if (cell.classList.contains("hit")||cell.classList.contains("miss")) return;
      cell.classList.add("clickable");
      cell.addEventListener("click", () => handleFire(+cell.dataset.row, +cell.dataset.col));
    }));
  }
}

async function handleFire(row, col) {
  try {
    const result = await api.fire(state.currentGame.id, state.player.player_id, row, col);
    if (result.result === "hit") {
      state.hitStreak += 1;
      let msg = state.hitStreak >= 3 ? `🔥 x${state.hitStreak} STREAK! ON FIRE!` : `🎯 HIT! Streak x${state.hitStreak}`;
      if (result.ship_sunk) msg += ` — ${result.ship_type?result.ship_type.charAt(0).toUpperCase()+result.ship_type.slice(1):"Ship"} SUNK! 💀`;
      toast(msg, "success");
    } else {
      if (state.hitStreak > 0) toast(`Streak broken at x${state.hitStreak}. Miss.`, "info");
      else toast("Splash. Miss.", "info");
      state.hitStreak = 0;
    }
    refreshGame();
  } catch (e) { toast(e.message, "error"); }
}

function makeBoardGrid(boardEl, size) {
  boardEl.style.gridTemplateColumns = `repeat(${size}, 1fr)`; boardEl.style.gridTemplateRows = `repeat(${size}, 1fr)`; boardEl.innerHTML = "";
  const cells = [];
  for (let r = 0; r < size; r++) { cells[r] = []; for (let c = 0; c < size; c++) { const cell = document.createElement("div"); cell.className = "cell"; cell.dataset.row = r; cell.dataset.col = c; boardEl.appendChild(cell); cells[r][c] = cell; } }
  return cells;
}

function renderMoveHistory() {
  const el = document.getElementById("move-history");
  if (!state.moves.length) { el.innerHTML = `<p class="empty">No moves yet.</p>`; return; }
  el.innerHTML = state.moves.slice().reverse().map(m => {
    const isMe = !state.isSpectator && m.player_id === state.player.player_id;
    return `<div class="move-row"><span class="move-num">#${m.move_number}</span><span class="move-player">${isMe?"You":getUsername(m.player_id)}</span><span class="move-coords">(${m.row},${m.col})</span><span class="move-result ${m.result}">${m.result.toUpperCase()}</span></div>`;
  }).join("");
}

function renderPlayersList(g) {
  const el = document.getElementById("players-list");
  el.innerHTML = (g.players||[]).map(p => {
    const isMe = !state.isSpectator && p.player_id === state.player.player_id;
    const isCurrent = g.current_turn_player_id === p.player_id; const eliminated = p.ships_remaining === 0;
    return `<div class="player-row ${isCurrent?"current":""} ${eliminated?"eliminated":""}"><span class="player-name">${isMe?"You":getUsername(p.player_id)}${isCurrent?" 🎯":""}</span><span class="player-ships">${p.ships_remaining} ships</span></div>`;
  }).join("");
}

function renderStreakBanner() {
  const banner = document.getElementById("streak-banner"); if (!banner) return;
  const streak = state.hitStreak; banner.id = "streak-banner";
  if (streak === 0) { banner.className = ""; banner.innerHTML = `<span class="streak-label">Sniper Streak</span>`; return; }
  banner.className = streak >= 3 ? "hot" : "active";
  banner.innerHTML = `<span class="streak-count">${"🎯".repeat(Math.min(streak,5))}</span><span class="streak-label">x${streak} STREAK${streak>=3?" 🔥":""}</span>`;
}

async function pollChat() {
  if (!state.currentGame || state.isSpectator) return;
  try { const msgs = await api.getChat(state.currentGame.id, state.player.player_id); state.chatMessages = msgs; renderChatMessages(); } catch (_) {}
}

function renderChatMessages() {
  const el = document.getElementById("chat-messages");
  if (!state.chatMessages.length) { el.innerHTML = `<p class="empty">No messages yet.</p>`; return; }
  const myId = state.player.player_id;
  el.innerHTML = state.chatMessages.map(m => {
    const isMe = m.player_id === myId;
    const time = new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return `<div class="chat-msg ${isMe?"mine":"theirs"}"><div class="chat-msg-header"><span class="chat-msg-author">${isMe?"You":m.username}</span><span class="chat-msg-time">${time}</span></div><div class="chat-msg-text">${escapeHtml(m.message)}</div></div>`;
  }).join("");
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

async function handleSendChat() {
  const input = document.getElementById("chat-input"); const message = input.value.trim(); if (!message) return;
  input.value = "";
  try { await api.sendChat(state.currentGame.id, state.player.player_id, message); await pollChat(); }
  catch (e) { toast(e.message, "error"); }
}

async function pollRematch() {
  if (!state.currentGame || state.isSpectator) return;
  try {
    const rematch = await api.getRematch(state.currentGame.id, state.player.player_id);
    if (!rematch) return;
    state.rematchId = rematch.id; const myId = state.player.player_id;
    if (rematch.status === "accepted" && state.rematchStatus !== "accepted") {
      state.rematchStatus = "accepted"; showRematchView("accepted");
      setTimeout(() => { document.getElementById("win-modal").classList.add("hidden"); enterGame(rematch.new_game_id); }, 2000);
      return;
    }
    if (rematch.status === "declined" && state.rematchStatus !== "declined") { state.rematchStatus = "declined"; showRematchView("declined"); return; }
    if (rematch.status === "pending") {
      if (rematch.opponent_id === myId && state.rematchStatus !== "incoming") { state.rematchStatus = "incoming"; showRematchView("incoming"); }
      else if (rematch.requester_id === myId && state.rematchStatus !== "pending") { state.rematchStatus = "pending"; showRematchView("pending"); }
    }
  } catch (_) {}
}

function showRematchView(view) {
  ["requester","pending","incoming","declined","accepted"].forEach(v => { const el = document.getElementById(`rematch-${v}-view`); if (el) el.classList.add("hidden"); });
  const target = document.getElementById(`rematch-${view}-view`); if (target) target.classList.remove("hidden");
}

function showPostGameModal(g) {
  const won = g.winner_id === state.player.player_id;
  document.getElementById("win-title").textContent = won ? "🏆 Victory!" : "💀 Defeated";
  document.getElementById("win-text").textContent  = won ? `You sunk every ship. Game #${g.id} is yours.` : `${getUsername(g.winner_id)} wins Game #${g.id}. Better luck next time.`;
  const p = state.player;
  const gameShots = Math.max(0,(p.total_shots||0)-state.gameStartShots); const gameHits = Math.max(0,(p.total_hits||0)-state.gameStartHits);
  const gameMisses = Math.max(0,gameShots-gameHits); const gameAcc = gameShots>0?Math.round((gameHits/gameShots)*100):0;
  document.getElementById("postgame-this-game").innerHTML = statGrid([{val:gameShots,label:"Shots"},{val:gameHits,label:"Hits"},{val:gameMisses,label:"Misses"},{val:`${gameAcc}%`,label:"Accuracy"}]);
  const lifeAcc = p.total_shots?Math.round((p.total_hits/p.total_shots)*100):0;
  document.getElementById("postgame-lifetime").innerHTML = statGrid([{val:p.wins||0,label:"Wins"},{val:p.losses||0,label:"Losses"},{val:p.total_shots||0,label:"Shots"},{val:`${lifeAcc}%`,label:"Accuracy"}]);
  showRematchView("requester"); state.rematchStatus = null;
  document.getElementById("win-modal").classList.remove("hidden");
}

function statGrid(items) {
  return items.map(i => `<div class="stat-item"><span class="stat-val">${i.val}</span><span class="stat-label">${i.label}</span></div>`).join("");
}

async function showLeaderboard() {
  const modal = document.getElementById("leaderboard-modal"); const body = document.getElementById("leaderboard-body");
  modal.classList.remove("hidden"); body.innerHTML = `<p class="empty">Loading...</p>`;
  try {
    const players = await api.getLeaderboard();
    if (!players.length) { body.innerHTML = `<p class="empty">No players yet.</p>`; return; }
    body.innerHTML = players.slice(0,5).map((p,i) => {
      const rank = i+1; const podium = rank<=3?`podium-${rank}`:""; const acc = p.total_shots?Math.round((p.total_hits/p.total_shots)*100):0;
      const medal = rank===1?"🥇":rank===2?"🥈":rank===3?"🥉":"";
      return `<div class="lb-row ${podium}" data-pid="${p.player_id}"><span class="lb-rank">${medal||`#${rank}`}</span><span class="lb-name">${p.username}</span><span class="lb-stat">${p.wins}W</span><span class="lb-stat">${p.losses}L</span><span class="lb-stat">${acc}%</span></div>`;
    }).join("");
    body.querySelectorAll(".lb-row[data-pid]").forEach(row => { row.addEventListener("click", () => showProfile(parseInt(row.dataset.pid,10))); });
  } catch (e) { body.innerHTML = `<p class="empty">Could not load.</p>`; }
}

async function showProfile(playerId) {
  document.getElementById("leaderboard-modal").classList.add("hidden");
  const modal = document.getElementById("profile-modal"); const body = document.getElementById("profile-body");
  modal.classList.remove("hidden"); body.innerHTML = `<p class="empty">Loading...</p>`;
  try {
    const p = await api.getPlayer(playerId); const acc = p.total_shots?Math.round((p.total_hits/p.total_shots)*100):0;
    const winRate = p.games_played?Math.round((p.wins/p.games_played)*100):0;
    document.getElementById("profile-username").textContent = p.username;
    body.innerHTML = `
      <div class="profile-stats-grid">
        <div class="profile-stat"><span class="stat-val">${p.wins||0}</span><span class="stat-label">Wins</span></div>
        <div class="profile-stat"><span class="stat-val">${p.losses||0}</span><span class="stat-label">Losses</span></div>
        <div class="profile-stat"><span class="stat-val">${p.games_played||0}</span><span class="stat-label">Games</span></div>
        <div class="profile-stat"><span class="stat-val">${p.total_shots||0}</span><span class="stat-label">Shots</span></div>
        <div class="profile-stat"><span class="stat-val">${p.total_hits||0}</span><span class="stat-label">Hits</span></div>
        <div class="profile-stat"><span class="stat-val">${acc}%</span><span class="stat-label">Accuracy</span></div>
      </div>
      <div class="profile-winbar">
        <div class="profile-winbar-label"><span>Win Rate</span><span>${winRate}%</span></div>
        <div class="profile-winbar-track"><div class="profile-winbar-fill" style="width:${winRate}%"></div></div>
      </div>`;
  } catch (e) { body.innerHTML = `<p class="empty">Could not load profile.</p>`; }
}

document.addEventListener("DOMContentLoaded", () => {
  loadTheme();
  updateServerStatusDisplay();

  // Server switcher: collapsed -> expanded
  document.getElementById("btn-show-server-switcher")?.addEventListener("click", showServerSwitcher);
  document.getElementById("btn-hide-server-switcher")?.addEventListener("click", hideServerSwitcher);
  document.getElementById("btn-reset-server")?.addEventListener("click", resetToHomeServer);

  // Server URL submit
  const submitServer = () => setServer(document.getElementById("server-input-login").value);
  document.getElementById("btn-server-login")?.addEventListener("click", submitServer);
  document.getElementById("server-input-login")?.addEventListener("keydown", e => {
    if (e.key === "Enter") submitServer();
  });

  document.querySelectorAll(".btn-theme").forEach(btn => btn.addEventListener("click", toggleTheme));
  document.getElementById("btn-login").addEventListener("click", handleLogin);
  document.getElementById("username-input").addEventListener("keydown", e => { if (e.key === "Enter") handleLogin(); });
  document.getElementById("btn-logout").addEventListener("click", handleLogout);
  document.getElementById("btn-leaderboard").addEventListener("click", showLeaderboard);
  document.getElementById("btn-close-lb").addEventListener("click", () => document.getElementById("leaderboard-modal").classList.add("hidden"));
  document.getElementById("btn-close-profile").addEventListener("click", () => document.getElementById("profile-modal").classList.add("hidden"));
  document.getElementById("btn-refresh").addEventListener("click", refreshLobby);
  document.getElementById("btn-create").addEventListener("click", handleCreateGame);
  document.getElementById("btn-back").addEventListener("click", () => {
    state.currentGame = null; state.hitStreak = 0; state.isSpectator = false;
    document.getElementById("spectator-banner").classList.add("hidden");
    document.getElementById("chat-panel").classList.add("hidden");
    showView("lobby");
  });

  // Win modal — both X and Back to Lobby do the same thing
  document.getElementById("btn-win-close").addEventListener("click", closeWinModal);
  document.getElementById("btn-win-x").addEventListener("click", closeWinModal);

  // Chat
  document.getElementById("btn-chat-send").addEventListener("click", handleSendChat);
  document.getElementById("chat-input").addEventListener("keydown", e => { if (e.key === "Enter") handleSendChat(); });

  // Rematch
  document.getElementById("btn-rematch-request").addEventListener("click", async () => {
    try {
      const r = await api.requestRematch(state.currentGame.id, state.player.player_id);
      state.rematchId = r.id; state.rematchStatus = "pending"; showRematchView("pending");
    } catch (e) { toast(e.message, "error"); }
  });
  document.getElementById("btn-rematch-accept").addEventListener("click", async () => {
    if (!state.rematchId) return;
    try {
      const r = await api.respondRematch(state.rematchId, state.player.player_id, "accept");
      state.rematchStatus = "accepted"; showRematchView("accepted");
      setTimeout(() => { document.getElementById("win-modal").classList.add("hidden"); enterGame(r.new_game_id); }, 2000);
    } catch (e) { toast(e.message, "error"); }
  });
  document.getElementById("btn-rematch-decline").addEventListener("click", async () => {
    if (!state.rematchId) return;
    try { await api.respondRematch(state.rematchId, state.player.player_id, "decline"); state.rematchStatus = "declined"; showRematchView("declined"); }
    catch (e) { toast(e.message, "error"); }
  });

  if (!tryAutoLogin()) showView("login");
});