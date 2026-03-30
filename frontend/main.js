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

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("toggleBtn").addEventListener("click", toggleBot);
  document.getElementById("setIntervalBtn").addEventListener("click", applyInterval);

  // Poll every 3 seconds
  fetchStatus();
  setInterval(fetchStatus, 3000);
});
