"""Range-sample a timestamp-sorted Azure LLM trace CSV: fetch N evenly spaced byte chunks, save each raw.
Usage: python -I azure_range_sample.py URL OUTDIR N CHUNK_BYTES"""
import sys, os, urllib.request
from concurrent.futures import ThreadPoolExecutor
url, out, n, cb = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
os.makedirs(out, exist_ok=True)
with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
    size = int(r.headers["Content-Length"])
def get(i):
    a = 64 + int(i * (size - cb - 64) / (n - 1))
    dest = os.path.join(out, f"chunk_{i:04d}_{a}.csv.part")
    if os.path.exists(dest) and os.path.getsize(dest) == cb: return 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={a}-{a + cb - 1}"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r: d = r.read()
            open(dest, "wb").write(d); return len(d)
        except Exception as e: err = e
    print("fail", i, err); return 0
with ThreadPoolExecutor(12) as ex: tot = sum(ex.map(get, range(n)))
print(url, "size", size, "fetched_MB", round(tot / 1e6, 1))
