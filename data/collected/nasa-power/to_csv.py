"""NASA POWER hourly JSON (raw/) -> hourly.csv; reports the last hour with real solar data (-999 = not yet processed)."""
import csv, json, pathlib, sys
here = pathlib.Path(sys.argv[1])
rows, last = [], {}
for f in sorted((here / "raw").glob("*.json")):
    site = f.stem.split("_")[0]
    p = json.loads(f.read_text())["properties"]["parameter"]
    keys = list(p)
    for t in p[keys[0]]:
        r = {"site": site, "utc": f"{t[:4]}-{t[4:6]}-{t[6:8]}T{t[8:]}:00Z"}
        r.update({k: (None if p[k][t] == -999 else p[k][t]) for k in keys})
        rows.append(r)
        if r["ALLSKY_SFC_SW_DWN"] is not None:
            last[site] = max(last.get(site, ""), r["utc"])
with open(here / "hourly.csv", "w", newline="") as out:
    w = csv.DictWriter(out, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
print(len(rows), "rows; last real solar hour:", last)
