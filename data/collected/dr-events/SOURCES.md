# Rocky Mountain Power demand-response event history (Utah, 2022–2025)

Retrieved 2026-10-27. All four reports are public filings on the Utah Public Service Commission's site
(pscdocs.utah.gov, redacted versions; the confidential Appendix C is not public and not used). Public record, no
login. `events.csv` holds 1,048 rows; each row cites its report, PDF page and table.

## Sources

| # | Source | URL | Local file | Rows |
|---|---|---|---|---|
| 1 | RMP 2022 Utah Annual Energy Efficiency and Peak Load Reduction Report, filed 2023-06-01, Docket 23-035-26 | https://pscdocs.utah.gov/electric/23docs/2303526/328209RdctdRMP2022DSMRprt6-1-2023.pdf | raw/UT_DSM_2022_report_redacted.pdf | 89 |
| 2 | RMP 2023 report, filed 2024-05-30, Docket 24-035-29 | https://pscdocs.utah.gov/electric/24docs/2403529/334005RdctdDSM2023Rprt5-30-2024.pdf | raw/UT_DSM_2023_report_redacted.pdf | 106 |
| 3 | RMP 2024 report, filed 2025-05-27, Docket 25-035-36 | https://pscdocs.utah.gov/electric/25docs/2503536/339923RdctdRMPDSM2024EnrgyEfcncyPkLdRdctnRprt5-27-2025.pdf | raw/UT_DSM_2024_report_redacted.pdf | 158 |
| 4 | RMP 2025 report, filed 2026-06-01, Docket 26-035-24 | https://pscdocs.utah.gov/electric/26docs/2603524/345626RdctdRMP2025DSMRprt6-1-2026.pdf | raw/UT_DSM_2025_report_redacted.pdf | 695 |
| 5 | Torus case study, "Rocky Mountain Power deploys Torus to create 500 MW of flexible capacity" (vendor marketing) | https://www.torus.co/case-studies/case-studies-rocky-mountain-power | raw/torus_rmp_case_study.html | 0 (no per-event data) |

Docket pages (they list the reports and the comments filed on them): psc.utah.gov/2026/06/01/docket-no-26-035-24/,
psc.utah.gov/2024/05/31/docket-no-24-035-29/.

Rows by program and year (the counts match the totals printed in each report):

| Program | 2022 | 2023 | 2024 | 2025 | Where in the report |
|---|---|---|---|---|---|
| Wattsmart Business Demand Response (Schedule 114, the program Terra enrolls in) | no event table (program approved Jul 2022; report says enrollment takes 6–9 months) | 6 | 8 | 10 | Tables 15 / 16 / 16 |
| Cool Keeper (residential and commercial AC switches) | 40 | 31 | 134 | 282 | Table 11; 2024–25 Appendix D |
| Irrigation Load Control | 17 | 8 | 11 | 11 | Table 9 / 9 / 10 / 10 |
| Wattsmart Batteries | 32 | 61 | monthly only, not in csv | 350 | Table 13; 2025 Appendix E |
| Wattsmart Drive (EV pilot, test events) | — | — | 5 | 42 | Table 18 |

### Reported vs derived

- **Reported (copied as printed):** date, start and end times, MW, event type where given, tz label. The original
  string is kept in `time_as_printed` and `MW_as_printed`.
- **Derived by us:** `duration_min_derived` / `duration_h_derived` (end − start); `end_local` for 2025 Cool Keeper
  (start + printed duration) and 2025 EV (start + 5 min, from the table header); `timezone` = America/Denver (the
  reports' labels disagree, see below); `MW_numeric` (blank when MW is printed as "<20" or a range); and every
  count, share and hour total below.
- **Source quirks kept, not fixed** (see `flag`): AM/PM typos (e.g. 2023 battery "8:02 AM to 8:07 PM" on a 5-minute
  event), "3:355 PM", "3:25SM", and a missing AM/PM on two rows. The 2024 EV "MW" column (51.3 with 4 vehicles) is
  really kW: the same report gives the program max as 55.7 kW.
- **Time zone labels as printed disagree.** "MST" on 2022 and 2025 Cool Keeper and 2025 batteries; "MDT" on the
  irrigation tables, whose text says the window is "2 PM to 9 PM Mountain Standard Time"; "MDT" on 2025 Wattsmart
  Business, which includes January, November and December events; no label on 2023–24 Cool Keeper. We take all of
  them as local Mountain clock time and keep the printed label in `tz_label_as_printed`.
- Cool Keeper and battery rows often match the same grid frequency event (e.g. 2023-05-15 16:58 and 16:59). They are
  separate programs, so we didn't merge them.
- `pdf_page` is the PDF page index (1-based, as a viewer shows it), not the printed "Page x of y" footer.
- Parsing: `scripts/parse_utah_dsm.py` (run with `python -I` on `pdftotext -layout` output, one regex per table);
  stats: `scripts/summarize.py`.

## Where "every peak-type event 2024–26 fell in Jun–Aug" came from

That sentence isn't in the project. A grep of train/, out/, data/, deck/, web/data and README.md finds no Jun–Aug
claim. README.md actually says the opposite ("Wattsmart dispatch times aren't public"), and train/math_layer.py says
"RMP doesn't publish its event history". Neither is true: RMP files every event in the annual Utah DSM report.

## What this replaces

1. **RMP does publish when it calls.** Every Wattsmart Business, Cool Keeper, irrigation, battery and EV event is
   listed with date, time and MW in the annual report filed with the Utah PSC. The line "Rocky Mountain Power
   doesn't publish its event history" (web/data/dr_event.json, train/math_layer.py) should change to something like:
   "RMP publishes events about 5 months after each year closes (Utah PSC annual DSM report). The 2026 list isn't out
   yet, so the replay-week event is simulated."
2. **Real Wattsmart Business calls are short and happen all year, not 2-hour summer-afternoon blocks.** 24 events
   over 2023–25. 2023: 6 events of 15–60 min, Jun–Sep. 2024: 8 events, all exactly 20 min, Jun–Dec (Oct 2 08:12,
   Nov 14 10:21, Dec 12 14:13). 2025: 10 events of 20–45 min, Jan–Dec, including 01:23 on 7/24 and 07:14 on 12/22.
   All of them are "Advance Notice" type. RMP's own description (2025 report, printed p. 11 = PDF page 15): the program "allows
   year-round availability, sub-hour and fast-response dispatch" and is "not just a seasonal offering" (reported). Hours used (derived): 4.5 h (2023), 2.7 h (2024), 4.2 h (2025), against
   the 65 h a year the tariff allows (65 h is the project's Schedule 114 reading; these reports don't state it). The demo's single 2-hour noon–2 PM call is about 3× the longest real event
   (45 min), and on its own equals about half of a real year's Wattsmart Business dispatch.
3. **The $/kWh framing.** The project's floor ("$100/kW-yr ÷ 65 h ≥ $1.54 per kWh cut") assumes all 65 h get used.
   At the hours actually used (2.7–4.5 h a year), $100/kW-yr works out to roughly $22–37 per kWh cut (derived).
   The payment is mainly for being available, not for energy delivered, and slowing a GPU for 20 minutes a few times
   a year costs almost nothing.
4. **Summer-peak timing applies only to irrigation.** Irrigation events (1–4 h, starting 4–8 PM, Jun–Aug) are the
   only "classic peak" program: 100% of 2023–24 events fell in Jun–Aug. Cool Keeper is now mostly 5-minute
   frequency-response events, Apr–Oct: 134 in 2024 (118 frequency response) and 282 in 2025 (268 frequency, 14
   contingency). Only 27% (2024) and 33% (2025) fell in Jun–Aug. Batteries are dispatched in every month.
5. **The demo week (Oct 19–25).** No Wattsmart Business event in any year fell in Oct 19–25; the closest are
   2024-10-02 and 2025-11-21. Real Utah grid events did happen in that calendar week, though, in other programs:
   Cool Keeper 2024-10-19 02:12, 10-20 23:23 and 23:54, 10-21 08:47; Cool Keeper 2025-10-19 01:00 and 12:01, 10-21 15:38,
   10-24 06:26 and 21:04–21:34 (30 min), with matching battery events on all but the 21:04 one; EV test 2025-10-21 15:50. All are 5–30 minute
   frequency or contingency events with ≤47 MW. None looks like a 2-hour noon-peak call.
6. **Torus.** The 2025 report (p. 12) names Torus as one of two commercial battery vendors approved for the
   Wattsmart Battery program (30 kW–1.2 MW systems). Torus's own case study claims "359 demand response events
   dispatched in 2025" and 500 MW of capacity "being deployed". That is vendor marketing, not a filing. The report's
   Appendix E lists 350 battery events for 2025, close to but not the same as 359. RMP's battery max potential was
   35 MW at site in 2025, so the 500 MW is planned capacity, not delivered.

Also noted: the 2025 report text says Wattsmart Business "maximum potential at generation was 431 MW at site", but
its Table 17 says 30 MW at site / 31 MW at gen. The 431 looks like a typo; use 30–31 MW.

Not collected (time box): CAISO Flex Alert / ERCOT EEA / PJM history, other-state PacifiCorp reports (Idaho,
Wyoming, Oregon) and IRP DR appendices. The Utah reports answer the question directly.
