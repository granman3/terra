"""Parse per-event tables out of Rocky Mountain Power's Utah DSM annual reports (redacted, public, Utah PSC).

Reads the pdftotext -layout output of each report (one .txt per report year, passed as args as YEAR=path.txt),
writes events.csv next to this script's parent. Values are copied as printed; anything computed is in a *_derived
column or the `flag` column. Run: python -I scripts/parse_utah_dsm.py 2022=a.txt 2023=b.txt 2024=c.txt 2025=d.txt
"""
import csv
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "events.csv"
SRC = {
    2022: ("Utah PSC Docket 23-035-26", "https://pscdocs.utah.gov/electric/23docs/2303526/328209RdctdRMP2022DSMRprt6-1-2023.pdf", "raw/UT_DSM_2022_report_redacted.pdf"),
    2023: ("Utah PSC Docket 24-035-29", "https://pscdocs.utah.gov/electric/24docs/2403529/334005RdctdDSM2023Rprt5-30-2024.pdf", "raw/UT_DSM_2023_report_redacted.pdf"),
    2024: ("Utah PSC Docket 25-035-36", "https://pscdocs.utah.gov/electric/25docs/2503536/339923RdctdRMPDSM2024EnrgyEfcncyPkLdRdctnRprt5-27-2025.pdf", "raw/UT_DSM_2024_report_redacted.pdf"),
    2025: ("Utah PSC Docket 26-035-24", "https://pscdocs.utah.gov/electric/26docs/2603524/345626RdctdRMP2025DSMRprt6-1-2026.pdf", "raw/UT_DSM_2025_report_redacted.pdf"),
}
COLS = ["program", "utility", "report_year", "date", "start_local", "end_local", "timezone", "tz_label_as_printed",
        "duration_min_derived", "duration_h_derived", "event_type", "MW_as_printed", "MW_numeric", "MW_basis",
        "time_as_printed", "flag", "source_docket", "source_url", "local_file", "pdf_page", "table"]
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
T12 = r"\d{1,2}:\d{2}(?::\d{2})?\s*[AaPp][Mm]"

# (year, section-start regex, program, table label, tz label, MW basis, row parser key)
SECTIONS = [
    (2022, r"Table 9: Irrigation Load Control Events", "Irrigation Load Control", "Table 9", "MT", "MW (column unlabeled in text; Table 9)", "irr22"),
    (2022, r"Table 11: Cool Keeper Load Control Events", "Cool Keeper", "Table 11", "MST", "MW Utah reductions", "ck12"),
    (2022, r"Battery Control Events", "Wattsmart Batteries", "Table 13", "Mountain Time", "MW potential", "bat_long"),
    (2023, r"Table 9: Irrigation Load Control Events", "Irrigation Load Control", "Table 9", "MDT", "MW est. reduction at gen", "irr"),
    (2023, r"Table 11: Cool Keeper Load Control Events", "Cool Keeper", "Table 11", "(none printed)", "MW est. reduction at gen", "ck12"),
    (2023, r"Table 13: Wattsmart Battery Control Events", "Wattsmart Batteries", "Table 13", "Mountain Time", "MW potential 'up to'", "bat_long"),
    (2023, r"Table 15: Wattsmart Business Load Control Events", "Wattsmart Business Demand Response", "Table 15", "Mountain Time", "MW achieved", "wsb"),
    (2024, r"Table 10: Irrigation Load Control Events", "Irrigation Load Control", "Table 10", "MDT", "MW est. reduction at gen", "irr"),
    (2024, r"Table 16: Wattsmart Business Load Control Events", "Wattsmart Business Demand Response", "Table 16", "Mountain Time", "MW achieved at site", "wsb"),
    (2024, r"Table 18: Electric Vehicle Charging Demand Response Events", "Wattsmart Drive (EV) pilot", "Table 18", "Mountain Time", "MW achieved (as printed; likely kW, see flag)", "ev24"),
    (2024, r"Table 12 - Cool Keeper Load Control Events$", "Cool Keeper", "Appendix D Table 12", "(none printed)", "MW est. reduction at gen", "ck24"),
    (2025, r"Table 10: Irrigation Load Control Events", "Irrigation Load Control", "Table 10", "MDT", "MW est. reduction at gen", "irr"),
    (2025, r"Table 16: Wattsmart Business Load Control Events", "Wattsmart Business Demand Response", "Table 16", "MDT", "MW achieved at site", "wsb"),
    (2025, r"Table 18: Electric Vehicle Charging Demand Response Events", "Wattsmart Drive (EV) pilot", "Table 18", "MDT", "MW achieved at site", "ev25"),
    (2025, r"^Cool Keeper Event Detail", "Cool Keeper", "Appendix D", "MST", "MW est. reduction at gen", "ck25"),
    (2025, r"^Battery Event Detail", "Wattsmart Batteries", "Appendix E", "MST", "MW est. Utah reductions at gen (range)", "bat25"),
]
END = re.compile(r"Table \d+: Program Performance|Program Performance for|^TOTAL COST|Appendix [A-Z]\b|^\s*Appendix")

DATE_N = r"(\d{1,2}/\d{1,2}/\d{2,4})"
DATE_L = r"([A-Z][a-z]+ \d{1,2}, \d{4})"
ROW = {
    "irr22": re.compile(rf"^\s*{DATE_N}(\s*-\s*Voluntary)?\s+(\d{{1,2}}:\d{{2}}) MT - (\d{{1,2}}:\d{{2}}) MT\s+([\d.]+)\s*$"),
    "irr": re.compile(rf"^\s*{DATE_N}\s+(\d+)(\*?)\s+({T12}) - ({T12}) MDT\s+([\d.]+)\s*$"),
    "ck12": re.compile(rf"^\s*{DATE_N}\s+(.+?)\s{{2,}}([\d.]+)\s*$"),
    "ck24": re.compile(rf"^\s*[A-Z][a-z]+\s+{DATE_N}\s+(\d{{2}}:?\d{{2}})\s*(?:-|to|t0)\s*(\d{{2}}:?\d{{2}})\s+([\d.]+)\s*$"),
    "ck25": re.compile(rf"^\s*{DATE_N}\s+({T12})\s+(\d+)\s+(<?\d+)\s*$"),
    "bat_long": re.compile(rf"^\s*{DATE_L}\s+(.+?)\s{{2,}}([\d]+(?:\s*to\s*\d+)?)\s+(?:(Residential|Commercial)\s+)?(Frequency Response)\s*$"),
    "bat25": re.compile(rf"^\s*{DATE_N}\s+(.+?)\s{{2,}}([\d]+\s*-\s*\d+|[\d.]+|<\d+)\s+(\w[\w ]*?)\s*$"),
    "wsb": re.compile(rf"^\s*{DATE_N}\s+(\d{{1,2}}:\d{{2}}) to (\d{{1,2}}:\d{{2}})\s+([\d.]+)\s+(Advanced? Notice)\s*$"),
    "ev24": re.compile(rf"^\s*{DATE_N}\s+({T12})\s*[–-]\s*({T12})\s+([\d.]+)\s+(\d+)\s+(Frequency Response Test)\s*$"),
    "ev25": re.compile(rf"^\s*{DATE_N}\s+({T12})\s+([\d.]+)\s+(\d+)\s+(Frequency Response Test)\s*$"),
}


def pdate(s):
    s = s.strip()
    for f in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError(s)


def t24(s):
    """'1407' -> 14:07, '0624' -> 06:24, '21:41' -> 21:41"""
    s = s.replace(":", "")
    return f"{int(s[:-2]):02d}:{s[-2:]}"


def t12(s):
    s = re.sub(r"\s+", "", s).upper()
    for f in ("%I:%M:%S%p", "%I:%M%p"):
        try:
            return datetime.strptime(s, f).strftime("%H:%M")
        except ValueError:
            pass
    raise ValueError(s)


def split_range(txt):
    try:
        return _split_range(txt)
    except Exception:
        return "", "", "time misprinted in source ('%s'); start/end left blank" % txt.strip()


def _split_range(txt):
    """'4:30 PM to 4:35PM' / '6:08 to 6:31 PM' / '3:50PM to 3:355 PM' -> (start, end, flag)"""
    a, b = re.split(r"\s+(?:to|t0)\s+", txt.strip(), maxsplit=1)
    flag = ""
    b = b.strip()
    ampm_b = re.search(r"([AaPp][Mm])", b)
    if not re.search(r"[AaPp][Mm]", a) and ampm_b:
        a = a + " " + ampm_b.group(1)
        flag = "start AM/PM not printed; copied from end time"
    m = re.match(r"(\d{1,2}):(\d{3,})\s*([AaPp][Mm])", b.replace(" ", ""))
    if m and len(m.group(2)) > 2:
        return t12(a), "", "end time misprinted in source ('%s'); end left blank" % b
    return t12(a), t12(b), flag


def dur(d, s, e):
    if not s or not e:
        return None
    a = datetime.combine(d, datetime.strptime(s, "%H:%M").time())
    b = datetime.combine(d, datetime.strptime(e, "%H:%M").time())
    if b < a:
        b += timedelta(days=1)
    return (b - a).total_seconds() / 60


def main(args):
    rows = []
    for arg in args:
        year, path = arg.split("=", 1)
        year = int(year)
        text = Path(path).read_text(errors="replace")
        page, cur = 1, None
        for raw in text.split("\n"):
            page += raw.count("\f")
            line = raw.replace("\f", "")
            for (y, pat, prog, tab, tz, basis, key) in SECTIONS:
                if y == year and re.search(pat, line.strip()):
                    cur = (prog, tab, tz, basis, key)
                    break
            else:
                if cur and END.search(line.strip()):
                    cur = None
            if not cur:
                continue
            prog, tab, tz, basis, key = cur
            m = ROW[key].match(line)
            if not m:
                continue
            g, flag, etype, mw, end, start, dmin = m.groups(), "", "", "", "", "", None
            if key == "irr22":
                d = pdate(g[0]); start, end = t24(g[2]), t24(g[3]); mw = g[4]
                etype = "Voluntary" if g[1] else "Mandatory"; printed = f"{g[2]} MT - {g[3]} MT"
            elif key == "irr":
                d = pdate(g[0]); start, end = t12(g[3]), t12(g[4]); mw = g[5]
                etype = "Voluntary" if g[2] else "Mandatory"; printed = f"{g[3]} - {g[4]} MDT"
            elif key == "ck12":
                d = pdate(g[0]); printed = g[1].strip(); mw = g[2]
                start, end, flag = split_range(printed.replace("(MST)", ""))
                etype = "Frequency response or contingency (type not given per event)"
            elif key == "ck24":
                d = pdate(g[0]); start, end = t24(g[1]), t24(g[2]); mw = g[3]
                printed = line.strip().split(None, 2)[2].rsplit(None, 1)[0]
                etype = "Frequency response or contingency (type not given per event)"
            elif key == "ck25":
                d = pdate(g[0]); start = t12(g[1]); dmin = float(g[2]); mw = g[3]
                end = (datetime.combine(d, datetime.strptime(start, "%H:%M").time()) + timedelta(minutes=dmin)).strftime("%H:%M")
                printed = f"start {g[1]}, {g[2]} min"
                flag = "end_local derived = start + printed duration"
                etype = "Frequency response or contingency (type not given per event)"
            elif key == "bat_long":
                d = pdate(g[0]); printed = g[1].strip(); mw = g[2]
                start, end, flag = split_range(printed)
                etype = "Frequency Response"
            elif key == "bat25":
                d = pdate(g[0]); printed = g[1].strip(); mw = g[2]
                start, end, flag = split_range(printed)
                etype = g[3].strip()
            elif key == "wsb":
                d = pdate(g[0]); start, end = t24(g[1]), t24(g[2]); mw = g[3]; etype = "Advance Notice"
                printed = f"{g[1]} to {g[2]}"
            elif key == "ev24":
                d = pdate(g[0]); start, end = t12(g[1]), t12(g[2]); mw = g[3]; etype = g[5]
                printed = f"{g[1]} - {g[2]} ({g[4]} vehicles)"
                if float(mw) > 1:
                    flag = f"MW as printed ({mw}) with {g[4]} vehicles is implausible; program max is 55.7 kW at site, so this column is likely kW"
            elif key == "ev25":
                d = pdate(g[0]); start = t12(g[1]); dmin = 5.0; mw = g[2]; etype = g[4]
                end = (datetime.combine(d, datetime.strptime(start, "%H:%M").time()) + timedelta(minutes=5)).strftime("%H:%M")
                printed = f"start {g[1]} ({g[3]} vehicles; table says all events 5 min)"
                flag = "end_local derived = start + 5 min (table header)"
            if dmin is None:
                dmin = dur(d, start, end)
            if dmin is not None and dmin > 60 and prog in ("Cool Keeper", "Wattsmart Batteries"):
                flag = (flag + "; " if flag else "") + f"derived duration {dmin:.0f} min for a frequency/contingency row: AM/PM typo in source likely"
            try:
                mwn = float(mw.split()[0]) if re.fullmatch(r"[\d.]+", mw.strip()) else ""
            except ValueError:
                mwn = ""
            docket, url, local = SRC[year]
            rows.append({"program": prog, "utility": "Rocky Mountain Power (PacifiCorp East, Utah)", "report_year": year,
                         "date": d.isoformat(), "start_local": start, "end_local": end, "timezone": "America/Denver",
                         "tz_label_as_printed": tz, "duration_min_derived": "" if dmin is None else round(dmin, 1),
                         "duration_h_derived": "" if dmin is None else round(dmin / 60, 3), "event_type": etype,
                         "MW_as_printed": mw, "MW_numeric": mwn, "MW_basis": basis, "time_as_printed": printed,
                         "flag": flag, "source_docket": docket, "source_url": url, "local_file": local,
                         "pdf_page": page, "table": tab})
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    for k, v in sorted(Counter((r["report_year"], r["program"]) for r in rows).items()):
        print(k, v)
    print("total", len(rows))


if __name__ == "__main__":
    main(sys.argv[1:])
