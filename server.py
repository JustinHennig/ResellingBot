"""
ResellingBot — Web Server

Runs the bot in a background thread and exposes a small REST API
so the frontend can start/stop the bot and change the interval.

Usage:
    python server.py
Then open http://localhost:5000 in your browser.
"""

import logging
import threading
import time

from flask import Flask, jsonify, render_template, request

from main import load_config, load_seen_listings, run_all_searches, setup_logging

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_state = {"running": False, "interval": 5}   # interval in minutes
_stop_event = threading.Event()
_bot_thread = None
_seen: set = set()
_config: dict = {}

# ---------------------------------------------------------------------------
# Bot loop
# ---------------------------------------------------------------------------

def _bot_loop() -> None:
    logger = logging.getLogger("server")
    while not _stop_event.is_set():
        try:
            run_all_searches(_config, _seen)
        except Exception as exc:
            logger.error(f"Unhandled error in bot loop: {exc}", exc_info=True)

        # Sleep for 'interval' minutes in 10-second chunks so we can stop quickly.
        interval_seconds = _state["interval"] * 60
        elapsed = 0
        while elapsed < interval_seconds and not _stop_event.is_set():
            chunk = min(10, interval_seconds - elapsed)
            time.sleep(chunk)
            elapsed += chunk

    with _lock:
        _state["running"] = False

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify(dict(_state))


@app.route("/api/start", methods=["POST"])
def api_start():
    global _bot_thread
    with _lock:
        if _state["running"]:
            return jsonify({"ok": False, "error": "Already running"}), 409
        _state["running"] = True

    _stop_event.clear()
    _bot_thread = threading.Thread(target=_bot_loop, daemon=True, name="bot-loop")
    _bot_thread.start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    with _lock:
        if not _state["running"]:
            return jsonify({"ok": False, "error": "Not running"}), 409

    _stop_event.set()
    return jsonify({"ok": True})


@app.route("/api/interval", methods=["POST"])
def api_interval():
    data = request.get_json(silent=True) or {}
    try:
        interval = int(data.get("interval", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "interval must be a number"}), 400

    if interval < 1:
        return jsonify({"ok": False, "error": "Interval must be at least 1 minute"}), 400

    with _lock:
        _state["interval"] = interval

    return jsonify({"ok": True, "interval": interval})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _config = load_config()
    settings = _config.get("settings", {})
    setup_logging(settings.get("log_file", "bot.log"))

    _seen = load_seen_listings(settings.get("seen_listings_file", "seen_listings.json"))
    _state["interval"] = settings.get("check_interval_minutes", 5)

    logger = logging.getLogger("server")
    logger.info("Starting web server — open http://localhost:5000")

    app.run(host="0.0.0.0", port=5000, debug=False)
