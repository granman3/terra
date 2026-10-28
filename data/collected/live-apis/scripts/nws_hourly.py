"""NWS (api.weather.gov) hourly forecast for Salt Lake City, keyless. NWS requires a User-Agent that identifies the
app (put a contact URL or email you are comfortable sharing in CONTACT). Two calls: /points -> gridpoint, then
/gridpoints/{office}/{x},{y}/forecast/hourly (7 days, deg F, text wind). Gridpoint for SLC is SLC/100,175.
Run: python3 -I nws_hourly.py [lat lon]
"""
import json
import sys
import urllib.request

CONTACT = "contact-placeholder"  # NWS asks for a way to reach you; set before heavy use
UA = f"terra-live-check/0.1 ({CONTACT})"
lat, lon = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("40.76", "-111.89")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


p = get(f"https://api.weather.gov/points/{lat},{lon}")["properties"]
f = get(p["forecastHourly"])["properties"]
print(f"NWS {p['gridId']}/{p['gridX']},{p['gridY']} hourly forecast, updated {f['updateTime']}, {len(f['periods'])} h")
for x in f["periods"][:3]:
    print(f"  {x['startTime']}: {x['temperature']} {x['temperatureUnit']}, {x['shortForecast']}, wind {x['windSpeed']}")
