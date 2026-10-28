"""Read only selected columns of parquet members inside a remote STORED zip, via HTTP Range.
Saves a column-projected parquet per member into --out. No full download.
Usage: python -I remote_parquet.py ZIP_URL --cols a,b,c --out DIR [--list] MEMBER..."""
import sys, os, io, struct, zipfile, urllib.request
import pyarrow.parquet as pq

FETCHED = [0]
class RangeFile(io.RawIOBase):
    def __init__(self, url, base=0, size=None):
        self.url, self.base, self.pos = url, base, 0
        if size is None:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
                size = int(r.headers["Content-Length"])
        self.size = size
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos
    def read(self, n=-1):
        if n is None or n < 0: n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0: return b""
        a = self.base + self.pos
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={a}-{a + n - 1}"})
        with urllib.request.urlopen(req) as r: data = r.read()
        FETCHED[0] += len(data); self.pos += len(data)
        return data
    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)

args = sys.argv[1:]
url = args[0]
cols = args[args.index("--cols") + 1].split(",")
out = args[args.index("--out") + 1]
members = [a for i, a in enumerate(args[1:], 1) if not a.startswith("--") and args[i - 1] not in ("--cols", "--out")]
root = RangeFile(url)
zf = zipfile.ZipFile(io.BufferedReader(root, buffer_size=1 << 16))
info = {i.filename: i for i in zf.infolist()}
if "--list" in args:
    for n, i in info.items(): print(n, i.file_size)
    sys.exit()
os.makedirs(out, exist_ok=True)
for m in members:
    zi = info[m]
    assert zi.compress_type == 0, "member must be STORED"
    root.seek(zi.header_offset); h = root.read(30)
    fn_len, ex_len = struct.unpack("<HH", h[26:30])
    data_off = zi.header_offset + 30 + fn_len + ex_len
    before = FETCHED[0]
    t = pq.read_table(RangeFile(url, data_off, zi.file_size), columns=cols)
    dest = os.path.join(out, m.replace("/", "__").replace("=", "-"))
    pq.write_table(t, dest)
    print(m, "rows", t.num_rows, "fetched_MB", round((FETCHED[0] - before) / 1e6, 1), "->", dest, flush=True)
