"""ERCOT public dashboard JSON (www.ercot.com/gridmktinfo/dashboards), keyless, no User-Agent needed.
  supply-demand.json      5-min actual demand + capacity today, hourly forecast demand 6 days ahead
  fuel-mix.json           5-min generation by fuel, yesterday + today
  system-wide-prices.json 15-min real-time settlement point prices (hubs, load zones) + today's DAM hourly
Timestamps carry their own offset (Central, -0500 in CDT).
Run: python3 -I ercot_dashboard.py
"""
import json
import urllib.request
from datetime import datetime, timezone

B = "https://www.ercot.com/api/1/services/read/dashboards/"


def get(name):
    req = urllib.request.Request(B + name, headers={"User-Agent": "terra-live-check/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def utc(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S%z").astimezone(timezone.utc)


sd = get("supply-demand.json")
a = [x for x in sd["data"] if x["forecast"] == 0][-1]
print(f"ERCO demand {a['demand']} MW at {utc(a['timestamp']):%Y-%m-%d %H:%M} UTC (capacity {a['capacity']} MW)")
fc = [x for x in sd["forecast"] if x["deliveryDate"] == sd["forecast"][0]["deliveryDate"]]
hi = max(fc, key=lambda x: x["forecastedDemand"])
print(f"ERCOT forecast {hi['deliveryDate']}: peak {hi['forecastedDemand']} MW, hour ending {hi['hourEnding']} Central")
fm = get("fuel-mix.json")["data"]
day = sorted(fm)[-1]
t = sorted(fm[day])[-1]
print(f"ERCOT fuel mix at {utc(t):%H:%M} UTC: " + ", ".join(f"{k} {v['gen']:.0f}" for k, v in fm[day][t].items()))
p = get("system-wide-prices.json")
r = p["rtSppData"][-1]
print(f"ERCOT RT hub avg ${r['hbHubAvg']}/MWh, interval ending {r['intervalEnding']} Central (updated {p['lastUpdated']})")
