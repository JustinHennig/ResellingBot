let current = { running: false, interval: 5 };
let pending = null; // "starting" | "stopping" | null
let countdownSecs = null; // local countdown, decremented every second
let countdownTimer = null;

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    applyStatus(data);
  } catch (_) {
    /* server unreachable */
  }
}

function applyStatus(data) {
  current = data;

  const badge = document.getElementById("badge");
  const dot = document.getElementById("dot");
  const text = document.getElementById("badgeText");
  const btn = document.getElementById("toggleBtn");
  const input = document.getElementById("intervalInput");

  // While a transition is in progress, wait until the expected state is reached
  if (pending === "stopping" && data.running) return;
  if (pending === "starting" && !data.running) return;

  // Target state reached — clear pending and re-enable the button
  if (pending !== null) {
    pending = null;
    btn.disabled = false;
  }

  if (data.running) {
    badge.className = "badge running";
    text.textContent = "Running";
    dot.classList.add("pulse");
    btn.className = "btn-toggle stop";
    btn.textContent = "Stop";
  } else {
    badge.className = "badge stopped";
    text.textContent = "Stopped";
    dot.classList.remove("pulse");
    btn.className = "btn-toggle start";
    btn.textContent = "Start";
  }

  // Update interval field only when not focused
  if (document.activeElement !== input) {
    input.value = data.interval;
  }

  // Sync countdown from server, then let it tick locally
  startCountdown(data.running ? data.next_run_in : null);
}

function startCountdown(secs) {
  clearInterval(countdownTimer);
  countdownSecs = secs;
  renderCountdown();
  if (secs === null || secs <= 0) return;
  countdownTimer = setInterval(() => {
    countdownSecs = Math.max(0, countdownSecs - 1);
    renderCountdown();
  }, 1000);
}

function renderCountdown() {
  const el = document.getElementById("countdown");
  if (countdownSecs === null) {
    el.innerHTML = "";
  } else if (countdownSecs === 0) {
    el.innerHTML = "Searching...";
  } else {
    const m = Math.floor(countdownSecs / 60);
    const s = countdownSecs % 60;
    const time = m > 0
      ? `<span>${m}m ${String(s).padStart(2, "0")}s</span>`
      : `<span>${s}s</span>`;
    el.innerHTML = `Next run in ${time}`;
  }
}

async function toggleBot() {
  const btn = document.getElementById("toggleBtn");
  const isRunning = current.running;

  btn.disabled = true;
  btn.className = "btn-toggle pending";
  btn.textContent = isRunning ? "Stopping..." : "Starting...";
  pending = isRunning ? "stopping" : "starting";

  try {
    const endpoint = isRunning ? "/api/stop" : "/api/start";
    const res = await fetch(endpoint, { method: "POST" });
    const data = await res.json();
    if (!data.ok) {
      showToast(data.error, "error");
      // Reset on API error
      pending = null;
      btn.disabled = false;
      await fetchStatus();
    }
  } catch (_) {
    pending = null;
    btn.disabled = false;
  }
}

async function applyInterval() {
  const val = parseInt(document.getElementById("intervalInput").value, 10);
  if (!val || val < 1) {
    showToast("Enter a valid interval (≥ 1 min)", "error");
    return;
  }
  const res = await fetch("/api/interval", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interval: val }),
  });
  const data = await res.json();
  if (data.ok) {
    showToast(`Interval set to ${val} min`);
    current.interval = val;
  } else {
    showToast(data.error, "error");
  }
}

let toastTimer = null;
function showToast(msg, type = "success") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.color = type === "error" ? "#f87171" : "#4ade80";
  el.style.opacity = "1";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.style.opacity = "0";
  }, 3000);
}

// ---------------------------------------------------------------------------
// Searches list
// ---------------------------------------------------------------------------

async function fetchSearches() {
  try {
    const res = await fetch("/api/searches");
    const searches = await res.json();
    renderSearches(searches);
  } catch (_) { /* ignore */ }
}

function renderSearches(searches) {
  const list = document.getElementById("searchesList");
  list.innerHTML = "";
  for (const s of searches) {
    const row = document.createElement("div");
    row.className = "search-row" + (s.enabled ? "" : " disabled");

    const nameEl = document.createElement("span");
    nameEl.className = "search-name";
    nameEl.textContent = s.name;

    // Max price input
    const priceWrap = document.createElement("div");
    priceWrap.className = "price-inputs";

    const maxInput = document.createElement("input");
    maxInput.type = "number";
    maxInput.className = "price-input";
    maxInput.value = s.max_price || "";
    maxInput.placeholder = "max €";
    maxInput.title = "Max price (€)";
    maxInput.min = "0";

    priceWrap.appendChild(maxInput);

    // Save on blur or Enter
    let _origMax = maxInput.value;
    async function savePrice() {
      const max = parseInt(maxInput.value) || 0;
      if (String(max) === _origMax) return;
      maxInput.classList.add("saving");
      try {
        const res = await fetch("/api/searches/price", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: s.name, max_price: max }),
        });
        const data = await res.json();
        if (!data.ok) {
          showToast(data.error || "Save failed", "error");
          maxInput.value = _origMax;
        } else {
          _origMax = String(max);
          showToast(`${s.name} max price updated`);
        }
      } catch (_) {
        maxInput.value = _origMax;
      } finally {
        maxInput.classList.remove("saving");
      }
    }
    maxInput.addEventListener("blur", savePrice);
    maxInput.addEventListener("keydown", e => { if (e.key === "Enter") maxInput.blur(); });

    // Toggle switch
    const label = document.createElement("label");
    label.className = "toggle-switch";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = s.enabled;
    checkbox.addEventListener("change", () => toggleSearch(s.name, checkbox, row));
    const slider = document.createElement("span");
    slider.className = "toggle-slider";
    label.appendChild(checkbox);
    label.appendChild(slider);

    row.appendChild(nameEl);
    row.appendChild(priceWrap);
    row.appendChild(label);
    list.appendChild(row);
  }
}

async function toggleSearch(name, checkbox, row) {
  checkbox.disabled = true;
  try {
    const res = await fetch("/api/searches/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!data.ok) {
      showToast(data.error || "Toggle failed", "error");
      checkbox.checked = !checkbox.checked; // revert
    } else {
      row.classList.toggle("disabled", !data.enabled);
    }
  } catch (_) {
    checkbox.checked = !checkbox.checked; // revert on network error
  } finally {
    checkbox.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("toggleBtn").addEventListener("click", toggleBot);
  document.getElementById("setIntervalBtn").addEventListener("click", applyInterval);

  fetchStatus();
  fetchSearches();
  setInterval(fetchStatus, 3000);
});
