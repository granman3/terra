"""List / extract members of a remote ZIP via HTTP Range requests (no full download).
Usage: python -I remote_zip.py URL [list|get MEMBER... --out DIR]"""
import sys, os, io, zipfile, urllib.request

class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req) as r:
            self.size = int(r.headers["Content-Length"])
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos
    def read(self, n=-1):
        if n is None or n < 0: n = self.size - self.pos
        if n == 0 or self.pos >= self.size: return b""
        end = min(self.pos + n, self.size) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(req) as r: data = r.read()
        self.pos += len(data)
        return data
    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)

url, cmd = sys.argv[1], sys.argv[2]
zf = zipfile.ZipFile(io.BufferedReader(RangeFile(url), buffer_size=1 << 20))
if cmd == "list":
    for i in zf.infolist():
        print(i.filename, i.file_size, i.compress_size, i.compress_type)
else:
    out = sys.argv[sys.argv.index("--out") + 1]
    for m in sys.argv[3:sys.argv.index("--out")]:
        dest = os.path.join(out, m.replace("/", "__"))
        with zf.open(m) as src, open(dest, "wb") as dst:
            while chunk := src.read(1 << 22): dst.write(chunk)
        print("saved", dest, os.path.getsize(dest))
