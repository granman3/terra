"""Live demand-response agent for the on-stage demo (runs on enterprise as root; stdlib only).

  GET  /power     server-sent events, one GPU sample every 100 ms
  GET  /state     current mode, settings, load generator status
  POST /load      start the load generator (llama-bench decode loop: steady AI work)
  POST /unload    stop it
  POST /event     peak event: lock the SM clock (decode drops ~275 W -> ~195 W for ~6% speed)
  POST /restore   back to default clocks

Every POST needs header X-Token (or ?token=) matching /root/watts-per-token/.dr-token.
Safety: an event auto-restores after AUTO_RESTORE_S; exit/SIGTERM restores clocks, the
350 W cap, and stops the load. Uses the clock lock, not the power cap, so the host
watchdog (which checks the cap) stays quiet during the demo.

Run: python3 demo/dr_agent.py   (port 8765)
"""
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
EVENT_MHZ = int(os.environ.get("EVENT_MHZ", 2400))
STANDING_CAP = 350
AUTO_RESTORE_S = 300
BENCH = "/fast/ollama/prism/llama-bench"
MODEL = "/fast/ollama/models/Ternary-Bonsai-2-27B-PTQ1_0.gguf"
TOKEN_FILE = Path("/root/watts-per-token/.dr-token")

if not TOKEN_FILE.exists():
    TOKEN_FILE.write_text(secrets.token_urlsafe(18))
    TOKEN_FILE.chmod(0o600)
TOKEN = TOKEN_FILE.read_text().strip()

state = {"mode": "normal", "event_since": None, "load": False, "event_mhz": EVENT_MHZ}
latest = {}
lock = threading.Lock()
load_proc = None
restore_timer = None


def smi(*args):
    return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True)


def sampler():
    """One nvidia-smi process for everyone; clients read the latest sample."""
    fields = "power.draw.instant,clocks.sm,utilization.gpu,power.limit,temperature.gpu"
    p = subprocess.Popen(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits", "-lms", "100"],
                         stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        try:
            w, mhz, util, cap, temp = (float(x) for x in line.split(","))
        except ValueError:
            continue
        with lock:
            latest.update(t=time.time(), watts=w, sm_mhz=mhz, util=util, cap=cap, temp=temp, mode=state["mode"], load=state["load"])


def load_loop():
    env = dict(os.environ, LD_LIBRARY_PATH="/fast/ollama/prism/cudalibs:/fast/ollama/prism")
    while state["load"]:
        global load_proc
        load_proc = subprocess.Popen([BENCH, "-m", MODEL, "-ngl", "99", "-p", "0", "-n", "512", "-r", "50"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        load_proc.wait()


def start_load():
    if not state["load"]:
        state["load"] = True
        threading.Thread(target=load_loop, daemon=True).start()


def stop_load():
    state["load"] = False
    if load_proc and load_proc.poll() is None:
        load_proc.terminate()


def event():
    global restore_timer
    smi("-lgc", f"{EVENT_MHZ},{EVENT_MHZ}")
    state.update(mode="event", event_since=time.time())
    if restore_timer:
        restore_timer.cancel()
    restore_timer = threading.Timer(AUTO_RESTORE_S, restore)
    restore_timer.daemon = True
    restore_timer.start()


def restore():
    smi("-rgc")
    smi("-pl", str(STANDING_CAP))
    state.update(mode="normal", event_since=None)


def shutdown(*_):
    stop_load()
    restore()
    sys.exit(0)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-Token, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/state":
            with lock:
                return self.json({**latest, **state})
        if path == "/power":
            self.send_response(200)
            self.cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                last = 0
                while True:
                    with lock:
                        s = dict(latest)
                    if s.get("t", 0) != last:
                        last = s["t"]
                        self.wfile.write(f"data: {json.dumps(s)}\n\n".encode())
                        self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return
        self.json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        token = self.headers.get("X-Token") or parse_qs(u.query).get("token", [""])[0]
        if not secrets.compare_digest(token, TOKEN):
            return self.json({"error": "bad token"}, 403)
        actions = {"/load": start_load, "/unload": stop_load, "/event": event, "/restore": restore}
        if u.path not in actions:
            return self.json({"error": "not found"}, 404)
        actions[u.path]()
        with lock:
            self.json({**latest, **state})


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    restore()
    threading.Thread(target=sampler, daemon=True).start()
    print(f"dr_agent on :{PORT}, event clock {EVENT_MHZ} MHz, auto-restore {AUTO_RESTORE_S}s", flush=True)
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    finally:
        shutdown()
