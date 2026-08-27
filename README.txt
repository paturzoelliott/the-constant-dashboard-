THE CONSTANT — Public Live Dashboard v4.1

This is the public-host edition. It is designed for 24/7 hosting rather than Google Colab.

Viewer behavior:
- the clock uses each visitor's own browser/device time zone;
- the clock updates every second without flashing;
- dashboard state refreshes every 15 seconds without redrawing the whole page;
- official government sources are checked every 60 seconds server-side.

Deploy:
1. Upload these files to a Git repository or hosting service.
2. Install with: pip install -r requirements.txt
3. Start with: gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT app:app
4. For persistent audit state, attach persistent storage and set DATA_DIR=/data.

LinkedIn:
Put the public HTTPS dashboard URL in your LinkedIn Featured section/profile link.
The dashboard includes a direct button back to:
https://www.linkedin.com/in/robert-paturzo-elliott-b878771a8

Important:
Render Free web services spin down after 15 minutes of no inbound traffic, so use a paid always-on service if you require true 24/7 availability.


v4.2 adds: Employee LCI panel, Remuneration Tribunal comparison, RBA policy monitor, stronger embedded blue background.


v4.3 adds LOW-PAID & AWARD CLAIMS MONITOR:
- monitors ACTU official media releases plus FWC Annual Wage Review submissions/determinations;
- shows rate before, claimed/applied percentage and implied weekly rate, and final outcome;
- active items remain on the main dashboard for 30 days;
- items then move automatically into an 18-month archive;
- archive is retained in state.json and exposed through the dashboard;
- seeded archive includes ACTU 2026 5% -> 6% claim and 2026 FWC outcome, plus CFMEU 2026 submission context.


v4.4 announcement retention policy:
- every official announcement stays on the main dashboard for 7 days;
- after 7 days it moves automatically to the general announcement archive;
- the archive retains announcements for 18 months;
- this applies across monitored official sources, including DSS ministerial RSS, ABS, RBA, FWC and other announcement sources;
- union/award claims retain their richer 30-day active claim table plus 18-month claim archive, while the announcement headline itself follows the general 7-day announcement rule.


THE CONSTANT LIVE OFFICIAL MONITOR v5.0
=======================================

This consolidates the complete public dashboard system.

Refresh schedule
----------------
- Viewer-local clock: continuous, every second.
- Dashboard state pull: quiet browser update, no full-page flashing.
- Official-source refresh: 10:00 AM and 10:00 PM Australia/Sydney every day.
- Australia/Sydney automatically handles AEST/AEDT daylight saving.
- One startup source check is performed when the server starts.

Included monitoring layers
--------------------------
- National Minimum Wage / FWC.
- Chart C / Services Australia / DSS.
- Official forward social-security announcements.
- Complete Monthly CPI / ABS.
- Employee Living Cost Index (LECI) / Selected Living Cost Indexes.
- RBA cash rate and monetary-policy decisions.
- Remuneration Tribunal and higher-income remuneration comparisons.
- Union movements, low-paid claims and award applications/outcomes.
- Main-page announcement retention: 7 days.
- General announcement archive: 18 months.
- Union/award claim archive: 18 months.
- LinkedIn author link.
- Strong embedded blue background.
- Viewer local clock.
- No flashing redraw loop.

Historical versions should be retained as audit history; do not overwrite them.


v5.1 PRESENTATION RESTORATION
-----------------------------
Restores the useful presentation panels from the earliest dashboard concept:
- Presentation Talking Points
- Real Wage & Cost Pressure
- Current / announced Chart C comparison
- Household Living-Cost Pressure
- Indexation Framework
- Upcoming Official Events
- Live Ticker

Earlier unvalidated figures such as the old 8.95% "Real LECI", household -8.2% impact,
and unverified 3x interest-rate claim are NOT restored as facts. Those panels now use
official ABS values or clearly-labelled THE CONSTANT derived metrics.

The page is wrapped in a self-contained blue tc-shell so the background remains blue
inside notebook/staging renderers as well as on a normal hosted page.


v5.2 BOOK-METHODOLOGY IMPACT MODULES
====================================
Adds the five-panel live implementation requested for the book:

1. ABS Official Living Cost Indexes
   - official ABS observations only.

2. THE CONSTANT LECI / LECIB
   - actual statutory minimum wage vs Chart-C-aligned corrected wage;
   - current essential-cost basket calibrated to the book comparison;
   - same essential costs are divided by actual and corrected wages.

3. Workers' Compensation Premiums & Fees
   - monitors Safe Work Australia's official premium material;
   - current standardised-average premium comparison is shown as an illustration;
   - book historical cumulative counterfactual remains:
       conservative ~ $9.51b;
       central ~ $11.98b;
   - these are premium differences, not observed accounting deficits.
   - jurisdiction-specific scheme fees remain distinct.

4. Tax & Medicare
   - 2026-27 resident tax structure seeded from current law;
   - 15% first marginal rate from 1 July 2026;
   - Medicare levy 2%;
   - single-person low-income thresholds retained in structured state;
   - dashboard book case is single resident, no dependants/exemptions;
   - actual and corrected wage cases are recalculated automatically.

5. Superannuation
   - 12% SG / Payday Super rule;
   - actual and corrected compulsory contributions;
   - annual difference;
   - separately-labelled projection based on explicit return/year assumptions.

Automatic update rule
---------------------
The server runs a startup check, then comprehensive official-source refreshes
at 10:00 AM and 10:00 PM Australia/Sydney. When monitored official inputs
change, the affected book calculations are recalculated before state is saved.

Methodological rule
-------------------
Official observations and THE CONSTANT counterfactual calculations are kept
separate on screen and in state.json.


v5.3 SECTION 6 — INCOME SUPPORT
================================
Added immediately beneath the five v5.2 book-methodology modules.

Method:
- Actual column = official current payment rate.
- Calculate each payment's weekly equivalent.
- Calculate that weekly payment as a percentage of the actual NMW.
- Preserve that percentage and apply it to THE CONSTANT corrected wage.
- Display actual rate, percentage, counterfactual rate, and dollar difference.

Seeded current rates:
- Age Pension single basic: $1,100.30/fn.
- Age Pension single total: $1,200.90/fn.
- DSP adult single basic: $1,100.30/fn.
- DSP adult single typical total: $1,200.90/fn.
- JobSeeker single, no children: $808.70/fn.

Official actual rates and THE CONSTANT counterfactual outputs are explicitly
labelled separately. Counterfactual values are not government payment rates.

Automatic monitoring:
- Services Australia Age Pension rate page.
- Services Australia JobSeeker rate page.
- Recalculation whenever the actual NMW, corrected wage, or monitored payment
  rate changes.


v5.6.5 — CPI MONTH COMPARISON + THREE-INCOME LECI
=================================================

Adds:

- ABS monthly CPI automatic monitoring
- previous/current CPI tables side by side
- exact reference month under each CPI table
- 84-month / seven-year CPI archive

July 2026:

- annual CPI 3.5%
- monthly original +1.0%
- monthly seasonally adjusted +0.6%
- Housing +5.0%
- Food and non-alcoholic beverages +3.2%
- Transport +1.6%
- Trimmed mean inflation 3.6%

THE CONSTANT LECI:

- essential weekly basket $1,150.77
- housing and utilities shown separately
- National Minimum Wage $1,004.90/week
- THE CONSTANT proposed wage $1,313.90/week
- Average Weekly Ordinary-Time Earnings $2,083.70/week
- burden percentages shown before income tax and Medicare levy

Official ABS observations remain separately identified from
THE CONSTANT derived measures.



THE CONSTANT LIVE v5.6.6
========================

Adds:
- July 2026 CPI integration.
- Six-month inflation comparison.
- Headline, seasonally adjusted, ex-volatile and fuel measures.
- What Changed This Month.
- RBA Policy Monitor.
- Low Essential Cost Index (LECI).
- Chart C Proposed Wage terminology.
- Material Developments relevant to THE CONSTANT.
- 30-day current announcement and seven-year archive policy.
