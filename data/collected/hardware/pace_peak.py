import csv, sys, glob
best = {}
for f in sorted(glob.glob(sys.argv[1] + "/EIA930_BALANCE_*.csv")):
    r = csv.reader(open(f, encoding="utf-8-sig"))
    h = next(r)
    bi = h.index("Balancing Authority"); ti = h.index("UTC Time at End of Hour")
    cands = [h.index("Demand (MW) (Adjusted)")]
    di = cands[0]
    for row in r:
        if row[bi] != "PACE": continue
        v = row[di].replace(",", "")
        if not v: continue
        try: x = float(v)
        except: continue
        y = row[ti][6:10] if "/" in row[ti] else row[ti][:4]
        if y not in best or x > best[y][0]: best[y] = (x, row[ti], h[di], f.split("/")[-1])
for y in sorted(best): print(y, best[y])
