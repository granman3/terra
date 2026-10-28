"""Live demand-response agent for the stage demo, on the MacBook (no server, no network).

The AI load is real: the ~4B-parameter fine-tune forecasting grid peaks nonstop on the Mac's GPU,
through the replay week, grid after grid. A peak event downshifts: the 4B model stops and the
455K-parameter model takes over the same forecasts. Power comes from macmon (no sudo).

  GET  /power     server-sent events, one sample every 200 ms: watts (CPU+GPU+ANE), gpu, model, J/forecast
  GET  /state     the same, once
  POST /load      start the 4B forecasting loop
  POST /unload    stop all forecasting
  POST /event     peak: downshift to the 455K model
  POST /restore   back to the 4B model

Same API as demo/dr_agent.py, so the router works with either. Binds to 127.0.0.1 only.
Run: demo/.venv/bin/python demo/mac_agent.py   (port 8765; env BIG=models/mycelium-4b, PROMPT=v1|v2)
"""
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "train"))
import numpy as np  # noqa: E402
import torch  # noqa: E402

PORT = 8765
BIG = Path(os.environ.get("BIG", ROOT / "models" / "mycelium-4b"))
PROMPT = os.environ.get("PROMPT", "v2")
TINY = Path(os.environ.get("TINY", next(f for f in (ROOT / "out" / v / "mycelium.pt" for v in ("v3", "v2")) if f.exists())))
REPLAY = ROOT / "data" / "train" / "replay_v2.json"
BATCH = int(os.environ.get("BATCH", 1))  # 1 keeps the downshift quick: at most one 4B forecast (~1.4 s) in flight
WINDOW_S = 10

state = {"mode": "normal", "event_since": None, "load": False, "model": None, "label": None}
labels = {}
latest = {}
lock = threading.Lock()
done = deque(maxlen=400)  # (time, n_forecasts, model) for the live rate
models = {}


def sampler():
    p = subprocess.Popen(["macmon", "pipe", "-i", "200"], stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        now = time.time()
        with lock:
            recent = [(t, n) for t, n, mod in done if now - t < WINDOW_S and mod == state["model"]]
            span = min(WINDOW_S, now - min(t for t, _ in recent) + 0.5) if recent else WINDOW_S
            rate = sum(n for _, n in recent) / span if recent else 0.0
            watts = m["cpu_power"] + m["gpu_power"] + m.get("ane_power", 0)
            latest.update(t=now, watts=round(watts, 2), gpu=round(m["gpu_power"], 2), util=round(m["gpu_active_ratio"] * 100),
                          temp=round(m["temp"]["gpu_temp_avg"]), mode=state["mode"], load=state["load"], model=state["model"],
                          forecasts_per_s=round(rate, 2), joules_per_forecast=round(watts / rate, 4) if rate else None)


def replay_inputs():
    r = json.load(open(REPLAY))
    rows = [(i, ba, h) for ba in r["regions"] for i, h in enumerate(r["hours"][ba])]
    rows.sort(key=lambda x: x[0])  # hour by hour, every grid
    return r["regions"], rows


big_lock = threading.Lock()  # the warm-up thread and the first /load must not both load 8 GB of weights


def big_model():
    with big_lock:
        return _big_model()


def _big_model():
    if "big" not in models:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(BIG)
        tok.padding_side = "left"
        m = AutoModelForSequenceClassification.from_pretrained(BIG, dtype=torch.bfloat16).to("mps").eval()
        m.config.pad_token_id = tok.pad_token_id
        models["big"] = (tok, m, float(getattr(m.config, "peak_temperature", 1.0)))
        n = sum(p.numel() for p in m.parameters())
        labels["big"] = f"{'Qwen3-4B fine-tune' if hasattr(m.config, 'peak_temperature') else 'Qwen3-4B base'} · {n / 1e9:.1f}B params"
    return models["big"]


def tiny_model(regions):
    if "tiny" not in models:
        from train import build, kind_of
        sd = torch.load(TINY, map_location="cpu")
        m = build(kind_of(sd), len(regions), 5, 10, 6)  # v2 MLP or v3 transformer, whichever TINY holds
        m.load_state_dict(sd)
        models["tiny"] = m.eval()
        labels["tiny"] = f"Terra · {sum(p.numel() for p in m.parameters()) / 1e3:.0f}K params"
    return models["tiny"]


def text_for(h, ba, regions):
    from train_big import to_text
    past, fut, cal, mkt = (np.array(h[k], dtype=np.float32) for k in ("past", "fut", "cal", "mkt"))
    if PROMPT == "v1":  # the v1 fine-tune saw 4 past and 4 future channels (same scaling)
        return to_text(past[:, :4], fut[:, [0, 1, 4, 5]], cal, regions.index(ba), regions)
    return to_text(past, fut, cal, regions.index(ba), regions, mkt)


def load_loop():
    regions, rows = replay_inputs()
    k = 0
    while state["load"]:
        if state["mode"] == "event":
            m = tiny_model(regions)
            batch = [rows[(k + j) % len(rows)] for j in range(len(regions))]
            k += len(batch)
            past = torch.tensor([b[2]["past"] for b in batch]); fut = torch.tensor([b[2]["fut"] for b in batch])
            cal = torch.tensor([b[2]["cal"] for b in batch]); mkt = torch.tensor([b[2]["mkt"] for b in batch])
            reg = torch.tensor([regions.index(b[1]) for b in batch])
            with torch.no_grad():
                m(past, fut, cal, reg, mkt)
            with lock:
                done.append((time.time(), len(batch), "tiny"))
                label()
            time.sleep(0.25)  # the tiny model is idle most of the time; this is ~200 forecasts/s
            continue
        tok, m, _ = big_model()
        batch = [rows[(k + j) % len(rows)] for j in range(BATCH)]
        k += BATCH
        enc = tok([text_for(h, ba, regions) for _, ba, h in batch], return_tensors="pt", padding=True).to("mps")
        with torch.no_grad():
            m(**enc).logits.float().cpu()
        with lock:
            done.append((time.time(), len(batch), "big"))
            label()


def label():
    state["label"] = labels.get(state["model"])


def start_load():
    if not state["load"]:
        state.update(load=True, model="tiny" if state["mode"] == "event" else "big")
        threading.Thread(target=load_loop, daemon=True).start()


def stop_load():
    state.update(load=False, model=None)


def event():
    state.update(mode="event", event_since=time.time(), model="tiny" if state["load"] else None)


def restore():
    state.update(mode="normal", event_since=None, model="big" if state["load"] else None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/state":
            with lock:
                return self.json({**latest, **state})
        if path == "/power":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                last = 0
                while True:
                    with lock:
                        s = {**latest, **state}
                    if s.get("t", 0) != last:
                        last = s["t"]
                        self.wfile.write(f"data: {json.dumps(s)}\n\n".encode())
                        self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return
        self.json({"error": "not found"}, 404)

    def do_POST(self):
        actions = {"/load": start_load, "/unload": stop_load, "/event": event, "/restore": restore}
        path = urlparse(self.path).path
        if path not in actions:
            return self.json({"error": "not found"}, 404)
        actions[path]()
        with lock:
            self.json({**latest, **state})


if __name__ == "__main__":
    threading.Thread(target=sampler, daemon=True).start()
    if os.environ.get("WARM", "1") == "1":
        threading.Thread(target=big_model, daemon=True).start()  # load weights before anyone presses a button
    print(f"mac_agent on 127.0.0.1:{PORT}, big {BIG.name} ({PROMPT} prompts), tiny {TINY}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
