"""Derived summary stats from events.csv (all numbers here are derived by us, not printed in the reports)."""
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path
r = list(csv.DictReader(open(Path(__file__).resolve().parent.parent / "events.csv")))
for prog in sorted({x["program"] for x in r}):
    for y in sorted({x["report_year"] for x in r if x["program"] == prog}):
        rows = [x for x in r if x["program"] == prog and x["report_year"] == y]
        d = [float(x["duration_min_derived"]) for x in rows if x["duration_min_derived"] and not ("typo" in x["flag"])]
        months = Counter(int(x["date"][5:7]) for x in rows)
        jja = sum(v for k, v in months.items() if k in (6, 7, 8))
        hrs = [int(x["start_local"][:2]) for x in rows if x["start_local"]]
        aft = sum(1 for h in hrs if 14 <= h < 20)
        print(f"{prog[:30]:30} {y} n={len(rows):3} Jun-Aug={jja:3} ({jja/len(rows):.0%}) start 14-20h={aft:3} ({aft/max(1,len(hrs)):.0%}) "
              f"dur min/med/max={min(d):.0f}/{sorted(d)[len(d)//2]:.0f}/{max(d):.0f} min total={sum(d)/60:.2f} h months={dict(sorted(months.items()))}")
