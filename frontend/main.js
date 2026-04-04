// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let current = { running: false, interval: 5 };
let pending = null; // "starting" | "stopping" | null
let countdownSecs = null; // local countdown, decremented every second
let countdownTimer = null;

// ---------------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------------

// Fetches the current bot status from the server and applies it to the UI.
async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    applyStatus(data);
  } catch (_) {
    /* server unreachable */
  }
}

// Updates badge, button, interval input, and countdown based on the latest API response.
// Ignores updates while a start/stop transition is still in progress.
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

// Syncs the local countdown to a server-supplied value and starts ticking it down every second.
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

// Renders the countdown text element based on the current countdownSecs value.
function renderCountdown() {
  const el = document.getElementById("countdown");
  if (countdownSecs === null) {
    el.innerHTML = "";
  } else if (countdownSecs === 0) {
    el.innerHTML = "Searching...";
  } else {
    const m = Math.floor(countdownSecs / 60);
    const s = countdownSecs % 60;
    const time =
      m > 0
        ? `<span>${m}m ${String(s).padStart(2, "0")}s</span>`
        : `<span>${s}s</span>`;
    el.innerHTML = `Next run in ${time}`;
  }
}

// Sends a start or stop request, locks the button, and sets the pending state
// so applyStatus() waits for the expected final state before re-enabling the UI.
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

// Reads the interval input and POSTs the new value to /api/interval.
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
// Shows a brief success (green) or error (red) toast message.
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

// Fetches the list of searches from /api/searches and passes them to renderSearches().
async function fetchSearches() {
  try {
    const res = await fetch("/api/searches");
    const searches = await res.json();
    renderSearches(searches);
  } catch (_) {
    /* ignore */
  }
}

// Builds the search list DOM — one row per search with a name label, min/max price inputs, and toggle.
function renderSearches(searches) {
  const list = document.getElementById("searchesList");
  list.innerHTML = "";
  for (const s of searches) {
    const row = document.createElement("div");
    row.className = "search-row" + (s.enabled ? "" : " disabled");

    const nameEl = document.createElement("span");
    nameEl.className = "search-name";
    nameEl.textContent = s.name;

    // Min + Max price inputs
    const priceWrap = document.createElement("div");
    priceWrap.className = "price-inputs";

    const minInput = document.createElement("input");
    minInput.type = "number";
    minInput.className = "price-input";
    minInput.value = s.min_price || "";
    minInput.placeholder = "min €";
    minInput.title = "Min price (€)";
    minInput.min = "0";

    const maxInput = document.createElement("input");
    maxInput.type = "number";
    maxInput.className = "price-input";
    maxInput.value = s.max_price || "";
    maxInput.placeholder = "max €";
    maxInput.title = "Max price (€)";
    maxInput.min = "0";

    priceWrap.appendChild(minInput);
    priceWrap.appendChild(maxInput);

    // Generic save handler — saves any single price field on blur or Enter
    function makeSaveHandler(input, field) {
      let orig = String(input.value);
      async function save() {
        const v = parseInt(input.value) || 0;
        if (String(v) === orig) return;
        input.classList.add("saving");
        try {
          const res = await fetch("/api/searches/price", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: s.name, [field]: v }),
          });
          const data = await res.json();
          if (!data.ok) {
            showToast(data.error || "Save failed", "error");
            input.value = orig;
          } else {
            orig = String(v);
            showToast(`${s.name} updated`);
          }
        } catch (_) {
          input.value = orig;
        } finally {
          input.classList.remove("saving");
        }
      }
      input.addEventListener("blur", save);
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") input.blur();
      });
    }

    makeSaveHandler(minInput, "min_price");
    makeSaveHandler(maxInput, "max_price");

    // Toggle switch
    const label = document.createElement("label");
    label.className = "toggle-switch";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = s.enabled;
    checkbox.addEventListener("change", () =>
      toggleSearch(s.name, checkbox, row),
    );
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

// Calls /api/searches/toggle for the given search name and updates the row's disabled class.
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
// Add Search modal
// ---------------------------------------------------------------------------

function openAddModal() {
  document.getElementById("newSearchName").value = "";
  document.getElementById("newSearchQuery").value = "";
  document.getElementById("newSearchMinPrice").value = "";
  document.getElementById("newSearchMaxPrice").value = "";
  document.getElementById("addSearchModal").style.display = "flex";
  document.getElementById("newSearchName").focus();
}

function closeAddModal() {
  document.getElementById("addSearchModal").style.display = "none";
}

async function addSearch() {
  const name = document.getElementById("newSearchName").value.trim();
  if (!name) {
    showToast("Name is required", "error");
    return;
  }
  const payload = {
    name,
    query: document.getElementById("newSearchQuery").value.trim(),
    min_price:
      parseInt(document.getElementById("newSearchMinPrice").value) || 0,
    max_price:
      parseInt(document.getElementById("newSearchMaxPrice").value) || 0,
  };
  const btn = document.getElementById("addSearchSubmitBtn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/searches/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) {
      showToast(data.error || "Add failed", "error");
    } else {
      closeAddModal();
      showToast(`"${name}" added`);
      fetchSearches();
    }
  } catch (_) {
    showToast("Request failed", "error");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Add Search modal
// ---------------------------------------------------------------------------

function openAddModal() {
  document.getElementById("newSearchName").value = "";
  document.getElementById("newSearchQuery").value = "";
  document.getElementById("newSearchMinPrice").value = "";
  document.getElementById("newSearchMaxPrice").value = "";
  document.getElementById("addSearchModal").style.display = "flex";
  document.getElementById("newSearchName").focus();
}

function closeAddModal() {
  document.getElementById("addSearchModal").style.display = "none";
}

async function addSearch() {
  const name = document.getElementById("newSearchName").value.trim();
  if (!name) {
    showToast("Name is required", "error");
    return;
  }
  const payload = {
    name,
    query: document.getElementById("newSearchQuery").value.trim(),
    min_price:
      parseInt(document.getElementById("newSearchMinPrice").value) || 0,
    max_price:
      parseInt(document.getElementById("newSearchMaxPrice").value) || 0,
  };
  const btn = document.getElementById("addSearchSubmitBtn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/searches/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) {
      showToast(data.error || "Add failed", "error");
    } else {
      closeAddModal();
      showToast(`"${name}" added`);
      fetchSearches();
    }
  } catch (_) {
    showToast("Request failed", "error");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Clears the seen listings file so the bot will re-check all listings.
async function clearSeenListings() {
  if (
    !confirm(
      "Clear all seen listings? The bot will re-notify you about listings it has already seen.",
    )
  )
    return;
  const res = await fetch("/api/seen/clear", { method: "POST" });
  const data = await res.json();
  if (data.ok) {
    showToast("Seen listings cleared");
  } else {
    showToast(data.error || "Clear failed", "error");
  }
}

// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("toggleBtn").addEventListener("click", toggleBot);
  document
    .getElementById("setIntervalBtn")
    .addEventListener("click", applyInterval);
  document
    .getElementById("clearSeenBtn")
    .addEventListener("click", clearSeenListings);
  document
    .getElementById("addSearchBtn")
    .addEventListener("click", openAddModal);
  document
    .getElementById("modalCloseBtn")
    .addEventListener("click", closeAddModal);
  document
    .getElementById("addSearchSubmitBtn")
    .addEventListener("click", addSearch);
  document.getElementById("addSearchModal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeAddModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAddModal();
  });

  fetchStatus();
  fetchSearches();
  setInterval(fetchStatus, 3000);
});
