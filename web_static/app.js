const SEATS = ["UTG", "HJ", "CO", "BTN", "SB", "BB"];
const EFFECTIVE_STACK_BB = 100;

const state = {
  history: [],
  studyPosition: "UTG",
  studyData: null,
  selectedHand: null,
  strategyProfile: null,
  trainerQuestion: null,
  loadingCount: 0,
  analysisRequestId: 0,
  analysisPending: false,
};

const el = (id) => document.getElementById(id);

function showLoading(message = "Calculating range and EV...") {
  state.loadingCount += 1;
  const overlay = el("loading-overlay");
  const messageNode = el("loading-message");
  if (messageNode) {
    messageNode.textContent = message;
  }
  if (overlay) {
    overlay.classList.remove("hidden");
  }
}

function hideLoading() {
  state.loadingCount = Math.max(0, state.loadingCount - 1);
  const overlay = el("loading-overlay");
  if (overlay && state.loadingCount === 0) {
    overlay.classList.add("hidden");
  }
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatRaiseOptions(options) {
  if (!options || options.length === 0) return "-";
  return options
    .map((option) => `${formatNumber(option.amount, 1)}: ${formatNumber(option.frequency, 1)}% / ${formatNumber(option.ev, 2)}`)
    .join(" | ");
}

function countRaises() {
  return state.history.filter((record) => record.action === "raise").length;
}

function deriveClientPreflopState(history = state.history) {
  const contributions = Object.fromEntries(SEATS.map((seat) => [seat, 0]));
  contributions.SB = 0.5;
  contributions.BB = 1.0;
  const folded = new Set();
  let acted = new Set();
  let currentBet = 1.0;
  let lastRaiseIncrement = 1.0;
  let lastActor = null;

  history.forEach((record) => {
    const seat = record.position;
    if (!SEATS.includes(seat) || folded.has(seat)) return;
    if (record.action === "fold") {
      folded.add(seat);
      acted.add(seat);
      lastActor = seat;
      return;
    }
    if (record.action === "check") {
      acted.add(seat);
      lastActor = seat;
      return;
    }
    if (record.action === "call") {
      const toCall = Math.max(0, currentBet - contributions[seat]);
      contributions[seat] += Math.min(toCall, EFFECTIVE_STACK_BB - contributions[seat]);
      acted.add(seat);
      lastActor = seat;
      return;
    }
    if (record.action === "raise") {
      const newTotal = Math.min(Number(record.amount || 0), EFFECTIVE_STACK_BB);
      if (newTotal <= currentBet) return;
      const raiseIncrement = Math.max(0, newTotal - currentBet);
      contributions[seat] = newTotal;
      currentBet = newTotal;
      if (raiseIncrement > 0) {
        lastRaiseIncrement = raiseIncrement;
      }
      acted = new Set([seat]);
      lastActor = seat;
    }
  });

  const nextToAct = nextClientPositionToAct(folded, contributions, currentBet, acted, lastActor);
  return {
    contributions,
    folded,
    acted,
    currentBet,
    lastRaiseIncrement,
    lastActor,
    nextToAct,
    minRaiseTotal: Math.min(EFFECTIVE_STACK_BB, currentBet + Math.max(1.0, lastRaiseIncrement)),
  };
}

function clientBettingClosed(folded, contributions, currentBet, acted) {
  const activeSeats = SEATS.filter((seat) => !folded.has(seat));
  if (activeSeats.length <= 1) return true;
  return activeSeats.every((seat) => (
    contributions[seat] >= EFFECTIVE_STACK_BB
    || (contributions[seat] >= currentBet && acted.has(seat))
  ));
}

function nextClientPositionToAct(folded, contributions, currentBet, acted, afterPosition = null) {
  if (clientBettingClosed(folded, contributions, currentBet, acted)) return null;
  const startIndex = afterPosition ? (SEATS.indexOf(afterPosition) + 1) % SEATS.length : 0;
  for (let offset = 0; offset < SEATS.length; offset += 1) {
    const seat = SEATS[(startIndex + offset) % SEATS.length];
    if (folded.has(seat)) continue;
    if (contributions[seat] >= EFFECTIVE_STACK_BB) continue;
    if (contributions[seat] < currentBet || !acted.has(seat)) {
      return seat;
    }
  }
  return null;
}

function currentStudyPosition() {
  return state.studyPosition || state.studyData?.betting_state?.next_to_act || "UTG";
}

function setStudyPosition(position) {
  state.studyPosition = position;
  const positionInput = el("hero-position");
  if (positionInput) {
    positionInput.value = position;
  }
}

function autoRaiseAmount(seat, action = "raise") {
  const bettingState = state.studyData?.betting_state;
  const currentBet = Number(bettingState?.current_bet_bb || 1);
  const raiseCount = countRaises();
  const oop = isPostflopOop(seat);
  if (action === "all-in") {
    return Number(bettingState?.max_raise_total_bb || 100);
  }
  if (raiseCount === 0) {
    return seat === "SB" ? 3.5 : 2.5;
  }
  if (raiseCount === 1) {
    const multiplier = oop ? 4.0 : 3.0;
    return Math.min(100, Math.max(currentBet + 1, currentBet * multiplier));
  }
  if (raiseCount === 2) {
    const multiplier = oop ? 2.65 : 2.35;
    return Math.min(100, Math.max(currentBet + 1, currentBet * multiplier));
  }
  const multiplier = oop ? 2.35 : 2.15;
  return Math.min(100, Math.max(currentBet + 1, currentBet * multiplier));
}

function isPostflopOop(seat) {
  const postflopOrder = { SB: 0, BB: 1, UTG: 2, HJ: 3, CO: 4, BTN: 5 };
  const folded = new Set(
    state.history
      .filter((record) => record.action === "fold")
      .map((record) => record.position)
  );
  const activeOpponents = state.history
    .filter((record) => record.position !== seat && !folded.has(record.position))
    .filter((record) => ["call", "raise", "check"].includes(record.action))
    .map((record) => record.position);
  if (activeOpponents.length === 0) {
    return seat === "SB" || seat === "BB";
  }
  const heroOrder = postflopOrder[seat] ?? 0;
  return [...new Set(activeOpponents)].some((position) => heroOrder < (postflopOrder[position] ?? 0));
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function setMode(mode) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  el("study-view").classList.toggle("hidden", mode !== "study");
  el("trainer-view").classList.toggle("hidden", mode !== "trainer");
}

function updateTrainerControls() {
  const street = el("trainer-street").value;
  el("preflop-mode-label").classList.toggle("hidden", street !== "preflop");
  el("flop-mode-label").classList.toggle("hidden", street !== "flop");
}

function renderHistory() {
  const list = el("history-list");
  list.innerHTML = "";
  if (state.history.length === 0) {
    const item = document.createElement("li");
    item.className = "empty-history";
    item.textContent = "Root node";
    list.appendChild(item);
  }
  state.history.forEach((record, index) => {
    const item = document.createElement("li");
    item.textContent = `${record.position} ${record.action} ${formatNumber(record.amount, 1)} BB`;
    const remove = document.createElement("button");
    remove.className = "icon-button";
    remove.title = "Remove action";
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      state.history.splice(index, 1);
      setStudyPosition(inferNextSeatAfterHistory());
      state.studyData = null;
      state.analysisPending = true;
      renderHistory();
      analyze();
    });
    item.append(" ", remove);
    list.appendChild(item);
  });
  renderTableState();
}

function buildStudyPayload() {
  const studyPosition = currentStudyPosition();
  setStudyPosition(studyPosition);
  const autoState = el("auto-state").checked;
  const candidateRaiseAmounts = el("raise-sizes").value
    .split(",")
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0);
  return {
    hero_position: studyPosition,
    hero_hand: el("hero-hand").value,
    street: el("street").value,
    board_cards: el("board-cards").value,
    pot_bb: Number(el("pot-bb").value),
    call_amount_bb: Number(el("call-bb").value),
    raise_amount_bb: autoState ? 0 : Number(el("raise-bb").value),
    candidate_raise_amounts: autoState ? [] : candidateRaiseAmounts,
    simulations: Number(el("simulations").value),
    action_history: state.history,
    active_opponent_count: Number(el("opponents").value),
    auto_state: autoState,
  };
}

async function analyze() {
  const requestId = ++state.analysisRequestId;
  state.analysisPending = true;
  renderStudyPending();
  el("status-line").textContent = "Analyzing...";
  showLoading("Calculating range matrix and EV...");
  try {
    const data = await postJson("/api/study", buildStudyPayload());
    if (requestId !== state.analysisRequestId) {
      return;
    }
    state.studyData = data;
    state.analysisPending = false;
    setStudyPosition(data.betting_state?.next_to_act || data.hero_position || currentStudyPosition());
    state.selectedHand = data.range_grid.find((item) => item.is_selected) || data.range_grid[0];
    renderStudy(data);
    el("status-line").textContent = `Loaded ${data.range_grid.length} hand classes with ${data.range_simulations} range sims each against ${data.opponent_ranges.length} opponent ranges.`;
  } catch (error) {
    if (requestId === state.analysisRequestId) {
      state.analysisPending = false;
      el("status-line").textContent = error.message;
      renderTableState();
    }
  } finally {
    hideLoading();
  }
}

function renderStudyPending() {
  renderRangeSummary([]);
  el("range-grid").innerHTML = `<div class="range-pending">Solving range matrix...</div>`;
  el("detail-hand").textContent = "Solving...";
  el("detail-stats").innerHTML = `
    <dt>Status</dt><dd>Calculating</dd>
    <dt>Viewing</dt><dd>${currentStudyPosition()}</dd>
  `;
  el("hands-table").innerHTML = `<tr><td colspan="13">Calculating hand list...</td></tr>`;
  el("opponent-summary").textContent = "Solving ranges";
  el("opponent-ranges").innerHTML = `<p class="status-line">Inferring opponent ranges...</p>`;
  renderTableState();
}

function renderStudy(data) {
  if (data.auto_state && data.betting_state) {
    el("pot-bb").value = formatNumber(data.betting_state.pot_bb, 1);
    el("call-bb").value = formatNumber(data.betting_state.call_amount_bb, 1);
    el("opponents").value = data.betting_state.active_opponent_count;
  }
  el("street").value = data.street || el("street").value;
  el("board-cards").value = data.board_cards || "";
  if (data.candidate_raise_amounts?.length) {
    el("raise-sizes").value = data.candidate_raise_amounts.map((amount) => formatNumber(amount, 1)).join(", ");
  }
  const errors = data.betting_state?.validation_errors || [];
  if (errors.length > 0) {
    el("status-line").textContent = errors.join("; ");
  }
  renderRangeSummary(data.range_grid);
  renderRangeGrid(data.range_grid);
  renderDetail(state.selectedHand);
  renderHandsTable(data.range_grid);
  renderOpponentRanges(data.opponent_ranges || []);
  renderTableState();
}

function renderOpponentRanges(ranges) {
  el("opponent-summary").textContent = `${ranges.length} active ranges`;
  const container = el("opponent-ranges");
  if (ranges.length === 0) {
    container.innerHTML = `<p class="status-line">No active opponent ranges inferred for this node.</p>`;
    return;
  }
  container.innerHTML = ranges
    .map((range) => `
      <article class="opponent-card">
        <h3>${range.position}</h3>
        <dl>
          <dt>Source</dt><dd>${range.source}</dd>
          <dt>Profile</dt><dd>${range.profile_key}</dd>
          <dt>Continue</dt><dd>${formatNumber(range.continue_fraction * 100, 1)}%</dd>
          <dt>Candidates</dt><dd>${range.candidate_count}</dd>
          <dt>Weight</dt><dd>${formatNumber(range.total_weight, 1)}</dd>
        </dl>
      </article>
    `)
    .join("");
}

function handComboCount(hand) {
  if (!hand || hand.length < 2) return 1;
  if (hand[0] === hand[1]) return 6;
  if (hand.endsWith("s")) return 4;
  if (hand.endsWith("o")) return 12;
  return 1;
}

function rangeActionSummary(items) {
  const totals = {
    fold: 0,
    call: 0,
    raise: 0,
    allin: 0,
    combos: 0,
  };
  items.forEach((item) => {
    const combos = handComboCount(item.hand);
    const frequencies = rangeActionFrequencies(item);
    totals.fold += frequencies.fold * combos;
    totals.call += frequencies.call * combos;
    totals.raise += frequencies.raise * combos;
    totals.allin += frequencies.allin * combos;
    totals.combos += combos;
  });
  const divisor = Math.max(1, totals.combos);
  return {
    fold: totals.fold / divisor,
    call: totals.call / divisor,
    raise: totals.raise / divisor,
    allin: totals.allin / divisor,
    combos: totals.combos,
  };
}

function renderRangeSummary(items) {
  const summary = rangeActionSummary(items);
  el("summary-position").textContent = currentStudyPosition();
  el("summary-fold").textContent = `${formatNumber(summary.fold, 1)}%`;
  el("summary-call").textContent = `${formatNumber(summary.call, 1)}%`;
  el("summary-raise").textContent = `${formatNumber(summary.raise, 1)}%`;
  el("summary-allin").textContent = `${formatNumber(summary.allin, 1)}%`;
}

async function loadStrategyProfile() {
  try {
    const profile = await getJson("/api/strategy-profiles");
    state.strategyProfile = profile;
    renderStrategyProfile(profile);
    el("profile-status").textContent = "Loaded";
  } catch (error) {
    el("profile-status").textContent = error.message;
  }
}

function renderStrategyProfile(profile) {
  el("profile-large-raise").value = formatNumber(profile.raise_size_thresholds.large_raise_total_bb, 1);
  el("profile-all-in").value = formatNumber(profile.raise_size_thresholds.all_in_total_bb, 1);
  const keys = ["unacted", "check", "call", "raise", "large_raise", "all_in"];
  const labels = {
    unacted: "Open",
    check: "Check",
    call: "Call",
    raise: "Raise",
    large_raise: "Large",
    all_in: "All-in",
  };
  const rows = Object.entries(profile.positions)
    .map(([position, fractions]) => `
      <article class="profile-row" data-profile-position="${position}">
        <h4>${position}</h4>
        ${keys.map((key) => `
          <label>${labels[key]}
            <input
              data-profile-key="${key}"
              type="number"
              min="0.01"
              max="1"
              step="0.01"
              value="${formatNumber(fractions[key], 2)}"
            >
          </label>
        `).join("")}
      </article>
    `)
    .join("");
  el("strategy-profile-grid").innerHTML = rows;
}

function buildStrategyProfilePayload() {
  const keys = ["unacted", "check", "call", "raise", "large_raise", "all_in"];
  const defaultProfile = state.strategyProfile?.default || {};
  const positions = {};
  document.querySelectorAll(".profile-row").forEach((row) => {
    const position = row.dataset.profilePosition;
    positions[position] = {};
    keys.forEach((key) => {
      const input = row.querySelector(`[data-profile-key="${key}"]`);
      positions[position][key] = Number(input.value);
    });
  });
  return {
    default: defaultProfile,
    positions: positions,
    raise_size_thresholds: {
      large_raise_total_bb: Number(el("profile-large-raise").value),
      all_in_total_bb: Number(el("profile-all-in").value),
    },
  };
}

async function saveStrategyProfile() {
  el("profile-status").textContent = "Saving...";
  showLoading("Saving strategy profile...");
  try {
    const profile = await postJson("/api/strategy-profiles", buildStrategyProfilePayload());
    state.strategyProfile = profile;
    renderStrategyProfile(profile);
    el("profile-status").textContent = "Saved";
    analyze();
  } catch (error) {
    el("profile-status").textContent = error.message;
  } finally {
    hideLoading();
  }
}

function renderTableState() {
  const studyPosition = currentStudyPosition();
  const street = el("street").value;
  const boardCards = el("board-cards").value.trim();
  const bettingState = state.studyData?.betting_state;
  const pending = state.analysisPending;
  const isClosed = Boolean(bettingState?.is_closed);
  const latestBySeat = {};
  state.history.forEach((record) => {
    latestBySeat[record.position] = record;
  });
  SEATS.forEach((seat) => {
    const seatNode = document.querySelector(`.seat[data-seat="${seat}"]`);
    const stateLabel = el(`seat-state-${seat}`);
    const record = latestBySeat[seat];
    const seatState = bettingState?.seats?.[seat];
    seatNode.classList.remove("hero-seat", "study-seat", "seat-state-fold", "seat-state-call", "seat-state-raise", "seat-state-check", "seat-can-act", "seat-disabled");
    seatNode.classList.toggle("seat-disabled", pending || isClosed || (Boolean(bettingState) && !seatState?.can_act));
    if (seat === studyPosition) {
      seatNode.classList.add("study-seat");
    }
    if (seatState?.can_act) {
      seatNode.classList.add("seat-can-act");
      stateLabel.textContent = seatState.to_call > 0
        ? `to call ${formatNumber(seatState.to_call, 1)}`
        : "to act";
    } else if (record) {
      seatNode.classList.add(`seat-state-${record.action}`);
      stateLabel.textContent = `${record.action} ${formatNumber(record.amount, 1)} BB`;
    } else if (seat === studyPosition) {
      stateLabel.textContent = "Viewing";
    } else if (seat === "SB") {
      stateLabel.textContent = "0.5 BB";
    } else if (seat === "BB") {
      stateLabel.textContent = "1.0 BB";
    } else {
      stateLabel.textContent = "empty";
    }
    renderSeatActions(seat, seatState, pending || isClosed);
  });
  el("table-pot").textContent = `${formatNumber(el("pot-bb").value, 1)} BB`;
  el("table-board").textContent = boardCards ? `${street} ${boardCards}` : `${street} board -`;
  const nextToAct = state.studyData?.betting_state?.next_to_act;
  const minRaise = state.studyData?.betting_state?.min_raise_total_bb;
  const maxRaise = state.studyData?.betting_state?.max_raise_total_bb;
  const suggestedSizes = state.studyData?.candidate_raise_amounts || [];
  el("node-status").textContent = pending ? "Solving" : isClosed ? "Node closed" : "Open node";
  el("node-status").classList.toggle("closed", pending || isClosed);
  document.querySelector(".poker-table").classList.toggle("closed-node", pending || isClosed);
  el("table-hero").textContent = pending
    ? `Viewing ${studyPosition} | Solving...`
    : isClosed
    ? `Viewing ${studyPosition} | Analysis locked`
    : nextToAct
    ? `Viewing ${studyPosition} | Next ${nextToAct}`
    : `Viewing ${studyPosition}`;
  el("table-sizing").textContent = isClosed
    ? "Preflop betting round complete"
    : suggestedSizes.length
    ? `Suggested raise ${suggestedSizes.map((amount) => formatNumber(amount, 1)).join(" / ")}`
    : minRaise
    ? `Min raise ${formatNumber(minRaise, 1)} | All-in ${formatNumber(maxRaise, 0)}`
    : "Betting closed";
  syncLegalActionButtons();
}

function renderSeatActions(seat, seatState, isClosed) {
  const container = el(`seat-actions-${seat}`);
  container.innerHTML = "";
  if (isClosed || !seatState?.can_act) {
    return;
  }
  const actions = seatState.available_actions || [];
  actions.forEach((action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `seat-line-action action-${action}`;
    button.dataset.seat = seat;
    button.dataset.action = action;
    button.textContent = seatActionLabel(action, seatState);
    container.appendChild(button);
  });
  if (actions.includes("raise")) {
    const allIn = document.createElement("button");
    allIn.type = "button";
    allIn.className = "seat-line-action action-all-in";
    allIn.dataset.seat = seat;
    allIn.dataset.action = "all-in";
    allIn.textContent = "All-in 100";
    container.appendChild(allIn);
  }
}

function seatActionLabel(action, seatState) {
  if (action === "fold") return "Fold";
  if (action === "check") return "Check";
  if (action === "call") return `Call ${formatNumber(seatState?.to_call || 0, 1)}`;
  if (action === "raise") return `Raise ${formatNumber(autoRaiseAmount(seatState?.position || "UTG", action), 1)}`;
  return action;
}

function appendSeatAction(seat, action) {
  const seatState = state.studyData?.betting_state?.seats?.[seat];
  if (seatState && !seatState.can_act) {
    return;
  }
  const normalizedAction = action === "all-in" ? "raise" : action;
  const amount = normalizedAction === "call"
    ? Number(seatState?.to_call || 0)
    : normalizedAction === "raise"
    ? autoRaiseAmount(seat, action)
    : 0;
  state.history.push({
    position: seat,
    action: normalizedAction,
    amount: amount,
  });
  setStudyPosition(inferNextSeatAfterHistory());
  state.studyData = null;
  state.analysisPending = true;
  renderHistory();
  analyze();
}

function syncLegalActionButtons() {
}

function buildOpenHistoryToSeat(seat) {
  const index = SEATS.indexOf(seat);
  if (index <= 0) return [];
  return SEATS.slice(0, index).map((position) => ({
    position: position,
    action: "fold",
    amount: 0,
  }));
}

function buildHistoryToSeatDecision(seat) {
  const existingSeatActionIndex = state.history.findIndex((record) => record.position === seat);
  if (existingSeatActionIndex >= 0) {
    return state.history.slice(0, existingSeatActionIndex);
  }

  const targetIndex = SEATS.indexOf(seat);
  if (targetIndex <= 0) return [];

  const firstActionBySeat = new Map();
  state.history.forEach((record) => {
    if (!firstActionBySeat.has(record.position)) {
      firstActionBySeat.set(record.position, record);
    }
  });

  return SEATS.slice(0, targetIndex).map((position) => (
    firstActionBySeat.get(position) || {
      position: position,
      action: "fold",
      amount: 0,
    }
  ));
}

function inferNextSeatAfterHistory() {
  const nextToAct = deriveClientPreflopState().nextToAct;
  return nextToAct || currentStudyPosition();
}

function selectStudySeat(seat) {
  const currentNextToAct = state.studyData?.betting_state?.next_to_act;
  const hasOpenHistory = state.history.length > 0;
  const viewNode = state.studyData?.betting_state?.view_nodes?.[seat];
  setStudyPosition(seat);
  if (viewNode) {
    state.history = viewNode;
  } else if (!hasOpenHistory || seat !== currentNextToAct) {
    state.history = buildHistoryToSeatDecision(seat);
  }
  state.studyData = null;
  state.analysisPending = true;
  renderHistory();
  analyze();
}

function renderRangeGrid(items) {
  const grid = el("range-grid");
  grid.innerHTML = "";
  items.forEach((item) => {
    const cell = document.createElement("button");
    const frequencies = rangeActionFrequencies(item);
    cell.className = "hand-cell";
    cell.classList.toggle("selected", item.is_selected);
    cell.dataset.hand = item.hand;
    cell.style.setProperty("--fold-pct", `${frequencies.fold}%`);
    cell.style.setProperty("--call-pct", `${frequencies.fold + frequencies.call}%`);
    cell.style.setProperty("--raise-pct", `${frequencies.fold + frequencies.call + frequencies.raise}%`);
    cell.style.setProperty("--allin-pct", `${frequencies.fold + frequencies.call + frequencies.raise + frequencies.allin}%`);
    cell.innerHTML = `
      <span class="hand-name">${item.hand}</span>
      <span class="freq-strip" aria-hidden="true">
        <span class="freq-segment fold" style="width:${frequencies.fold}%"></span>
        <span class="freq-segment call" style="width:${frequencies.call}%"></span>
        <span class="freq-segment raise" style="width:${frequencies.raise}%"></span>
        <span class="freq-segment all-in" style="width:${frequencies.allin}%"></span>
      </span>
      <span class="hand-meta">AI ${formatNumber(frequencies.allin, 0)} R ${formatNumber(frequencies.raise, 0)} C ${formatNumber(frequencies.call, 0)} F ${formatNumber(frequencies.fold, 0)}</span>
    `;
    cell.addEventListener("click", () => {
      state.selectedHand = item;
      document.querySelectorAll(".hand-cell").forEach((node) => {
        node.classList.toggle("selected", node.dataset.hand === item.hand);
      });
      renderDetail(item);
    });
    grid.appendChild(cell);
  });
}

function rangeActionFrequencies(item) {
  const fold = Number(item.actions.Fold || 0);
  const call = Number(item.actions.Call || item.actions.Check || 0);
  const raise = Number(item.actions.Raise || 0);
  const allin = Number(item.actions["All-in"] || 0);
  const total = Math.max(1, fold + call + raise + allin);
  return {
    fold: fold / total * 100,
    call: call / total * 100,
    raise: raise / total * 100,
    allin: allin / total * 100,
  };
}

function renderDetail(item) {
  if (!item) return;
  el("detail-hand").textContent = item.hand;
  const rows = [
    ["Recommended", item.recommended],
    ["Frequency", `${formatNumber(item.frequency, 1)}%`],
    ["EV", formatNumber(item.ev, 3)],
    ["Equity", `${formatNumber(item.equity, 1)}%`],
    ["Representative", item.representative_hand || item.hand],
    ["Fold", `${formatNumber(item.actions.Fold || 0, 1)}%`],
    ["EV Fold", formatNumber(item.evs.Fold, 3)],
    ["Call", `${formatNumber(item.actions.Call || item.actions.Check || 0, 1)}%`],
    ["EV Call/Check", formatNumber(item.evs.Call ?? item.evs.Check, 3)],
    ["Raise", `${formatNumber(item.actions.Raise || 0, 1)}%`],
    ["EV Raise", formatNumber(item.evs.Raise, 3)],
    ["All-in", `${formatNumber(item.actions["All-in"] || 0, 1)}%`],
    ["EV All-in", formatNumber(item.evs["All-in"], 3)],
    ["Raise Sizes", formatRaiseOptions(item.raise_options)],
  ];
  el("detail-stats").innerHTML = rows
    .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
    .join("");
}

function renderHandsTable(items) {
  const filter = el("hand-filter").value.trim().toLowerCase();
  const tbody = el("hands-table");
  tbody.innerHTML = "";
  items
    .filter((item) => {
      if (!filter) return true;
      return `${item.hand} ${item.recommended} ${item.ev}`.toLowerCase().includes(filter);
    })
    .forEach((item) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${item.hand}</td>
        <td>${item.recommended}</td>
        <td>${formatNumber(item.frequency, 1)}%</td>
        <td>${formatNumber(item.ev, 3)}</td>
        <td>${formatNumber(item.actions.Fold || 0, 1)}%</td>
        <td>${formatNumber(item.evs.Fold, 3)}</td>
        <td>${formatNumber(item.actions.Call || item.actions.Check || 0, 1)}%</td>
        <td>${formatNumber(item.evs.Call ?? item.evs.Check, 3)}</td>
        <td>${formatNumber(item.actions.Raise || 0, 1)}%</td>
        <td>${formatNumber(item.evs.Raise, 3)}</td>
        <td>${formatNumber(item.actions["All-in"] || 0, 1)}%</td>
        <td>${formatNumber(item.evs["All-in"], 3)}</td>
        <td>${formatRaiseOptions(item.raise_options)}</td>
      `;
      tbody.appendChild(row);
    });
}

async function loadTrainerQuestion() {
  el("trainer-status").textContent = "Loading question...";
  showLoading("Generating trainer question...");
  try {
    const street = el("trainer-street").value;
    const endpoint = street === "flop" ? "/api/flop-trainer/question" : "/api/trainer/question";
    const payload = street === "flop" ? {
      simulations: Number(el("trainer-simulations").value),
      pot_type: el("flop-trainer-mode").value,
    } : {
      simulations: Number(el("trainer-simulations").value),
      scenario_type: el("trainer-mode").value,
    };
    const question = await postJson(endpoint, payload);
    state.trainerQuestion = question;
    renderTrainerQuestion(question);
    el("trainer-status").textContent = question.question_id;
  } catch (error) {
    el("trainer-status").textContent = error.message;
  } finally {
    hideLoading();
  }
}

function splitCardText(cardsText) {
  const compact = String(cardsText || "").replace(/[\s,|]/g, "");
  const cards = [];
  for (let index = 0; index + 1 < compact.length; index += 2) {
    cards.push(compact.slice(index, index + 2));
  }
  return cards;
}

function cardSuitMeta(card) {
  const suit = String(card || "").slice(-1).toLowerCase();
  return {
    c: { className: "suit-club", symbol: "♣" },
    d: { className: "suit-diamond", symbol: "♦" },
    h: { className: "suit-heart", symbol: "♥" },
    s: { className: "suit-spade", symbol: "♠" },
  }[suit] || { className: "suit-unknown", symbol: "" };
}

function renderCardTiles(container, cards) {
  container.innerHTML = "";
  if (!cards || cards.length === 0) {
    container.innerHTML = `<div class="trainer-card-empty">No cards</div>`;
    return;
  }
  cards.forEach((card) => {
    const meta = cardSuitMeta(card);
    const tile = document.createElement("div");
    tile.className = `trainer-card-tile ${meta.className}`;
    tile.innerHTML = `
      <strong>${escapeHtml(String(card).slice(0, -1).toUpperCase())}</strong>
      <span>${meta.symbol}</span>
    `;
    container.appendChild(tile);
  });
}

function actionDisplay(record) {
  if (!record) {
    return { action: "waiting", detail: "" };
  }
  const action = String(record.action || "").toLowerCase();
  const amount = Number(record.amount || 0);
  if (action === "fold") return { action: "fold", detail: "" };
  if (action === "check") return { action: "check", detail: "" };
  if (action === "call") return { action: "call", detail: `${formatNumber(amount, 1)} BB` };
  if (action === "raise" && amount >= EFFECTIVE_STACK_BB - 1) return { action: "all-in", detail: `${formatNumber(amount, 0)} BB` };
  if (action === "raise") return { action: "raise", detail: `${formatNumber(amount, 1)} BB` };
  return { action: action || "waiting", detail: amount ? `${formatNumber(amount, 1)} BB` : "" };
}

function latestActionsBySeat(records = []) {
  const latest = {};
  records.forEach((record, index) => {
    if (!record || !SEATS.includes(record.position)) return;
    latest[record.position] = { ...record, order: index + 1 };
  });
  return latest;
}

function renderTrainerTable(question) {
  const table = el("trainer-table");
  const records = Array.isArray(question.action_history) ? question.action_history : [];
  const latest = latestActionsBySeat(records);
  const lastSeat = [...records].reverse().find((record) => SEATS.includes(record.position))?.position;
  const heroSeat = question.hero_position || question.hero_table_position;
  const centerLines = [];

  if (question.street === "flop") {
    centerLines.push(`<span>Flop</span>`);
    centerLines.push(`<div id="trainer-table-board" class="trainer-table-board"></div>`);
    centerLines.push(`<strong>Pot ${formatNumber(question.pot_bb, 1)} BB</strong>`);
    if (question.pfa_action) {
      const pfaText = question.pfa_action === "bet"
        ? `${question.pfa_position} bets ${formatNumber(question.pfa_bet_size_bb, 1)} BB`
        : `${question.pfa_position} checks`;
      centerLines.push(`<small>${escapeHtml(pfaText)}</small>`);
    }
  } else {
    centerLines.push(`<span>Pot</span>`);
    centerLines.push(`<strong>${formatNumber(question.pot_bb, 1)} BB</strong>`);
    centerLines.push(`<small>Call ${formatNumber(question.call_amount_bb, 1)} BB</small>`);
    if (question.open_size_bb) centerLines.push(`<small>Open ${formatNumber(question.open_size_bb, 1)} BB</small>`);
    if (question.three_bet_size_bb) centerLines.push(`<small>3-bet ${formatNumber(question.three_bet_size_bb, 1)} BB</small>`);
    if (question.four_bet_size_bb) centerLines.push(`<small>4-bet ${formatNumber(question.four_bet_size_bb, 1)} BB</small>`);
  }

  table.innerHTML = `
    <div class="trainer-felt-center">${centerLines.join("")}</div>
    ${SEATS.map((seat) => {
      const record = latest[seat];
      const display = actionDisplay(record);
      const classes = [
        "trainer-seat",
        `trainer-seat-${seat.toLowerCase()}`,
        record ? "has-action" : "",
        record ? `trainer-action-${display.action.replace(/[^a-z-]/g, "")}` : "trainer-action-waiting",
        seat === heroSeat ? "is-hero" : "",
        seat === lastSeat ? "is-last-action" : "",
      ].filter(Boolean).join(" ");
      const stack = question.stacks?.[seat] ?? (seat === "SB" ? 99.5 : seat === "BB" ? 99 : 100);
      return `
        <div class="${classes}" style="--action-order: ${record?.order || 0}">
          <div class="trainer-seat-top">
            <span>${escapeHtml(seat)}</span>
            <strong>${formatNumber(stack, 0)}</strong>
          </div>
          <div class="trainer-seat-action">${escapeHtml(display.action)}</div>
          <div class="trainer-seat-detail">${escapeHtml(display.detail || (record ? "acted" : "not acted"))}</div>
          ${seat === heroSeat ? `<div class="trainer-seat-cards" aria-label="Hero hand"></div>` : ""}
        </div>
      `;
    }).join("")}
  `;

  const heroCards = table.querySelector(".trainer-seat-cards");
  if (heroCards) {
    renderCardTiles(heroCards, splitCardText(question.hero_hand));
  }

  if (question.street === "flop") {
    const board = table.querySelector("#trainer-table-board");
    if (board) renderCardTiles(board, question.flop_cards || []);
  }
}

function renderTrainerCards(question) {
  renderCardTiles(el("trainer-hero-cards"), splitCardText(question.hero_hand));
  const board = el("trainer-board-cards");
  if (question.street === "flop") {
    board.classList.remove("hidden");
    renderCardTiles(board, question.flop_cards || []);
  } else {
    board.classList.add("hidden");
    board.innerHTML = "";
  }
}

function renderTrainerHistoryItems(items) {
  const history = el("trainer-history");
  history.innerHTML = "";
  items.forEach((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    history.appendChild(item);
  });
}

function renderTrainerQuestion(question) {
  if (question.street === "flop") {
    renderFlopTrainerQuestion(question);
    return;
  }
  const scenarioLabel = {
    open_first: "Open First",
    facing_open: "Facing Open",
    facing_3bet: "Facing 3-bet",
    facing_4bet: "Facing 4-bet",
  }[question.scenario_type] || "Preflop Spot";
  el("trainer-title").textContent = `${question.hero_position} | ${scenarioLabel}`;
  const sizingParts = [];
  if (question.open_size_bb) sizingParts.push(`Open ${formatNumber(question.open_size_bb, 1)} BB`);
  if (question.three_bet_size_bb) sizingParts.push(`3-bet ${formatNumber(question.three_bet_size_bb, 1)} BB`);
  if (question.four_bet_size_bb) sizingParts.push(`4-bet ${formatNumber(question.four_bet_size_bb, 1)} BB`);
  el("trainer-hand").textContent = `Pot ${formatNumber(question.pot_bb, 1)} BB | Call ${formatNumber(question.call_amount_bb, 1)} BB${sizingParts.length ? ` | ${sizingParts.join(" | ")}` : ""}`;
  renderTrainerCards(question);
  renderTrainerTable(question);
  el("flop-summary").classList.add("hidden");
  el("flop-summary").innerHTML = "";
  renderTrainerHistoryItems(question.action_history.map((record) => `${record.position} ${record.action} ${formatNumber(record.amount, 1)} BB`));
  const actions = el("trainer-actions");
  actions.innerHTML = "";
  question.available_actions.forEach((action) => {
    const button = document.createElement("button");
    button.textContent = action;
    button.addEventListener("click", () => gradeTrainer(action));
    actions.appendChild(button);
  });
  el("trainer-result").innerHTML = "";
}

function renderFlopTrainerQuestion(question) {
  el("trainer-title").textContent = `${question.hero_table_position} | ${question.pot_type}`;
  el("trainer-hand").textContent = `Flop ${formatFlopCards(question.flop_cards)} | Pot ${formatNumber(question.pot_bb, 1)} BB`;
  renderTrainerCards(question);
  renderTrainerTable(question);
  const summary = el("flop-summary");
  summary.classList.remove("hidden");
  summary.innerHTML = `
    <div>
      <span class="metric-label">Role</span>
      <strong>${escapeHtml(question.hero_role)}</strong>
    </div>
    <div>
      <span class="metric-label">Position</span>
      <strong>${escapeHtml(question.hero_relative_position)}</strong>
    </div>
    <div>
      <span class="metric-label">Opponent</span>
      <strong>${escapeHtml(question.opponent_position)}</strong>
    </div>
    <div>
      <span class="metric-label">Stack</span>
      <strong>${formatNumber(question.remaining_stack_bb, 1)} BB</strong>
    </div>
  `;

  renderTrainerHistoryItems([
    question.preflop_summary,
    question.pfa_action === "bet"
      ? `Flop: ${question.pfa_position} bets ${formatNumber(question.pfa_bet_size_bb, 1)} BB`
      : question.pfa_action === "check"
      ? "Flop: preflop aggressor checks"
      : "Flop: Hero to act",
  ]);

  const actions = el("trainer-actions");
  actions.innerHTML = "";
  question.available_actions.forEach((action) => {
    const button = document.createElement("button");
    button.textContent = action;
    button.addEventListener("click", () => gradeTrainer(action));
    actions.appendChild(button);
  });
  el("trainer-result").innerHTML = "";
}

function formatFlopCards(cards) {
  if (!cards || cards.length === 0) return "-";
  return cards.join(" ");
}

async function gradeTrainer(action) {
  if (!state.trainerQuestion) return;
  el("trainer-status").textContent = "Grading...";
  showLoading("Grading action EV...");
  try {
    const endpoint = state.trainerQuestion.street === "flop" ? "/api/flop-trainer/grade" : "/api/trainer/grade";
    const result = await postJson(endpoint, {
      question_id: state.trainerQuestion.question_id,
      user_action: action,
    });
    renderTrainerResult(result);
    el("trainer-status").textContent = result.is_correct ? "Correct" : "Review EVs";
  } catch (error) {
    el("trainer-status").textContent = error.message;
  } finally {
    hideLoading();
  }
}

function renderTrainerResult(result) {
  if (result.street === "flop") {
    renderFlopTrainerResult(result);
    return;
  }
  const rows = result.actions
    .map((action) => `
      <tr>
        <td>${action.name}</td>
        <td>${formatNumber(action.frequency, 1)}%</td>
        <td>${formatNumber(action.ev, 3)}</td>
        <td>${action.is_best ? "Best" : ""}</td>
      </tr>
    `)
    .join("");
  el("trainer-result").innerHTML = `
    <div class="section-heading">
      <h2>${result.is_correct ? "Correct" : "Not correct"} | Score ${result.score}</h2>
    </div>
    <p>${result.feedback}</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Action</th><th>Frequency</th><th>EV</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderFlopTrainerResult(result) {
  const rows = result.actions
    .map((action) => `
      <tr>
        <td>${escapeHtml(action.name)}</td>
        <td>${action.is_acceptable ? "Accepted" : ""}</td>
        <td>${formatNumber(action.ev, 3)}</td>
        <td>${formatNumber(action.score, 2)}</td>
        <td>${escapeHtml(action.reason)}</td>
        <td>${action.is_best ? "Best" : ""}</td>
      </tr>
    `)
    .join("");
  const accepted = (result.accepted_actions || []).map(escapeHtml).join(", ");
  el("trainer-result").innerHTML = `
    <div class="section-heading">
      <h2>${result.is_correct ? "Correct" : "Review"} | Score ${result.score}</h2>
    </div>
    <p>${escapeHtml(result.feedback)}</p>
    <div class="flop-result-grid">
      <div><span class="metric-label">Board texture</span><strong>${escapeHtml(result.texture?.board_texture || "-")}</strong></div>
      <div><span class="metric-label">Hero read</span><strong>${escapeHtml(result.texture?.summary || "-")}</strong></div>
      <div><span class="metric-label">Equity</span><strong>${formatNumber(result.metrics?.equity, 1)}%</strong></div>
      <div><span class="metric-label">Range advantage</span><strong>${escapeHtml(result.metrics?.range_advantage || "-")}</strong></div>
      <div><span class="metric-label">Nut advantage</span><strong>${escapeHtml(result.metrics?.nut_advantage || "-")}</strong></div>
      <div><span class="metric-label">Accepted</span><strong>${accepted || "-"}</strong></div>
    </div>
    <div class="table-wrap trainer-result-table">
      <table>
        <thead><tr><th>Action</th><th>Status</th><th>EV</th><th>Score</th><th>Reason</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

el("add-action").addEventListener("click", () => {
  state.history.push({
    position: el("history-position").value,
    action: el("history-action").value,
    amount: Number(el("history-amount").value),
  });
  setStudyPosition(inferNextSeatAfterHistory());
  state.studyData = null;
  state.analysisPending = true;
  renderHistory();
  analyze();
});

el("clear-actions").addEventListener("click", () => {
  state.history = [];
  setStudyPosition("UTG");
  state.studyData = null;
  state.analysisPending = true;
  renderHistory();
  analyze();
});

document.querySelector(".poker-table").addEventListener("click", (event) => {
  const actionButton = event.target.closest(".seat-line-action");
  if (actionButton) {
    appendSeatAction(actionButton.dataset.seat, actionButton.dataset.action);
    return;
  }
  const seatNode = event.target.closest(".seat");
  if (seatNode) {
    selectStudySeat(seatNode.dataset.seat);
  }
});

["board-cards", "pot-bb", "call-bb", "opponents", "simulations"].forEach((id) => {
  el(id).addEventListener("input", () => {
    state.analysisPending = true;
    renderTableState();
    analyze();
  });
  el(id).addEventListener("change", () => {
    state.analysisPending = true;
    renderTableState();
    analyze();
  });
});

function syncAutoStateControls() {
  const isPreflop = el("street").value === "preflop";
  el("auto-state").disabled = !isPreflop;
  if (!isPreflop) {
    el("auto-state").checked = false;
  }
  const disabled = isPreflop && el("auto-state").checked;
  el("pot-bb").disabled = disabled;
  el("call-bb").disabled = disabled;
  el("opponents").disabled = disabled;
}

el("auto-state").addEventListener("change", () => {
  syncAutoStateControls();
  state.analysisPending = true;
  renderTableState();
  analyze();
});

el("street").addEventListener("change", () => {
  syncAutoStateControls();
  state.analysisPending = true;
  renderTableState();
  analyze();
});

el("analyze-button").addEventListener("click", analyze);
el("hand-filter").addEventListener("input", () => {
  if (state.studyData) renderHandsTable(state.studyData.range_grid);
});
el("trainer-street").addEventListener("change", () => {
  updateTrainerControls();
  state.trainerQuestion = null;
  el("trainer-title").textContent = "No question loaded";
  el("trainer-hand").textContent = "";
  el("trainer-table").innerHTML = "";
  el("trainer-hero-cards").innerHTML = "";
  el("trainer-board-cards").innerHTML = "";
  el("trainer-board-cards").classList.add("hidden");
  el("trainer-history").innerHTML = "";
  el("trainer-actions").innerHTML = "";
  el("trainer-result").innerHTML = "";
  el("flop-summary").classList.add("hidden");
  el("trainer-status").textContent = "";
});
el("new-question").addEventListener("click", loadTrainerQuestion);
el("save-profile").addEventListener("click", saveStrategyProfile);

renderHistory();
syncAutoStateControls();
updateTrainerControls();
renderTableState();
loadStrategyProfile();
analyze();
