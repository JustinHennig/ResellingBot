// Fetches log lines from the server and renders them with colour coding.
async function fetchLogs() {
  const lines = document.getElementById("linesSelect").value;
  const autoScroll = document.getElementById("logAutoScroll").checked;
  const box = document.getElementById("logBox");

  try {
    const res = await fetch(`/api/logs?lines=${lines}`);
    const data = await res.json();

    box.innerHTML = data.lines.map(line => {
      const lower = line.toLowerCase();
      let cls = "log-info";
      if (lower.includes("[error]"))        cls = "log-error";
      else if (lower.includes("[warning]")) cls = "log-warning";
      const escaped = line
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      return `<span class="${cls}">${escaped}</span>`;
    }).join("\n");

    if (autoScroll) box.scrollTop = box.scrollHeight;
  } catch (_) {}
}

// Clears the log file on the server.
async function clearLog() {
  if (!confirm("Clear the entire log file?")) return;
  const res = await fetch("/api/logs/clear", { method: "POST" });
  const data = await res.json();
  if (data.ok) {
    document.getElementById("logBox").innerHTML = "";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("linesSelect").addEventListener("change", fetchLogs);
  document.getElementById("clearLogBtn").addEventListener("click", clearLog);

  fetchLogs();
  setInterval(fetchLogs, 5000);
});
