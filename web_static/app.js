const state = {
  history: [
    { position: "UTG", action: "raise", amount: 2.5 },
    { position: "HJ", action: "fold", amount: 0 },
  ],
  studyData: null,
  selectedHand: null,
  strategyProfile: null,
  trainerQuestion: null,
  selectedSeatAction: "fold",
};

const el = (id) => document.getElementById(id);

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
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

function autoRaiseAmount(seat) {
  const bettingState = state.studyData?.betting_state;
  const currentBet = Number(bettingState?.current_bet_bb || 1);
  const raiseCount = countRaises();
  if (state.selectedSeatAction === "all-in") {
    return Number(bettingState?.max_raise_total_bb || 100);
  }
  if (raiseCount === 0) {
    return seat === "SB" ? 3.5 : 2.5;
  }
  if (raiseCount === 1) {
    const multiplier = seat === "SB" || seat === "BB" ? 4.0 : 3.0;
    return Math.min(100, Math.max(currentBet + 1, currentBet * multiplier));
  }
  return Math.min(100, Math.max(currentBet + 1, currentBet * 2.25));
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

function renderHistory() {
  const list = el("history-list");
  list.innerHTML = "";
  state.history.forEach((record, index) => {
    const item = document.createElement("li");
    item.textContent = `${record.position} ${record.action} ${formatNumber(record.amount, 1)} BB`;
    const remove = document.createElement("button");
    remove.className = "icon-button";
    remove.title = "Remove action";
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      state.history.splice(index, 1);
      renderHistory();
    });
    item.append(" ", remove);
    list.appendChild(item);
  });
  renderTableState();
}

function buildStudyPayload() {
  return {
    hero_position: el("hero-position").value,
    hero_hand: el("hero-hand").value,
    street: "preflop",
    board_cards: "",
    pot_bb: Number(el("pot-bb").value),
    call_amount_bb: Number(el("call-bb").value),
    raise_amount_bb: 0,
    candidate_raise_amounts: [],
    simulations: Number(el("simulations").value),
    action_history: state.history,
    active_opponent_count: Number(el("opponents").value),
    auto_state: true,
  };
}

async function analyze() {
  el("status-line").textContent = "Analyzing...";
  try {
    const data = await postJson("/api/study", buildStudyPayload());
    state.studyData = data;
    state.selectedHand = data.range_grid.find((item) => item.is_selected) || data.range_grid[0];
    renderStudy(data);
    el("status-line").textContent = `Loaded ${data.range_grid.length} hand classes with ${data.range_simulations} range sims each against ${data.opponent_ranges.length} opponent ranges.`;
  } catch (error) {
    el("status-line").textContent = error.message;
  }
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
  el("recommendation").textContent = data.selected_hand.recommended;
  el("equity").textContent = `${formatNumber(data.metrics.equity, 1)}%`;
  el("ev-call").textContent = formatNumber(data.metrics.ev_call, 3);
  el("ev-raise").textContent = formatNumber(data.metrics.ev_raise, 3);
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
  try {
    const profile = await postJson("/api/strategy-profiles", buildStrategyProfilePayload());
    state.strategyProfile = profile;
    renderStrategyProfile(profile);
    el("profile-status").textContent = "Saved";
    analyze();
  } catch (error) {
    el("profile-status").textContent = error.message;
  }
}

function renderTableState() {
  const heroPosition = el("hero-position").value;
  const heroHand = el("hero-hand").value;
  const street = el("street").value;
  const boardCards = el("board-cards").value.trim();
  const bettingState = state.studyData?.betting_state;
  const isClosed = Boolean(bettingState?.is_closed);
  const latestBySeat = {};
  state.history.forEach((record) => {
    latestBySeat[record.position] = record;
  });
  ["UTG", "HJ", "CO", "BTN", "SB", "BB"].forEach((seat) => {
    const button = document.querySelector(`.seat[data-seat="${seat}"]`);
    const stateLabel = el(`seat-state-${seat}`);
    const record = latestBySeat[seat];
    const seatState = bettingState?.seats?.[seat];
    button.classList.remove("hero-seat", "seat-state-fold", "seat-state-call", "seat-state-raise", "seat-state-check");
    button.disabled = isClosed || (Boolean(bettingState) && !seatState?.can_act);
    if (seat === heroPosition) {
      button.classList.add("hero-seat");
    }
    if (seatState?.can_act) {
      stateLabel.textContent = seatState.to_call > 0
        ? `to call ${formatNumber(seatState.to_call, 1)}`
        : "to act";
    } else if (record) {
      button.classList.add(`seat-state-${record.action}`);
      stateLabel.textContent = `${record.action} ${formatNumber(record.amount, 1)} BB`;
    } else if (seat === heroPosition) {
      stateLabel.textContent = "Hero";
    } else if (seat === "SB") {
      stateLabel.textContent = "0.5 BB";
    } else if (seat === "BB") {
      stateLabel.textContent = "1.0 BB";
    } else {
      stateLabel.textContent = "empty";
    }
  });
  el("table-pot").textContent = `${formatNumber(el("pot-bb").value, 1)} BB`;
  el("table-board").textContent = boardCards ? `${street} ${boardCards}` : `${street} board -`;
  const nextToAct = state.studyData?.betting_state?.next_to_act;
  const minRaise = state.studyData?.betting_state?.min_raise_total_bb;
  const maxRaise = state.studyData?.betting_state?.max_raise_total_bb;
  const suggestedSizes = state.studyData?.candidate_raise_amounts || [];
  el("node-status").textContent = isClosed ? "Node closed" : "Open node";
  el("node-status").classList.toggle("closed", isClosed);
  document.querySelector(".poker-table").classList.toggle("closed-node", isClosed);
  el("table-hero").textContent = isClosed
    ? `Hero ${heroPosition} ${heroHand} | Analysis locked`
    : nextToAct
    ? `Hero ${heroPosition} ${heroHand} | Next ${nextToAct}`
    : `Hero ${heroPosition} ${heroHand}`;
  el("table-sizing").textContent = isClosed
    ? "Preflop betting round complete"
    : suggestedSizes.length
    ? `Suggested raise ${suggestedSizes.map((amount) => formatNumber(amount, 1)).join(" / ")}`
    : minRaise
    ? `Min raise ${formatNumber(minRaise, 1)} | All-in ${formatNumber(maxRaise, 0)}`
    : "Betting closed";
  syncLegalActionButtons();
}

function syncLegalActionButtons() {
  const legalActions = state.studyData?.betting_state?.legal_actions;
  const isClosed = Boolean(state.studyData?.betting_state?.is_closed);
  document.querySelectorAll(".seat-action").forEach((button) => {
    const action = button.dataset.seatAction;
    const normalizedAction = action === "all-in" ? "raise" : action;
    const allowed = !isClosed && (!legalActions || legalActions.includes(normalizedAction));
    button.disabled = !allowed;
    if (!allowed && state.selectedSeatAction === action) {
      state.selectedSeatAction = legalActions?.[0] || "fold";
    }
  });
  document.querySelectorAll(".seat-action").forEach((button) => {
    button.classList.toggle("active", button.dataset.seatAction === state.selectedSeatAction);
  });
}

function renderRangeGrid(items) {
  const grid = el("range-grid");
  grid.innerHTML = "";
  items.forEach((item) => {
    const cell = document.createElement("button");
    const recClass = item.recommended.toLowerCase().replace(/\s+/g, "-");
    cell.className = `hand-cell rec-${recClass}`;
    cell.classList.toggle("selected", item.is_selected);
    cell.dataset.hand = item.hand;
    cell.innerHTML = `
      <span class="hand-name">${item.hand}</span>
      <span class="hand-meta">${item.recommended} ${formatNumber(item.frequency, 0)}%</span>
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
        <td>${formatRaiseOptions(item.raise_options)}</td>
      `;
      tbody.appendChild(row);
    });
}

async function loadTrainerQuestion() {
  el("trainer-status").textContent = "Loading question...";
  try {
    const question = await postJson("/api/trainer/question", {
      simulations: Number(el("trainer-simulations").value),
      scenario_type: el("trainer-mode").value,
    });
    state.trainerQuestion = question;
    renderTrainerQuestion(question);
    el("trainer-status").textContent = question.question_id;
  } catch (error) {
    el("trainer-status").textContent = error.message;
  }
}

function renderTrainerQuestion(question) {
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
  el("trainer-hand").textContent = `${question.hero_hand} | Pot ${formatNumber(question.pot_bb, 1)} BB | Call ${formatNumber(question.call_amount_bb, 1)} BB${sizingParts.length ? ` | ${sizingParts.join(" | ")}` : ""}`;
  const history = el("trainer-history");
  history.innerHTML = "";
  question.action_history.forEach((record) => {
    const item = document.createElement("li");
    item.textContent = `${record.position} ${record.action} ${formatNumber(record.amount, 1)} BB`;
    history.appendChild(item);
  });
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

async function gradeTrainer(action) {
  if (!state.trainerQuestion) return;
  el("trainer-status").textContent = "Grading...";
  try {
    const result = await postJson("/api/trainer/grade", {
      question_id: state.trainerQuestion.question_id,
      user_action: action,
    });
    renderTrainerResult(result);
    el("trainer-status").textContent = result.is_correct ? "Correct" : "Review EVs";
  } catch (error) {
    el("trainer-status").textContent = error.message;
  }
}

function renderTrainerResult(result) {
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

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

el("add-action").addEventListener("click", () => {
  state.history.push({
    position: el("history-position").value,
    action: el("history-action").value,
    amount: Number(el("history-amount").value),
  });
  renderHistory();
});

el("clear-actions").addEventListener("click", () => {
  state.history = [];
  renderHistory();
  analyze();
});

document.querySelectorAll(".seat-action").forEach((button) => {
  button.addEventListener("click", () => {
    state.selectedSeatAction = button.dataset.seatAction;
    if (state.selectedSeatAction === "raise") {
      el("seat-action-amount").value = autoRaiseAmount(state.studyData?.betting_state?.next_to_act || "UTG");
    } else if (state.selectedSeatAction === "all-in") {
      el("seat-action-amount").value = state.studyData?.betting_state?.max_raise_total_bb || "100";
    } else {
      el("seat-action-amount").value = "0";
    }
    document.querySelectorAll(".seat-action").forEach((node) => {
      node.classList.toggle("active", node === button);
    });
  });
});

document.querySelectorAll(".seat").forEach((button) => {
  button.addEventListener("click", () => {
    const seat = button.dataset.seat;
    const seatState = state.studyData?.betting_state?.seats?.[seat];
    if (seatState && !seatState.can_act) {
      return;
    }
    const action = state.selectedSeatAction === "all-in" ? "raise" : state.selectedSeatAction;
    const amount = action === "call"
      ? Number(seatState?.to_call || 0)
      : action === "raise"
      ? autoRaiseAmount(seat)
      : Number(el("seat-action-amount").value);
    state.history.push({
      position: seat,
      action: action,
      amount: amount,
    });
    renderHistory();
    analyze();
  });
});

["hero-position", "hero-hand", "street", "board-cards", "pot-bb"].forEach((id) => {
  el(id).addEventListener("input", renderTableState);
  el(id).addEventListener("change", renderTableState);
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
  renderTableState();
});

el("street").addEventListener("change", () => {
  syncAutoStateControls();
  renderTableState();
});

el("analyze-button").addEventListener("click", analyze);
el("hand-filter").addEventListener("input", () => {
  if (state.studyData) renderHandsTable(state.studyData.range_grid);
});
el("new-question").addEventListener("click", loadTrainerQuestion);
el("save-profile").addEventListener("click", saveStrategyProfile);

renderHistory();
syncAutoStateControls();
renderTableState();
loadStrategyProfile();
analyze();
