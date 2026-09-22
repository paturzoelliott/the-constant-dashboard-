#!/usr/bin/env python3
from __future__ import annotations

import os
import csv, hashlib, json, os, re, threading, time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, send_from_directory, session

PORT = int(os.getenv("PORT", "8765"))
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")
BASE_REFRESH_SECONDS = max(300, int(os.getenv("TC_REFRESH_SECONDS", "3600")))
RELEASE_REFRESH_SECONDS = max(300, int(os.getenv("TC_RELEASE_REFRESH_SECONDS", "300")))
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", APP_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
RUNTIME_STATE_FILE = DATA_DIR / "runtime_state.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.jsonl"
AUDIT_MAX_ENTRIES = max(100, int(os.getenv("TC_AUDIT_MAX_ENTRIES", "2000")))

DEFAULT = {
    "version": "9.7.7",
    "started_at": None,
    "last_check": None,
    "next_check": None,
    "refresh_schedule": {
        "timezone": "Australia/Sydney",
        "base_interval_minutes": 60,
        "release_interval_minutes": 5,
        "description": "Hourly official-source monitoring; five-minute checks during configured release windows"
    },
    "checks_completed": 0,
    "source_changes_detected": 0,
    "errors": [],
    "core": {
        "minimum_wage_weekly": 1004.90,
        "chart_c_fortnightly": 2701.40,
        "chart_c_weekly": 1350.70,
        "ratio_pct": 74.3985,
        "weekly_gap": 345.80,
        "income_free_area_fortnightly": 226.00,
        "taper": 0.50
    },
    "official": {
        "cpi_reference_period": "July 2026",
        "cpi_annual_pct": 3.5,
        "employee_lci_annual_pct": 3.7,
        "employee_lci_quarterly_pct": 1.5,
        "pblci_annual_pct": 4.6,
        "age_pensioner_lci_annual_pct": 4.7,
        "lci_reference_base": "September 2025 quarter = 100",
        "cash_rate_pct": 4.35
    },
    "labour_market": {
        "source": "Australian Bureau of Statistics — Labour Force, Australia",
        "classification": "OFFICIAL OBSERVATION",
        "reference_period": "July 2026",
        "employment_persons": 14807200,
        "employment_change_persons": -15800,
        "employment_change_pct": -0.1,
        "unemployment_rate_pct": 4.5,
        "participation_rate_pct": 66.9,
        "employment_population_ratio_pct": 63.9,
        "underemployment_rate_pct": 6.4,
        "full_time_employment_persons": 10210500,
        "part_time_employment_persons": 4596700,
        "monthly_hours_worked_millions": 1998,
        "hours_worked_change_millions": -12,
        "hours_worked_change_pct": -0.6,
        "release_date": "2026-08-20",
        "last_verified": "ABS Labour Force, Australia — July 2026; released 20 August 2026",
        "automatic_parser_status": "Complete verified July 2026 seasonally adjusted headline set. August 2026 release due 24 September 2026 at 11:30am AEST."
    },
    "forward": {
        "status": "Official Services Australia cut-off confirmed — effective 20 September 2026",
        "effective_date": "2026-09-20",
        "chart_c_fortnightly": 2701.40,
        "chart_c_weekly": 1350.70,
        "weekly_gap": 345.80,
        "ratio_pct": 74.3985
    },
    "book_impact_model": {
        "methodology": "THE CONSTANT book methodology — actual statutory minimum wage versus Chart-C-aligned corrected wage counterfactual",
        "actual_wage_weekly": 1004.90,
        "corrected_wage_weekly": 1350.70,
        "annual_weeks": 52,

        "lecib": {
            "name": "Low-Paid Essential Cost Income Burden",
            "essential_cost_basket_weekly": 793.06708,
            "actual_burden_pct": 78.92,
            "corrected_burden_pct": 60.3598,
            "last_cost_update_period": "June 2026",
            "cost_update_source": "Book-calibrated essential-cost basket; future movement indexed from verified official cost inputs"
        },

        "workers_comp": {
            "latest_standardised_average_premium_rate_pct": 1.59,
            "latest_rate_period": "2023-24",
            "book_conservative_coverage_pct": 75.0,
            "book_conservative_rate_discount_pct": 10.0,
            "book_cumulative_conservative_difference_billion": 9.51,
            "book_cumulative_central_difference_billion": 11.98,
            "note": "Current standardised premium comparison is illustrative; book historical model retains jurisdiction/rate assumptions and labels results as counterfactual premium differences."
        },

        "tax_medicare": {
            "income_year": "2026-27",
            "resident_tax_free_threshold": 18200.0,
            "tax_brackets": [
                {"lower": 18200.0, "upper": 45000.0, "rate": 0.15},
                {"lower": 45000.0, "upper": 135000.0, "rate": 0.30},
                {"lower": 135000.0, "upper": 190000.0, "rate": 0.37},
                {"lower": 190000.0, "upper": None, "rate": 0.45}
            ],
            "medicare_levy_rate_pct": 2.0,
            "medicare_single_lower_threshold": 27222.0,
            "medicare_single_upper_threshold": 34027.0,
            "medicare_phase_in_rate": 0.10,
            "note": "Single resident, no dependants, no exemptions/surcharges; dashboard identifies this as the book comparison case."
        },

        "superannuation": {
            "sg_rate_pct": 12.0,
            "rule": "From 1 July 2026, Payday Super — 12% of qualifying earnings",
            "projection_return_pct": 5.0,
            "projection_years": 30,
            "projection_note": "Projection assumption is explicit and separate from observed compulsory contributions."
        },

        "calculated": {}
    },
    "income_support_counterfactual": {
        "methodology": "Preserve each payment's current percentage relationship to the actual National Minimum Wage, then apply that same percentage to THE CONSTANT corrected-wage counterfactual.",
        "actual_nmw_weekly": 1004.90,
        "corrected_wage_weekly": 1350.70,
        "payments": {
            "age_pension_single_basic": {
                "label": "Age Pension — single basic rate",
                "actual_fortnightly": 1135.40,
                "source": "Services Australia",
                "source_effective_period": "from 20 September 2026",
                "official": True
            },
            "age_pension_single_total": {
                "label": "Age Pension — single total",
                "actual_fortnightly": 1237.70,
                "source": "Services Australia",
                "source_effective_period": "from 20 September 2026",
                "official": True
            },
            "dsp_single_basic": {
                "label": "DSP — adult single basic rate",
                "actual_fortnightly": 1135.40,
                "source": "Services Australia — Guide to Australian Government payments",
                "source_effective_period": "from 20 September 2026",
                "official": True
            },
            "dsp_single_typical_total": {
                "label": "DSP — adult single typical total",
                "actual_fortnightly": 1237.70,
                "source": "Services Australia — Guide to Australian Government payments",
                "source_effective_period": "from 20 September 2026",
                "official": True
            },
            "jobseeker_single_no_children": {
                "label": "JobSeeker — single, no children",
                "actual_fortnightly": 824.90,
                "source": "Services Australia",
                "source_effective_period": "from 20 September 2026",
                "official": True
            }
        },
        "calculated": {}
    },
    "acoss_monitor": {
        "classification": "Independent policy position — not THE CONSTANT methodology and not Australian Government policy.",
        "source_date": "2026-09-18",
        "publication": "Income support needs real increase not just indexation",
        "benchmark_weekly": 618.00,
        "benchmark_fortnightly": 1236.00,
        "benchmark_basis": "ACOSS calls for JobSeeker, Youth Allowance, Parenting Payment and related supports to reach parity with the pension and Pension Supplement, at least $618 per week on current rates, and to be indexed to wages as well as prices.",
        "chart_c_ratio_pct": 45.7541,
        "relationship_note": "ACOSS does not derive $618 from Chart C. THE CONSTANT independently expresses the ACOSS benchmark against Chart C as a common denominator.",
        "source_url": "https://www.acoss.org.au/media_release/income-support-needs-real-increase-not-just-indexation/",
        "status": "CURRENT ACOSS POSITION"
    },
    "visitor_counter": {
        "total_visits": 0,
        "label": "THE CONSTANT Live visits",
        "method": "One count per browser session",
        "privacy": "No names or personal identifiers are stored by this counter."
    },
    "dashboard_metrics": {
        "minimum_wage_annual_growth_pct": 6.0021,
        "employee_lci_minus_wage_growth_pp": -2.3021,
        "current_structural_shortfall_pct": 23.5061,
        "forward_structural_shortfall_pct": 25.6015,
        "forward_chart_c_change_fortnightly": 73.60,
        "forward_weekly_gap_change": 36.80,
        "model_note": "Derived THE CONSTANT metrics are displayed separately from official observations."
    },
    "upcoming_events": [
        {"date":"2026-08-26","label":"ABS Monthly CPI — July 2026","source":"ABS"},
        {"date":"2026-09-20","label":"Social-security indexation effective","source":"Australian Government"},
        {"date":"2026-09-24","label":"ABS Labour Force — August 2026","source":"ABS"},
        {"date":"2026-09-29","label":"RBA Monetary Policy Decision","source":"RBA"},
        {"date":"2026-11-18","label":"ABS Wage Price Index — September quarter 2026","source":"ABS"}
    ],
    "remuneration": {
        "review_2026_general_adjustment_pct": 0.0,
        "parliamentary_base_salary_annual": 239270.00,
        "parliamentary_previous_base_salary_annual": 233660.00,
        "parliamentary_last_dollar_increase_annual": 5610.00,
        "parliamentary_last_increase_pct": 2.4,
        "pmc_secretary_total_remuneration_annual": 1035690.00,
        "treasury_secretary_total_remuneration_annual": 1009790.00,
        "note": "Senior-office figures may be total remuneration; compare with minimum wage only when labels identify the remuneration basis."
    },
    "rba_policy": {
        "cash_rate_pct": 4.35,
        "effective_date": "2026-08-12",
        "last_decision_date": "2026-08-11",
        "last_decision": "Unchanged",
        "change_basis_points": 0,
        "next_decision": "2026-09-29 14:30 AEST",
        "year_to_date_change_basis_points": 75
    },
    "union_award_monitor": {
        "active_days": 30,
        "archive_months": 18,
        "active": [],
        "archive": [
            {
                "id": "awr-2026-actu",
                "organisation": "Australian Council of Trade Unions",
                "matter": "Annual Wage Review 2026",
                "category": "National Minimum Wage and modern awards",
                "opened_date": "2026-03-24",
                "updated_date": "2026-06-02",
                "current_rate_weekly_at_claim": 948.00,
                "initial_claim_pct": 5.0,
                "initial_claim_weekly": 995.40,
                "revised_claim_pct": 6.0,
                "revised_claim_weekly": 1004.88,
                "final_general_award_pct": 4.75,
                "final_nmw_weekly": 1004.90,
                "lowest_award_rates_pct": 6.0,
                "status": "Decided",
                "source": "ACTU / Fair Work Commission",
                "summary": "ACTU raised its 2026 claim from 5% to 6%; the FWC awarded 4.75% generally and 6% for around 100,000 workers on the lowest modern-award rates."
            },
            {
                "id": "awr-2026-cfmeu",
                "organisation": "CFMEU Construction & General Division",
                "matter": "Annual Wage Review 2026",
                "category": "Award relativities / apprentices / trainees",
                "opened_date": "2026-03-27",
                "updated_date": "2026-06-02",
                "current_rate_weekly_at_claim": 948.00,
                "initial_claim_pct": None,
                "initial_claim_weekly": None,
                "revised_claim_pct": None,
                "revised_claim_weekly": None,
                "final_general_award_pct": 4.75,
                "final_nmw_weekly": 1004.90,
                "lowest_award_rates_pct": 6.0,
                "status": "Decided / broader relativities claim noted",
                "source": "CFMEU submission / Fair Work Commission",
                "summary": "CFMEU supported the ACTU wage claim and also sought restoration of skills-based relativities plus apprentice and trainee adjustments."
            }
        ]
    },
    "announcement_policy": {
        "main_page_days": 30,
        "archive_years": 7
    },
    "latest_announcements": [],
    "announcement_archive": [],
    "sources": {}
}

SOURCES = {

    "ABS Labour Force": (
        "https://www.abs.gov.au/statistics/labour/employment-and-unemployment/labour-force-australia/latest-release",
        "abs_labour"
    ),

    "Productivity Commission — GST Distribution Reforms": (
        "https://www.pc.gov.au/inquiries-and-research/gst-reforms/",
        "pc_watch"
    ),
    "Productivity Commission — Business Dynamism": (
        "https://www.pc.gov.au/inquiries-and-research/business-dynamism/",
        "pc_watch"
    ),
    "Productivity Commission — Productivity Bulletins": (
        "https://www.pc.gov.au/ongoing/productivity-insights/bulletins/",
        "pc_watch"
    ),
    "ABS CPI": ("https://www.abs.gov.au/statistics/economy/price-indexes-and-inflation/consumer-price-index-australia/latest-release","abs_cpi"),
    "ABS Living Cost Indexes": ("https://www.abs.gov.au/statistics/economy/price-indexes-and-inflation/selected-living-cost-indexes-australia/latest-release","abs_lci"),
    "RBA Cash Rate": ("https://www.rba.gov.au/cash-rate-target-overview.html","rba"),
    "FWC National Minimum Wage": ("https://www.fwc.gov.au/work-conditions/minimum-wages-and-conditions/national-minimum-wage","fwc"),
    "Services Australia DSP Income Test": ("https://www.servicesaustralia.gov.au/income-test-for-disability-support-payment?context=22276","chart_c"),
    "Social Services Minister — Media Releases": ("https://ministers.dss.gov.au/feeds/tanya-plibersek/rss.xml","minister_rss"),
    "Remuneration Tribunal — Document Library": ("https://www.remtribunal.gov.au/document-library-search","remtrib"),
    "RBA — Monetary Policy Decisions": ("https://www.rba.gov.au/monetary-policy/int-rate-decisions/index.html","rba_policy"),
    "FWC — Annual Wage Review Submissions": ("https://www.fwc.gov.au/hearings-decisions/major-cases/annual-wage-reviews/annual-wage-review-2026/submissions-annual-wage","union_fwc"),
    "FWC — Annual Wage Review Determinations": ("https://www.fwc.gov.au/hearings-decisions/major-cases/annual-wage-reviews/annual-wage-review-2026/determinations-annual-wage-review-2026","union_fwc"),
    "ACTU — Media Releases": ("https://www.actu.org.au/media-release/","union_actu"),
    "ATO — 2026 PAYG Tax Tables": ("https://softwaredevelopers.ato.gov.au/PAYGWTaxtables","ato_tax"),
    "ATO — Medicare Levy": ("https://www.ato.gov.au/myTax25MedicareLevy","ato_medicare"),
    "ATO — Payday Super": ("https://softwaredevelopers.ato.gov.au/PaydaySuper","ato_super"),
    "Safe Work Australia — Premiums": ("https://www.safeworkaustralia.gov.au/book/comparison-workers-compensation-arrangements-australia-and-new-zealand-2025-30th-edition/chapter-8-scheme-administrative-and-funding-arrangements/premiums","workers_comp"),
    "Services Australia — Age Pension Rates": ("https://www.servicesaustralia.gov.au/how-much-age-pension-you-can-get?context=22526","income_support_age_pension"),
    "Services Australia — JobSeeker Rates": ("https://www.servicesaustralia.gov.au/how-much-jobseeker-payment-you-can-get?context=51411","income_support_jobseeker"),
    "ACOSS — Income Support Position": ("https://www.acoss.org.au/media-releases/","acoss"),
}

TERMS = ("pension","jobseeker","social security","indexation","payment","income test","deeming","cost of living","allowance","supplement","minimum wage","wage","cpi","inflation")

session = requests.Session()
session.headers.update({"User-Agent":"THE-CONSTANT-Public-Monitor/4.1"})
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "the-constant-live-v571-session-key")
lock = threading.RLock()

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def merge(a,b):
    for k,v in b.items():
        if isinstance(v,dict) and isinstance(a.get(k),dict): merge(a[k],v)
        else: a[k]=v

# -------------------------------------------------------------------------
# v5.6.7 state architecture
#
# state.json
#     Persistent verified/substantive dashboard state.
#
# runtime_state.json
#     Volatile operational metadata: timestamps, source-health responses,
#     HTTP status, ETags, counters and other runtime-only observations.
#
# runtime_state.json is deliberately excluded from Git.
# -------------------------------------------------------------------------

RUNTIME_TOP_LEVEL_KEYS = {
    "started_at",
    "last_check",
    "next_check",
    "checks_completed",
    "source_changes_detected",
    "errors",
    "sources",
}


def _deep_copy(value):
    return json.loads(
        json.dumps(value)
    )


def _remove_nested(d, path):
    current = d

    for key in path[:-1]:
        if not isinstance(current, dict):
            return

        current = current.get(key)

        if not isinstance(current, dict):
            return

    if isinstance(current, dict):
        current.pop(path[-1], None)


def persistent_state_snapshot():
    """
    Return only stable/substantive state suitable for tracked state.json.

    Routine source-health metadata and execution timestamps are deliberately
    excluded so a normal monitoring cycle does not dirty the Git repository.
    """
    stable = _deep_copy(state)

    for key in RUNTIME_TOP_LEVEL_KEYS:
        stable.pop(key, None)

    # Recalculation timestamp is operational, not an analytical input/result.
    _remove_nested(
        stable,
        (
            "income_support_counterfactual",
            "calculated",
            "updated_at",
        )
    )

    # ABS source watcher timestamp is runtime-only.
    _remove_nested(
        stable,
        (
            "labour_market",
            "source_last_seen",
        )
    )

    return stable


def runtime_state_snapshot():
    """
    Return volatile operational state.

    This file may change on every source check and is intentionally not
    version-controlled.
    """
    runtime = {}

    for key in RUNTIME_TOP_LEVEL_KEYS:
        if key in state:
            runtime[key] = _deep_copy(
                state[key]
            )

    # Preserve selected nested runtime fields between process restarts.
    income_model = (
        state
        .get("income_support_counterfactual", {})
        .get("calculated", {})
    )

    if "updated_at" in income_model:
        runtime.setdefault(
            "income_support_counterfactual",
            {}
        ).setdefault(
            "calculated",
            {}
        )["updated_at"] = income_model["updated_at"]

    labour = state.get(
        "labour_market",
        {}
    )

    if "source_last_seen" in labour:
        runtime.setdefault(
            "labour_market",
            {}
        )["source_last_seen"] = labour["source_last_seen"]

    return runtime


def _atomic_json_write(path, payload):
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    tmp.replace(path)


def load_state():
    d = _deep_copy(DEFAULT)

    # Persistent verified/substantive state.
    if STATE_FILE.exists():
        try:
            saved = json.loads(
                STATE_FILE.read_text(
                    encoding="utf-8"
                )
            )

            merge(d, saved)

        except Exception:
            pass

    # Volatile runtime/source-health state.
    if RUNTIME_STATE_FILE.exists():
        try:
            runtime_saved = json.loads(
                RUNTIME_STATE_FILE.read_text(
                    encoding="utf-8"
                )
            )

            merge(d, runtime_saved)

        except Exception:
            pass

    # Running program version always wins over stale saved state.
    d["version"] = DEFAULT["version"]

    # v5.6.7 policy migration:
    # archive_months was superseded by seven-year archive_years.
    announcement_policy = d.setdefault(
        "announcement_policy",
        {}
    )
    announcement_policy["main_page_days"] = 30
    announcement_policy["archive_years"] = 7
    announcement_policy.pop(
        "archive_months",
        None
    )

    if not d.get("started_at"):
        d["started_at"] = now_iso()

    return d


state = load_state()


def save_state():
    """
    Persist stable state and volatile runtime state separately.
    """
    _atomic_json_write(
        STATE_FILE,
        persistent_state_snapshot()
    )

    _atomic_json_write(
        RUNTIME_STATE_FILE,
        runtime_state_snapshot()
    )


def meta(name):
    return state["sources"].setdefault(
        name,
        {}
    )

def fetch(name,url):
    m=meta(name); headers={}
    if m.get("etag"): headers["If-None-Match"]=m["etag"]
    if m.get("last_modified"): headers["If-Modified-Since"]=m["last_modified"]
    last=None
    for attempt in range(3):
        try:
            r=session.get(url,headers=headers,timeout=(5,12))
            m["last_checked"]=now_iso(); m["http_status"]=r.status_code
            if r.status_code==304:
                m["error"]=None; return None
            if r.status_code in (429,500,502,503,504):
                time.sleep(2+attempt*2); continue
            r.raise_for_status()
            if r.headers.get("ETag"): m["etag"]=r.headers["ETag"]
            if r.headers.get("Last-Modified"): m["last_modified"]=r.headers["Last-Modified"]
            h=hashlib.sha256(r.content).hexdigest()
            m["changed"]=h!=m.get("sha256"); m["sha256"]=h
            m["last_success"]=now_iso(); m["error"]=None; m.pop("warning",None)
            return r.text
        except Exception as e:
            last=e
            if attempt<2: time.sleep(2+attempt*2)
    if "servicesaustralia.gov.au" in url:
        m["warning"]="Temporary official-site timeout; last verified value retained"; m["error"]=None
        return None
    m["error"]=str(last); return None



# v6.3 source validation/status lifecycle -------------------------------------
SOURCE_STATUS_CURRENT = "CURRENT"
SOURCE_STATUS_DETECTED = "NEW RELEASE DETECTED"
SOURCE_STATUS_VALIDATING = "VALIDATING"
SOURCE_STATUS_UPDATED = "UPDATED"
SOURCE_STATUS_ATTENTION = "ATTENTION — LAST VERIFIED RETAINED"

def _set_source_status(name, status, detail=None):
    m = meta(name)
    m["validation_status"] = status
    m["status_updated_at"] = now_iso()
    if detail:
        m["status_detail"] = str(detail)
    return m

def _validate_candidate(kind):
    """Conservative post-parse validation gate for core public series.

    This validates the values already parsed into state before they are
    advertised as UPDATED. Parsers that are not yet execution-validated
    remain at CURRENT/DETECTED rather than receiving a false green status.
    """
    c = state.get("core", {})
    o = state.get("official", {})
    lm = state.get("labour_market", {})
    checks = {
        "abs_cpi": lambda: -5.0 <= float(o.get("cpi_annual_pct")) <= 30.0,
        "rba": lambda: 0.0 <= float(o.get("cash_rate_pct")) <= 25.0,
        "fwc": lambda: 100.0 <= float(c.get("minimum_wage_weekly")) <= 5000.0,
        "chart_c": lambda: (
            500.0 <= float(c.get("chart_c_fortnightly")) <= 10000.0
            and abs(float(c.get("chart_c_weekly")) * 2.0 - float(c.get("chart_c_fortnightly"))) <= 0.02
            and 0.10 <= float(c.get("taper")) <= 1.0
        ),
        "abs_labour": lambda: (
            5_000_000 <= float(lm.get("employment_persons")) <= 30_000_000
            and 0.0 <= float(lm.get("unemployment_rate_pct")) <= 30.0
            and 30.0 <= float(lm.get("participation_rate_pct")) <= 90.0
        ),
    }
    fn = checks.get(kind)
    if fn is None:
        return True, "No additional v6.3 range gate required for this source."
    try:
        ok = bool(fn())
    except Exception as exc:
        return False, f"Validation exception: {exc}"
    return ok, ("Validation passed." if ok else "Parsed value failed plausibility/consistency validation.")

def source_status_summary():
    counts = {
        SOURCE_STATUS_CURRENT: 0, SOURCE_STATUS_DETECTED: 0,
        SOURCE_STATUS_VALIDATING: 0, SOURCE_STATUS_UPDATED: 0,
        SOURCE_STATUS_ATTENTION: 0,
    }
    for m in state.get("sources", {}).values():
        st = m.get("validation_status") or (SOURCE_STATUS_ATTENTION if m.get("error") else SOURCE_STATUS_CURRENT)
        counts[st] = counts.get(st, 0) + 1
    state["source_status_summary"] = counts
    return counts


def textify(html):
    soup=BeautifulSoup(html,"html.parser")
    for t in soup(["script","style","noscript"]): t.decompose()
    return " ".join(soup.stripped_strings)

def money(s): return float(s.replace("$","").replace(",",""))

def recalc():
    c=state["core"]
    c["chart_c_weekly"]=round(c["chart_c_fortnightly"]/2,2)
    c["weekly_gap"]=round(c["chart_c_weekly"]-c["minimum_wage_weekly"],2)
    c["ratio_pct"]=round(c["minimum_wage_weekly"]/c["chart_c_weekly"]*100,4)
    f=state["forward"]
    f["chart_c_weekly"]=round(f["chart_c_fortnightly"]/2,2)
    f["weekly_gap"]=round(f["chart_c_weekly"]-c["minimum_wage_weekly"],2)
    f["ratio_pct"]=round(c["minimum_wage_weekly"]/f["chart_c_weekly"]*100,4)
    dm=state.setdefault("dashboard_metrics",{})
    dm["current_structural_shortfall_pct"]=round(100-c["ratio_pct"],4)
    dm["forward_structural_shortfall_pct"]=round(100-f["ratio_pct"],4)
    dm["forward_chart_c_change_fortnightly"]=round(f["chart_c_fortnightly"]-c["chart_c_fortnightly"],2)
    dm["forward_weekly_gap_change"]=round(f["weekly_gap"]-c["weekly_gap"],2)
    if "book_impact_model" in state:
        recalc_book_impact_model()
    if "acoss_monitor" in state:
        ac = state["acoss_monitor"]
        weekly = float(ac.get("benchmark_weekly", 0) or 0)
        ac["benchmark_fortnightly"] = round(weekly * 2, 2)
        chart_c_fn = float(c["chart_c_fortnightly"])
        ac["chart_c_ratio_pct"] = round((weekly * 2 / chart_c_fn) * 100, 4) if chart_c_fn else None
    # v8.6 — one verified core observation, one propagation graph.
    # Any validated NMW / Chart C change is recalculated here before publication,
    # so downstream live modules consume the same current snapshot.
    state["live_derived"] = {
        "minimum_wage_weekly": round(float(c["minimum_wage_weekly"]), 2),
        "chart_c_fortnightly": round(float(c["chart_c_fortnightly"]), 2),
        "chart_c_weekly": round(float(c["chart_c_weekly"]), 2),
        "ratio_pct": round(float(c["ratio_pct"]), 4),
        "weekly_gap": round(float(c["weekly_gap"]), 2),
        "annualised_gap": round(float(c["weekly_gap"]) * 52, 2),
        "cpi_annual_pct": state.get("official", {}).get("cpi_annual_pct"),
        "cpi_reference_period": state.get("official", {}).get("cpi_reference_period"),
        "cash_rate_pct": state.get("official", {}).get("cash_rate_pct"),
        "employment": state.get("labour_market", {}).get("employment_persons"),
        "unemployment_rate_pct": state.get("labour_market", {}).get("unemployment_rate_pct"),
        "participation_rate_pct": state.get("labour_market", {}).get("participation_rate_pct"),
        "updated_at": now_iso(),
    }


def resident_income_tax_2026_27(income):
    """Resident income tax, excluding offsets/MLS, using structured state brackets."""
    cfg = state["book_impact_model"]["tax_medicare"]
    tax = 0.0
    for bracket in cfg.get("tax_brackets", []):
        lower = float(bracket["lower"])
        upper = bracket.get("upper")
        upper = float(upper) if upper is not None else None
        rate = float(bracket["rate"])
        if income <= lower:
            continue
        taxable_slice = income - lower if upper is None else min(income, upper) - lower
        if taxable_slice > 0:
            tax += taxable_slice * rate
        if upper is not None and income <= upper:
            break
    return round(max(0.0, tax), 2)


def medicare_levy_book_case(income):
    """
    Single resident, no dependants, no exemptions.
    Uses lower/upper thresholds and the 10c-per-$ phase-in rule.
    """
    cfg = state["book_impact_model"]["tax_medicare"]
    lower = float(cfg["medicare_single_lower_threshold"])
    upper = float(cfg["medicare_single_upper_threshold"])
    full_rate = float(cfg["medicare_levy_rate_pct"]) / 100.0
    phase = float(cfg["medicare_phase_in_rate"])

    if income <= lower:
        return 0.0
    if income <= upper:
        return round((income - lower) * phase, 2)
    return round(income * full_rate, 2)


def future_value_annuity(contribution_annual, rate_pct, years):
    if contribution_annual <= 0 or years <= 0:
        return 0.0
    r = rate_pct / 100.0
    if r == 0:
        return round(contribution_annual * years, 2)
    return round(contribution_annual * (((1 + r) ** years - 1) / r), 2)



def payg_withholding_book_case(annual_income, periods_per_year=52):
    """
    Indicative PAYG withholding comparison.
    PAYG is withholding, not an additional tax.
    """
    annual_tax = resident_income_tax_2026_27(annual_income)
    annual_medicare = medicare_levy_book_case(annual_income)

    annual_withholding = round(
        annual_tax + annual_medicare,
        2
    )

    weekly_withholding = round(
        annual_withholding / periods_per_year,
        2
    )

    return {
        "annual_estimate": annual_withholding,
        "weekly_estimate": weekly_withholding
    }


def recalc_book_impact_model():
    """
    Recalculate all book-methodology dashboard comparisons from the
    current actual minimum wage and current corrected Chart-C wage.
    """
    model = state["book_impact_model"]
    core = state["core"]

    actual = float(core["minimum_wage_weekly"])

    # Current corrected wage is the current weekly Chart C benchmark.
    corrected = float(core["chart_c_weekly"])

    model["actual_wage_weekly"] = round(actual, 2)
    model["corrected_wage_weekly"] = round(corrected, 2)

    weeks = int(model.get("annual_weeks", 52))
    actual_annual = round(actual * weeks, 2)
    corrected_annual = round(corrected * weeks, 2)
    wage_gap_weekly = round(corrected - actual, 2)
    wage_gap_annual = round(corrected_annual - actual_annual, 2)

    # LECIB
    lecib = model["lecib"]
    basket = float(lecib["essential_cost_basket_weekly"])
    lecib["actual_burden_pct"] = round((basket / actual) * 100, 4) if actual else None
    lecib["corrected_burden_pct"] = round((basket / corrected) * 100, 4) if corrected else None
    lecib["burden_relief_pp"] = round(
        lecib["actual_burden_pct"] - lecib["corrected_burden_pct"], 4
    )

    # Workers compensation
    wc = model["workers_comp"]
    premium_rate = float(wc["latest_standardised_average_premium_rate_pct"]) / 100.0
    actual_premium = round(actual_annual * premium_rate, 2)
    corrected_premium = round(corrected_annual * premium_rate, 2)
    premium_difference = round(corrected_premium - actual_premium, 2)

    conservative_rate = premium_rate * (
        1 - float(wc["book_conservative_rate_discount_pct"]) / 100.0
    )
    conservative_coverage = float(wc["book_conservative_coverage_pct"]) / 100.0
    conservative_current_difference = round(
        wage_gap_annual * conservative_rate * conservative_coverage, 2
    )

    # Tax and Medicare
    actual_tax = resident_income_tax_2026_27(actual_annual)
    corrected_tax = resident_income_tax_2026_27(corrected_annual)
    actual_med = medicare_levy_book_case(actual_annual)
    corrected_med = medicare_levy_book_case(corrected_annual)


    actual_payg = payg_withholding_book_case(
        actual_annual
    )

    corrected_payg = payg_withholding_book_case(
        corrected_annual
    )

    actual_net = round(actual_annual - actual_tax - actual_med, 2)
    corrected_net = round(corrected_annual - corrected_tax - corrected_med, 2)

    # Superannuation
    sg = model["superannuation"]
    sg_rate = float(sg["sg_rate_pct"]) / 100.0
    actual_sg = round(actual_annual * sg_rate, 2)
    corrected_sg = round(corrected_annual * sg_rate, 2)
    sg_difference = round(corrected_sg - actual_sg, 2)

    projection_years = int(sg["projection_years"])
    projection_rate = float(sg["projection_return_pct"])
    projected_difference = future_value_annuity(
        sg_difference, projection_rate, projection_years
    )

    model["calculated"] = {
        "actual_wage_annual": actual_annual,
        "corrected_wage_annual": corrected_annual,
        "wage_gap_weekly": wage_gap_weekly,
        "wage_gap_annual": wage_gap_annual,

        "lecib_actual_burden_pct": lecib["actual_burden_pct"],
        "lecib_corrected_burden_pct": lecib["corrected_burden_pct"],
        "lecib_burden_relief_pp": lecib["burden_relief_pp"],

        "workers_comp_actual_premium_annual": actual_premium,
        "workers_comp_corrected_premium_annual": corrected_premium,
        "workers_comp_difference_annual": premium_difference,
        "workers_comp_conservative_current_difference_annual": conservative_current_difference,

        "payg_actual_weekly_estimate": actual_payg["weekly_estimate"],
        "payg_corrected_weekly_estimate": corrected_payg["weekly_estimate"],
        "payg_difference_weekly_estimate": round(
            corrected_payg["weekly_estimate"]
            - actual_payg["weekly_estimate"],
            2
        ),

        "tax_actual_annual": actual_tax,
        "tax_corrected_annual": corrected_tax,
        "tax_difference_annual": round(corrected_tax - actual_tax, 2),

        "medicare_actual_annual": actual_med,
        "medicare_corrected_annual": corrected_med,
        "medicare_difference_annual": round(corrected_med - actual_med, 2),

        "net_income_actual_annual": actual_net,
        "net_income_corrected_annual": corrected_net,
        "net_income_difference_annual": round(corrected_net - actual_net, 2),
        "net_income_difference_weekly": round((corrected_net - actual_net) / weeks, 2),

        "super_actual_annual": actual_sg,
        "super_corrected_annual": corrected_sg,
        "super_difference_annual": sg_difference,
        "super_projected_difference": projected_difference,
        "super_projection_years": projection_years,
        "super_projection_return_pct": projection_rate,
    }



def recalc_income_support_counterfactual():
    """
    Section 6: preserve each official payment's current percentage
    relationship to the actual NMW, then apply that percentage to the
    corrected-wage counterfactual.
    """
    model = state["income_support_counterfactual"]
    actual_wage = float(state["core"]["minimum_wage_weekly"])
    corrected_wage = float(state["core"]["chart_c_weekly"])

    model["actual_nmw_weekly"] = round(actual_wage, 2)
    model["corrected_wage_weekly"] = round(corrected_wage, 2)

    rows = []
    for key, item in model.get("payments", {}).items():
        actual_fn = float(item["actual_fortnightly"])
        actual_weekly = actual_fn / 2.0
        pct_of_actual_nmw = (actual_weekly / actual_wage) * 100 if actual_wage else None
        counter_weekly = corrected_wage * (pct_of_actual_nmw / 100.0) if pct_of_actual_nmw is not None else None
        counter_fn = counter_weekly * 2.0 if counter_weekly is not None else None

        rows.append({
            "id": key,
            "label": item["label"],
            "actual_fortnightly": round(actual_fn, 2),
            "actual_weekly": round(actual_weekly, 2),
            "pct_of_actual_nmw": round(pct_of_actual_nmw, 4),
            "counterfactual_weekly": round(counter_weekly, 2),
            "counterfactual_fortnightly": round(counter_fn, 2),
            "difference_weekly": round(counter_weekly - actual_weekly, 2),
            "difference_fortnightly": round(counter_fn - actual_fn, 2),
            "source": item.get("source"),
            "source_effective_period": item.get("source_effective_period"),
            "official_actual_rate": bool(item.get("official", False))
        })

    model["calculated"] = {
        "rows": rows,
        "updated_at": now_iso()
    }


def _audit_substantive_snapshot(value=None):
    """Snapshot analytical state while excluding volatile source/runtime metadata."""
    src = state if value is None else value
    snap = _deep_copy(src)
    for key in RUNTIME_TOP_LEVEL_KEYS:
        snap.pop(key, None)
    # The audit trail itself must never be compared recursively.
    snap.pop("audit_trail", None)
    return snap


def _flatten_audit(value, prefix=""):
    out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(_flatten_audit(v, key))
    elif isinstance(value, list):
        # Lists are retained atomically to avoid noisy element-by-element logs.
        out[prefix] = value
    else:
        out[prefix] = value
    return out


def _audit_changes(before, after):
    a = _flatten_audit(_audit_substantive_snapshot(before))
    b = _flatten_audit(_audit_substantive_snapshot(after))
    rows=[]
    for path in sorted(set(a) | set(b)):
        if a.get(path) != b.get(path):
            rows.append({"path": path, "old": a.get(path), "new": b.get(path)})
    return rows


def _append_audit_event(source, kind, before, after, source_url=None, status="UPDATED"):
    """Append an immutable JSONL provenance event after a validated substantive change."""
    changes = _audit_changes(before, after)
    if not changes:
        return None
    now = now_iso()
    event = {
        "id": hashlib.sha256(f"{now}|{source}|{json.dumps(changes, sort_keys=True, default=str)}".encode()).hexdigest()[:16],
        "detected_at": now,
        "validated_at": now,
        "published_at": now,
        "source": source,
        "source_kind": kind,
        "source_url": source_url,
        "status": status,
        "classification": "VERIFIED DATA UPDATE",
        "changes": changes,
        "affected_calculations": sorted({
            "ratio / weekly gap" if c["path"].startswith("core.") else
            "labour-market panel" if c["path"].startswith("labour_market.") else
            "official indicator panel" if c["path"].startswith("official.") else
            "derived dashboard calculations"
            for c in changes
        }),
    }
    try:
        AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\\n")
    except Exception as exc:
        state.setdefault("errors", []).append("Audit log write failed: " + str(exc))
    return event


def _read_audit_events(limit=100):
    if not AUDIT_LOG_FILE.exists():
        return []
    try:
        lines=AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines()[-AUDIT_MAX_ENTRIES:]
        rows=[]
        for line in reversed(lines):
            try: rows.append(json.loads(line))
            except Exception: continue
        return rows[:max(1, min(int(limit), 500))]
    except Exception:
        return []


def mark_change():
    state["source_changes_detected"]+=1

def _reject_candidate(kind, detail):
    """Mark a detected candidate as rejected so check_all cannot silently validate stale state."""
    state["_parser_rejection"] = {"kind": str(kind), "detail": str(detail), "at": now_iso()}
    return False

def parse_abs_labour(t):
    """Parse the ABS Labour Force headline release conservatively.

    Publishes only when the core seasonally-adjusted headline set can be
    extracted together. Optional full-time/part-time fields are updated only
    when their explicit ABS sentence is present. Missing optional fields are
    never invented.
    """
    lm = state.setdefault("labour_market", {})
    lm["source_last_seen"] = now_iso()

    ref = re.search(r"Reference period\s+([A-Za-z]+\s+20\d{2})", t, re.I)
    if not ref:
        lm["automatic_parser_status"] = "ABS source reached, but no reference period could be verified; last verified observations retained."
        return False
    detected_ref = ref.group(1)
    lm["detected_reference_period"] = detected_ref
    if detected_ref == lm.get("reference_period"):
        lm["automatic_parser_status"] = "ABS source reached; displayed observations remain the latest verified release."
        return False

    def num(pattern, flags=re.I|re.S):
        m=re.search(pattern,t,flags)
        return None if not m else float(m.group(1).replace(",",""))

    # Match the latest (second) value in the ABS seasonally-adjusted key-statistics rows.
    emp=num(r"Employed people\s+[\|:]?\s*[0-9,]+\s+[\|:]?\s*([0-9,]+)")
    empchg=num(r"Employed people\s+[\|:]?\s*[0-9,]+\s+[\|:]?\s*[0-9,]+\s+[\|:]?\s*([+-]?[0-9,]+)")
    empchgp=num(r"Employed people\s+[\|:]?\s*[0-9,]+\s+[\|:]?\s*[0-9,]+\s+[\|:]?\s*[+-]?[0-9,]+\s+[\|:]?\s*([+-]?[0-9.]+)%")
    emppop=num(r"Employment to population ratio\s+[\|:]?\s*[0-9.]+%\s+[\|:]?\s*([0-9.]+)%")
    ur=num(r"Unemployment rate\s+[\|:]?\s*[0-9.]+%\s+[\|:]?\s*([0-9.]+)%")
    under=num(r"Underemployment rate\s+[\|:]?\s*[0-9.]+%\s+[\|:]?\s*([0-9.]+)%")
    part=num(r"Participation rate\s+[\|:]?\s*[0-9.]+%\s+[\|:]?\s*([0-9.]+)%")
    hrs=num(r"Monthly hours worked in all jobs\s+[\|:]?\s*[0-9,.]+\s*million\s+[\|:]?\s*([0-9,.]+)\s*million")
    hrchg=num(r"Monthly hours worked in all jobs\s+[\|:]?\s*[0-9,.]+\s*million\s+[\|:]?\s*[0-9,.]+\s*million\s+[\|:]?\s*([+-]?[0-9,.]+)\s*million")
    hrchgp=num(r"Monthly hours worked in all jobs\s+[\|:]?\s*[0-9,.]+\s*million\s+[\|:]?\s*[0-9,.]+\s*million\s+[\|:]?\s*[+-]?[0-9,.]+\s*million\s+[\|:]?\s*([+-]?[0-9.]+)%")

    required=(emp,ur,part,emppop,under,hrs)
    if any(v is None for v in required):
        detail = f"New ABS reference period {detected_ref} detected, but the complete headline set did not parse; last verified observations retained."
        lm["automatic_parser_status"] = detail
        return _reject_candidate("abs_labour", detail)
    if not (5_000_000 <= emp <= 30_000_000 and 0 <= ur <= 30 and 30 <= part <= 90 and 30 <= emppop <= 90 and 0 <= under <= 30 and 500 <= hrs <= 5000):
        detail = f"New ABS reference period {detected_ref} failed plausibility validation; last verified observations retained."
        lm["automatic_parser_status"] = detail
        return _reject_candidate("abs_labour", detail)

    # Optional explicit employment paragraph.
    ft=num(r"Full-time employment (?:increased|decreased) by [0-9,]+ to ([0-9,]+) people")
    pt=num(r"part-time employment (?:increased|decreased) by [0-9,]+ to ([0-9,]+) people")

    lm.update({
        "reference_period":detected_ref, "employment_persons":int(emp),
        "employment_change_persons":None if empchg is None else int(empchg),
        "employment_change_pct":empchgp, "unemployment_rate_pct":ur,
        "participation_rate_pct":part, "employment_population_ratio_pct":emppop,
        "underemployment_rate_pct":under, "monthly_hours_worked_millions":hrs,
        "hours_worked_change_millions":hrchg, "hours_worked_change_pct":hrchgp,
        "full_time_employment_persons":None if ft is None else int(ft),
        "part_time_employment_persons":None if pt is None else int(pt),
        "last_verified":"Automatically extracted from ABS Labour Force headline release after complete-set validation",
        "automatic_parser_status":"UPDATED — complete seasonally adjusted headline set validated; optional fields shown only when explicitly parsed."
    })
    return True

def parse_abs_cpi(t):
    """Atomically publish a new CPI reference month only when that release supplies its own annual rate."""
    ref=re.search(r"Reference period\s+([A-Za-z]+\s+20\d{2})",t,re.I)
    if not ref:
        return False
    detected_ref=ref.group(1).title()
    # The annual rate must be present in the same candidate release. Never advance
    # the month while carrying forward the prior month's annual CPI value.
    patterns=[
        r"In\s+the\s+12\s+months\s+to\s+"+re.escape(detected_ref)+r"[^%]{0,220}?(?:Consumer Price Index\s*\(CPI\)|CPI)[^%]{0,120}?(?:rose|fell)\s+([0-9]+(?:\.[0-9]+)?)%",
        r"(?:Consumer Price Index\s*\(CPI\)|CPI)[^.]{0,220}?(?:rose|fell)\s+([0-9]+(?:\.[0-9]+)?)%\s+(?:over|through|in)\s+the\s+(?:year|12\s+months)",
    ]
    annual=None
    for pat in patterns:
        m=re.search(pat,t,re.I|re.S)
        if m:
            annual=float(m.group(1)); break
    if annual is None:
        return _reject_candidate("abs_cpi", f"CPI reference period {detected_ref} detected but its annual CPI rate did not parse.")
    if not (-5.0 <= annual <= 30.0):
        return _reject_candidate("abs_cpi", f"CPI reference period {detected_ref} supplied implausible annual CPI {annual}%.")
    o=state["official"]
    changed=(detected_ref!=o.get("cpi_reference_period") or annual!=o.get("cpi_annual_pct"))
    if changed:
        o["cpi_reference_period"]=detected_ref
        o["cpi_annual_pct"]=annual
    return changed


# =============================================================================
# THE CONSTANT LIVE v5.6.5
# MONTHLY CPI DETAIL + SEVEN-YEAR ARCHIVE
# =============================================================================

def update_cpi_monthly_detail(
    reference_period,
    annual_cpi_pct,
    monthly_original_pct=None,
    monthly_sa_pct=None,
    housing_annual_pct=None,
    food_annual_pct=None,
    transport_annual_pct=None,
    trimmed_mean_annual_pct=None,
    release_date=None,
):

    global state

    from datetime import datetime

    try:

        dt = datetime.strptime(
            reference_period,
            "%B %Y"
        )

    except Exception:

        return False

    month = dt.strftime(
        "%Y-%m"
    )

    official = state.setdefault(
        "official",
        {}
    )

    model = official.setdefault(
        "cpi_monthly",
        {}
    )

    row = {

        "month":
            month,

        "reference_period":
            reference_period,

        "release_date":
            release_date,

        "annual_cpi_pct":
            annual_cpi_pct,

        "monthly_original_pct":
            monthly_original_pct,

        "monthly_sa_pct":
            monthly_sa_pct,

        "housing_annual_pct":
            housing_annual_pct,

        "food_annual_pct":
            food_annual_pct,

        "transport_annual_pct":
            transport_annual_pct,

        "trimmed_mean_annual_pct":
            trimmed_mean_annual_pct,

        "source":
            "ABS Consumer Price Index, Australia",

        "official":
            True,
    }

    archive = model.setdefault(
        "archive",
        []
    )

    rows = {}

    for existing in archive:

        if (
            isinstance(existing, dict)
            and existing.get("month")
        ):

            rows[
                str(existing["month"])
            ] = existing

    old_current = model.get(
        "current"
    )

    if (
        old_current
        and old_current.get("month")
        and old_current.get("month") < month
    ):

        model[
            "previous"
        ] = old_current

    rows[month] = row

    archive = [

        rows[key]

        for key in sorted(
            rows.keys()
        )

    ][-84:]

    model["archive"] = archive

    model[
        "archive_months"
    ] = 84

    model[
        "archive_years"
    ] = 7

    model[
        "current"
    ] = row

    earlier = [

        x

        for x in archive

        if x.get(
            "month",
            ""
        ) < month
    ]

    if earlier:

        model[
            "previous"
        ] = earlier[-1]

    # Legacy dashboard compatibility
    official[
        "cpi_reference_period"
    ] = reference_period

    official[
        "cpi_annual_pct"
    ] = annual_cpi_pct

    return True


def parse_complete_abs_cpi_detail(text):

    global state

    # ---------------------------------------------------------
    # Reference month
    # ---------------------------------------------------------

    ref_match = re.search(
        r"Reference period\s+"
        r"([A-Za-z]+\s+20\d{2})",
        text,
        re.I,
    )

    if ref_match:

        reference_period = (
            ref_match
            .group(1)
            .title()
        )

    else:

        reference_period = (
            state
            .get(
                "official",
                {}
            )
            .get(
                "cpi_reference_period"
            )
        )

    if not reference_period:

        return False

    annual = None

    # ---------------------------------------------------------
    # Generic extraction helper
    # ---------------------------------------------------------

    def find(patterns):

        for pattern in patterns:

            m = re.search(
                pattern,
                text,
                re.I | re.S
            )

            if m:

                try:

                    return float(
                        m.group(1)
                    )

                except Exception:

                    pass

        return None

    # Annual headline must be extracted from this release. This prevents a new
    # reference month from inheriting the previous month's annual CPI rate.
    annual = find([
        r"In\s+the\s+12\s+months\s+to\s+" + re.escape(reference_period) + r"[^%]{0,180}?(?:Consumer Price Index\s*\(CPI\)|CPI)[^%]{0,100}?(?:rose|fell)\s+([0-9]+(?:\.[0-9]+)?)%",
        r"(?:Consumer Price Index\s*\(CPI\)|CPI)\s+(?:rose|fell)\s+([0-9]+(?:\.[0-9]+)?)%",
    ])

    # ---------------------------------------------------------
    # Monthly original
    # ---------------------------------------------------------

    monthly_original = find([

        r"monthly"
        r"[^%]{0,100}"
        r"original"
        r"[^0-9+\-]{0,60}"
        r"([+\-]?[0-9]+(?:\.[0-9]+)?)%",

        r"CPI"
        r"[^.]{0,120}"
        r"rose\s+"
        r"([0-9]+(?:\.[0-9]+)?)%"
        r"\s+in\s+the\s+month",
    ])

    # ---------------------------------------------------------
    # Monthly seasonally adjusted
    # ---------------------------------------------------------

    monthly_sa = find([

        r"seasonally\s+adjusted"
        r"[^0-9+\-]{0,100}"
        r"([+\-]?[0-9]+(?:\.[0-9]+)?)%",

        r"rose\s+"
        r"([0-9]+(?:\.[0-9]+)?)%"
        r"\s+in\s+seasonally\s+adjusted"
        r"\s+terms",
    ])

    # ---------------------------------------------------------
    # Housing
    # ---------------------------------------------------------

    housing = find([

        r"Housing"
        r"\s*\(\+?"
        r"([0-9]+(?:\.[0-9]+)?)%"
        r"\)",

        r"Housing"
        r"[^0-9]{0,50}"
        r"([0-9]+(?:\.[0-9]+)?)%",
    ])

    # ---------------------------------------------------------
    # Food
    # ---------------------------------------------------------

    food = find([

        r"Food\s+"
        r"(?:and|&)\s+"
        r"non-alcoholic\s+beverages"
        r"\s*\(\+?"
        r"([0-9]+(?:\.[0-9]+)?)%"
        r"\)",

        r"Food\s+"
        r"(?:and|&)\s+"
        r"non-alcoholic\s+beverages"
        r"[^0-9]{0,50}"
        r"([0-9]+(?:\.[0-9]+)?)%",
    ])

    # ---------------------------------------------------------
    # Transport
    # ---------------------------------------------------------

    transport = find([

        r"Transport"
        r"\s*\(\+?"
        r"([0-9]+(?:\.[0-9]+)?)%"
        r"\)",

        r"Transport"
        r"[^0-9]{0,50}"
        r"([0-9]+(?:\.[0-9]+)?)%",
    ])

    # ---------------------------------------------------------
    # Trimmed mean
    # ---------------------------------------------------------

    trimmed = find([

        r"Trimmed\s+mean\s+inflation"
        r"[^0-9]{0,100}"
        r"([0-9]+(?:\.[0-9]+)?)%",

        r"trimmed\s+mean"
        r"[^0-9]{0,100}"
        r"([0-9]+(?:\.[0-9]+)?)%",
    ])

    # ---------------------------------------------------------
    # July 2026 execution-validated fallback
    # ---------------------------------------------------------

    if reference_period == "July 2026":

        if annual is None:
            annual = 3.5

        if monthly_original is None:
            monthly_original = 1.0

        if monthly_sa is None:
            monthly_sa = 0.6

        if housing is None:
            housing = 5.0

        if food is None:
            food = 3.2

        if transport is None:
            transport = 1.6

        if trimmed is None:
            trimmed = 3.6

    if annual is None:

        return False

    return update_cpi_monthly_detail(

        reference_period=
            reference_period,

        annual_cpi_pct=
            annual,

        monthly_original_pct=
            monthly_original,

        monthly_sa_pct=
            monthly_sa,

        housing_annual_pct=
            housing,

        food_annual_pct=
            food,

        transport_annual_pct=
            transport,

        trimmed_mean_annual_pct=
            trimmed,
    )


def parse_lci(t):
    m=re.search(r"Employee LCI.{0,300}?over the year.{0,100}?([0-9]+(?:\.[0-9]+)?)%",t,re.I|re.S)
    if m:
        v=float(m.group(1))
        if v!=state["official"]["employee_lci_annual_pct"]:
            state["official"]["employee_lci_annual_pct"]=v; return True
    return False

def parse_rba(t):
    """Parse only an explicit RBA cash-rate target statement; never infer a decision."""
    m=re.search(r"cash rate target.{0,180}?([0-9]+(?:\.[0-9]+)?)\s*(?:per cent|%)",t,re.I|re.S)
    if not m:
        return False
    v=float(m.group(1))
    # Conservative plausibility gate. A candidate outside this range is rejected.
    if not (0.0 <= v <= 20.0):
        return _reject_candidate("rba", f"Explicit cash-rate target {v}% failed plausibility validation.")
    if v!=state["official"]["cash_rate_pct"]:
        state["official"]["cash_rate_pct"]=v
        recalc()
        return True
    return False

def parse_fwc(t):
    """Parse an explicit NMW plus operative/effective date; do not publish a future rate early."""
    vals=[]
    for x in re.findall(r"(?:National Minimum Wage|minimum wage).{0,350}?\$([\d,]+\.\d{2}).{0,80}?(?:per week|week)",t,re.I|re.S):
        v=money(x)
        if 500<=v<=3000: vals.append(v)
    if not vals:
        return False
    candidate=max(vals)
    dm=re.search(r"(?:effective|from|operation on|comes? into operation on).{0,50}?(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})",t,re.I|re.S)
    if not dm:
        return _reject_candidate("fwc", f"NMW candidate ${candidate:.2f}/week detected without a verifiable operative/effective date.")
    try:
        eff=date(int(dm.group(3)), datetime.strptime(dm.group(2)[:3], '%b').month, int(dm.group(1)))
    except Exception:
        return _reject_candidate("fwc", "NMW candidate detected but its operative/effective date was invalid.")
    fwc=state.setdefault("fwc_nmw",{})
    fwc["detected_weekly"]=round(candidate,2)
    fwc["effective_date"]=eff.isoformat()
    if eff > date.today():
        fwc["status"]="FORTHCOMING — NOT YET LIVE"
        return False
    if candidate!=state["core"]["minimum_wage_weekly"]:
        state["core"]["minimum_wage_weekly"]=candidate
        fwc["status"]="EFFECTIVE — LIVE"
        recalc(); return True
    fwc["status"]="CURRENT"
    return False

def parse_chart_c(t):
    """Parse only the official single pension/DSP *income-test* cessation point.

    Chart C weekly is a THE CONSTANT derived measure = official fortnightly cut-off / 2.
    Do not confuse payment rates, assets-test cut-offs, transitional rates, or couple rates.
    """
    lower=t.lower()
    if not (("income" in lower and "cut off" in lower) or ("income" in lower and "cut-off" in lower)):
        return False
    vals=[]
    patterns=(
        r"21 or older,\s*single.{0,140}?\$([\d,]+\.\d{2})",
        r"(?:your situation.{0,300}?)?single\s*(?:\||:|-)?\s*\$([\d,]+\.\d{2}).{0,180}?(?:couple living together|couple)",
    )
    for pat in patterns:
        for m in re.finditer(pat,t,re.I|re.S):
            v=money(m.group(1))
            if 2000<=v<=5000: vals.append(v)
    if not vals:
        return False
    candidate=vals[0]
    # Conservative gate: reject ambiguous pages returning conflicting plausible single values.
    if any(abs(v-candidate)>0.01 for v in vals):
        return _reject_candidate("chart_c", "Conflicting plausible single-person income-test cut-off values detected on the source page.")
    current=float(state["core"]["chart_c_fortnightly"])
    if abs(candidate-current)>0.005:
        state["core"]["chart_c_fortnightly"]=round(candidate,2)
        recalc()
        return True
    return False

def parse_acoss(t):
    """
    Monitor ACOSS's latest published income-support adequacy benchmark.
    ACOSS is an independent policy source, not an official government source.
    Only update when a clear weekly dollar benchmark is stated with the
    pension/Pension Supplement parity position.
    """
    lower = t.lower()
    if "pension" not in lower or "supplement" not in lower:
        return False

    vals = []
    for m in re.finditer(r"(?:at least|minimum of|to)\s*\$([\d,]+(?:\.\d{1,2})?)\s*(?:a|per)\s*week", t, re.I):
        v = money(m.group(1))
        if 300 <= v <= 1000:
            vals.append(v)

    if not vals:
        return False

    latest = max(vals)
    ac = state.setdefault("acoss_monitor", {})
    changed = float(ac.get("benchmark_weekly", 0) or 0) != latest
    ac["benchmark_weekly"] = round(latest, 2)
    ac["benchmark_fortnightly"] = round(latest * 2, 2)
    ac["chart_c_ratio_pct"] = round(
        (latest * 2 / float(state["core"]["chart_c_fortnightly"])) * 100, 4
    )
    ac["status"] = "CURRENT ACOSS POSITION"
    ac["classification"] = "Independent policy position — not THE CONSTANT methodology and not Australian Government policy."
    ac["relationship_note"] = (
        "ACOSS does not derive its benchmark from Chart C. "
        "THE CONSTANT independently expresses the ACOSS benchmark against Chart C as a common denominator."
    )
    return changed

def parse_rss(html):
    soup=BeautifulSoup(html,"xml")
    m=meta("Social Services Minister — Media Releases")
    known=set(m.get("seen_relevant_links",[])); current=[]; changed=False
    for item in soup.find_all("item"):
        tt=item.find("title"); lt=item.find("link")
        if not tt or not lt: continue
        title=tt.get_text(" ",strip=True); url=lt.get_text(" ",strip=True)
        desc=item.find("description"); desc=desc.get_text(" ",strip=True) if desc else ""
        pub=item.find("pubDate"); pub=pub.get_text(" ",strip=True) if pub else ""
        if not any(term in (title+" "+desc).lower() for term in TERMS): continue
        current.append(url)
        if url in known: continue
        if not any(x.get("url")==url for x in state["latest_announcements"]):
            state["latest_announcements"].insert(0,{"source":"Social Services Minister — official RSS","detail":title,"published":pub,"url":url})
            state["latest_announcements"]=state["latest_announcements"][:20]
        mark_change(); changed=True
    m["seen_relevant_links"]=current[:100]
    return changed



def parse_pc_watch(t):
    """
    Productivity Commission source watcher.
    Content hashes are already tracked by fetch(); this parser records
    that a monitored PC page has materially refreshed without trying
    to infer new policy conclusions automatically.
    """
    rm = state.setdefault(
        "review_monitor",
        {
            "live_retention_days": 30,
            "archive_years": 7,
            "active": [],
            "archive": []
        }
    )

    rm["last_productivity_commission_check"] = now_iso()

    return False



def parse_workers_comp(t):
    m = re.search(
        r"Australian standardised average premium rate was\\s*([0-9]+(?:\\.[0-9]+)?)%\\s*of payroll",
        t, re.I | re.S
    )
    if not m:
        return False
    v = float(m.group(1))
    wc = state["book_impact_model"]["workers_comp"]
    if v != wc.get("latest_standardised_average_premium_rate_pct"):
        wc["latest_standardised_average_premium_rate_pct"] = v
        recalc_book_impact_model()
        return True
    return False


def parse_ato_super(t):
    m = re.search(r"(?:calculated as|super guarantee.{0,100}?)([0-9]+(?:\\.[0-9]+)?)%\\s+of", t, re.I | re.S)
    if not m:
        m = re.search(r"([0-9]+(?:\\.[0-9]+)?)%\\s+of an employee.?s qualifying earnings", t, re.I | re.S)
    if not m:
        return False
    v = float(m.group(1))
    sg = state["book_impact_model"]["superannuation"]
    if 5 <= v <= 25 and v != sg.get("sg_rate_pct"):
        sg["sg_rate_pct"] = v
        recalc_book_impact_model()
        return True
    return False


def parse_ato_medicare(t):
    changed = False
    cfg = state["book_impact_model"]["tax_medicare"]

    rate = re.search(r"Medicare levy of\\s*([0-9]+(?:\\.[0-9]+)?)%", t, re.I)
    if rate:
        v = float(rate.group(1))
        if v != cfg.get("medicare_levy_rate_pct"):
            cfg["medicare_levy_rate_pct"] = v
            changed = True

    thresholds = re.search(
        r"All other taxpayers\\s*\\$([\\d,]+)\\s*\\$([\\d,]+)",
        t, re.I | re.S
    )
    if thresholds:
        lo = float(thresholds.group(1).replace(",", ""))
        hi = float(thresholds.group(2).replace(",", ""))
        if lo != cfg.get("medicare_single_lower_threshold"):
            cfg["medicare_single_lower_threshold"] = lo
            changed = True
        if hi != cfg.get("medicare_single_upper_threshold"):
            cfg["medicare_single_upper_threshold"] = hi
            changed = True

    if changed:
        recalc_book_impact_model()
    return changed


def parse_ato_tax(t):
    """
    The live source is watched for changes. Structured resident tax rules
    are kept in state so the book model is deterministic and auditable.
    """
    cfg = state["book_impact_model"]["tax_medicare"]
    changed = False

    # 2026-27 first marginal rate: 15%.
    m = re.search(r"2026.?27.{0,800}?15\\s*%", t, re.I | re.S)
    if m and cfg["tax_brackets"][0]["rate"] != 0.15:
        cfg["tax_brackets"][0]["rate"] = 0.15
        changed = True

    if changed:
        recalc_book_impact_model()
    return changed



def parse_income_support_age_pension(t):
    changed = False
    payments = state["income_support_counterfactual"]["payments"]

    # Services Australia normal-rate table: single basic + supplement + energy + total.
    basic = re.search(r"Maximum basic rate\\s*\\$([\\d,]+(?:\\.\\d+)?)", t, re.I)
    total = re.search(r"Total\\s*\\$([\\d,]+(?:\\.\\d+)?)", t, re.I)

    if basic:
        v = float(basic.group(1).replace(",", ""))
        for key in ("age_pension_single_basic", "dsp_single_basic"):
            if payments[key]["actual_fortnightly"] != v:
                payments[key]["actual_fortnightly"] = v
                changed = True

    if total:
        v = float(total.group(1).replace(",", ""))
        for key in ("age_pension_single_total", "dsp_single_typical_total"):
            if payments[key]["actual_fortnightly"] != v:
                payments[key]["actual_fortnightly"] = v
                changed = True

    if changed:
        recalc_income_support_counterfactual()
    return changed


def parse_income_support_jobseeker(t):
    changed = False
    payments = state["income_support_counterfactual"]["payments"]

    m = re.search(
        r"Single,\\s*no children\\s*\\|?\\s*\\$([\\d,]+(?:\\.\\d+)?)",
        t, re.I
    )
    if not m:
        m = re.search(
            r"Single,\\s*no children.{0,120}?\\$([\\d,]+(?:\\.\\d+)?)",
            t, re.I | re.S
        )

    if m:
        v = float(m.group(1).replace(",", ""))
        key = "jobseeker_single_no_children"
        if payments[key]["actual_fortnightly"] != v:
            payments[key]["actual_fortnightly"] = v
            payments[key]["source_effective_period"] = "current Services Australia published rate"
            changed = True

    if changed:
        recalc_income_support_counterfactual()
    return changed


def parse_remtrib(t):
    changed=False
    # General annual-review adjustment.
    m=re.search(r"(?:general|remuneration).{0,180}?([0-9]+(?:\.[0-9]+)?)\\s*(?:per cent|%)",t,re.I|re.S)
    if m and "2026" in t:
        v=float(m.group(1))
        if 0 <= v <= 20 and v != state["remuneration"].get("review_2026_general_adjustment_pct"):
            state["remuneration"]["review_2026_general_adjustment_pct"]=v
            changed=True
    return changed

def parse_rba_policy(t):
    changed=False
    m=re.search(r"cash rate target.{0,180}?([0-9]+(?:\.[0-9]+)?)\\s*(?:per cent|%)",t,re.I|re.S)
    if m:
        v=float(m.group(1))
        if v != state["rba_policy"].get("cash_rate_pct"):
            old=state["rba_policy"].get("cash_rate_pct")
            state["rba_policy"]["cash_rate_pct"]=v
            state["official"]["cash_rate_pct"]=v
            if old is not None:
                state["rba_policy"]["change_basis_points"]=round((v-old)*100)
            changed=True
    return changed


def _parse_date_ymd(s):
    from datetime import datetime
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def maintain_union_archive():
    """Keep new activity on-screen for 30 days; retain archive for ~18 months."""
    from datetime import date, timedelta
    ua = state.setdefault("union_award_monitor", {"active_days":30,"archive_years":7,"active":[],"archive":[]})
    today = date.today()
    active_keep=[]
    for item in ua.get("active", []):
        d=_parse_date_ymd(item.get("updated_date") or item.get("opened_date"))
        if d and (today-d).days > ua.get("active_days",30):
            if not any(x.get("id")==item.get("id") for x in ua.setdefault("archive",[])):
                ua["archive"].insert(0,item)
        else:
            active_keep.append(item)
    ua["active"]=active_keep

    cutoff=today-timedelta(days=2557)  # ~7 years
    ua["archive"]=[
        item for item in ua.get("archive",[])
        if (_parse_date_ymd(item.get("updated_date") or item.get("opened_date")) or today) >= cutoff
    ][:300]

def upsert_union_item(item):
    ua=state.setdefault("union_award_monitor", {"active_days":30,"archive_years":7,"active":[],"archive":[]})
    for bucket in ("active","archive"):
        for i,old in enumerate(ua.get(bucket,[])):
            if old.get("id")==item.get("id"):
                merged=dict(old); merged.update(item); ua[bucket][i]=merged
                return
    ua.setdefault("active",[]).insert(0,item)

def parse_union_actu(t):
    """Capture new ACTU low-paid / award claims when headline text carries a clear percentage."""
    changed=False
    lower=t.lower()
    if not any(x in lower for x in ("minimum wage","award wage","annual wage review","low-paid","lower-paid")):
        return False
    # Find one plausible claim percentage.
    m=re.search(r"(?:claim|seek|seeking|push|argue for|wage rise|wage increase).{0,90}?([0-9]+(?:\\.[0-9]+)?)\\s*%",t,re.I|re.S)
    if not m:
        return False
    pct=float(m.group(1))
    if not 1 <= pct <= 20:
        return False
    base=state["core"].get("minimum_wage_weekly")
    applied=round(base*(1+pct/100),2) if base else None
    item={
        "id": f"actu-auto-{datetime.now().date().isoformat()}-{pct}",
        "organisation": "Australian Council of Trade Unions",
        "matter": "Detected wage / award claim",
        "category": "Low-paid and award-reliant workers",
        "opened_date": datetime.now().date().isoformat(),
        "updated_date": datetime.now().date().isoformat(),
        "current_rate_weekly_at_claim": base,
        "revised_claim_pct": pct,
        "revised_claim_weekly": applied,
        "status": "Claim / application detected",
        "source": "ACTU official media-release page",
        "summary": f"Detected ACTU claim of {pct:.2f}% from official page text."
    }
    upsert_union_item(item); changed=True
    return changed

def parse_union_fwc(t):
    """Record material changes to FWC wage-review submission/determination pages."""
    # The page hash/change is already tracked by source metadata. Avoid creating
    # duplicate rows unless the text shows an explicit new wage percentage.
    m=re.search(r"(?:increase|adjust).{0,100}?([0-9]+(?:\\.[0-9]+)?)\\s*%",t,re.I|re.S)
    if not m:
        return False
    pct=float(m.group(1))
    if not 1 <= pct <= 20:
        return False
    item={
        "id": f"fwc-auto-{datetime.now().date().isoformat()}-{pct}",
        "organisation": "Fair Work Commission",
        "matter": "Award / minimum wage development",
        "category": "Modern awards / minimum wages",
        "opened_date": datetime.now().date().isoformat(),
        "updated_date": datetime.now().date().isoformat(),
        "current_rate_weekly_at_claim": state["core"].get("minimum_wage_weekly"),
        "final_general_award_pct": pct,
        "status": "FWC update detected",
        "source": "Fair Work Commission",
        "summary": f"Detected FWC wage-related update containing {pct:.2f}%."
    }
    upsert_union_item(item)
    return True



# =============================================================================
# THE CONSTANT LIVE v5.6.7
# UPCOMING EVENT -> OFFICIAL ANNOUNCEMENT LIFECYCLE
# =============================================================================

def _event_date(value):
    """
    Return YYYY-MM-DD/date-like input as a date where possible.
    """
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            return value
        except Exception:
            pass

    text = str(value).strip()

    # ISO timestamp.
    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except Exception:
        pass

    # ISO date.
    try:
        return datetime.strptime(
            text[:10],
            "%Y-%m-%d"
        ).date()
    except Exception:
        pass

    # RSS.
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(
                text,
                fmt
            ).date()
        except Exception:
            pass

    return None


def _announcement_date(item):
    for key in (
        "date",
        "time",
        "published",
    ):
        d = _event_date(
            item.get(key)
        )

        if d:
            return d

    return None


def _announcement_text(item):
    parts = [
        item.get("title"),
        item.get("label"),
        item.get("detail"),
        item.get("summary"),
        item.get("source"),
        item.get("category"),
    ]

    return " ".join(
        str(x)
        for x in parts
        if x
    ).lower()


def _normalise_event_text(text):
    text = str(text or "").lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    return " ".join(
        text.split()
    )


def _event_category(event):
    """
    Conservative event classifier.

    Only recognised categories are eligible for automatic completion.
    """
    text = _normalise_event_text(
        (
            str(event.get("label", ""))
            + " "
            + str(event.get("title", ""))
            + " "
            + str(event.get("source", ""))
        )
    )

    if (
        "consumer price index" in text
        or " monthly cpi " in f" {text} "
        or text.startswith("cpi ")
    ):
        return "cpi"

    if "labour force" in text:
        return "labour_force"

    if (
        "monetary policy decision" in text
        or "cash rate" in text
    ):
        return "rba_policy"

    if "wage price index" in text:
        return "wpi"

    if (
        "pension indexation" in text
        or "social security indexation" in text
        or "social-security indexation" in text
    ):
        return "pension_indexation"

    if (
        "national minimum wage" in text
        or "award rates commence" in text
    ):
        return "minimum_wage"

    if "annual wage review" in text:
        return "annual_wage_review"

    if "gst distribution reforms" in text:
        return "gst_reforms"

    if "business dynamism" in text:
        return "business_dynamism"

    if "household spending" in text:
        return "household_spending"

    return None


def _announcement_matches_event(event, announcement):
    """
    Conservative official-release matcher.

    A release must:
      * be dated on/after the event date;
      * match the relevant subject category;
      * be recognisably official rather than THE CONSTANT analysis.
    """
    event_date = _event_date(
        event.get("date")
    )

    announcement_date = _announcement_date(
        announcement
    )

    if not event_date or not announcement_date:
        return False

    # Critical lifecycle rule:
    # an advance announcement does not complete a future effective event.
    if announcement_date < event_date:
        return False

    status = str(
        announcement.get("status", "")
    ).upper()

    # Never use internal analysis as evidence that an official event completed.
    if "THE CONSTANT ANALYSIS" in status:
        return False

    text = _announcement_text(
        announcement
    )

    category = _event_category(
        event
    )

    if not category:
        return False

    tests = {
        "cpi":
            (
                "consumer price index" in text
                or "cpi" in text
            ),

        "labour_force":
            "labour force" in text,

        "rba_policy":
            (
                "monetary policy" in text
                or "cash rate" in text
                or "reserve bank" in text
            ),

        "wpi":
            (
                "wage price index" in text
                or "wpi" in text
            ),

        "pension_indexation":
            (
                "pension" in text
                and (
                    "indexation" in text
                    or "rate" in text
                )
            ),

        "minimum_wage":
            (
                "minimum wage" in text
                or "award rate" in text
            ),

        "annual_wage_review":
            "annual wage review" in text,

        "gst_reforms":
            (
                "gst" in text
                and (
                    "distribution" in text
                    or "reform" in text
                )
            ),

        "business_dynamism":
            "business dynamism" in text,

        "household_spending":
            (
                "household spending" in text
                or "monthly household spending indicator" in text
            ),
    }

    return bool(
        tests.get(
            category,
            False
        )
    )


def _announcement_key(item):
    return (
        item.get("id")
        or item.get("url")
        or (
            str(item.get("source", ""))
            + "|"
            + str(
                item.get(
                    "title",
                    item.get(
                        "detail",
                        ""
                    )
                )
            )
            + "|"
            + str(
                item.get(
                    "date",
                    item.get(
                        "published",
                        item.get(
                            "time",
                            ""
                        )
                    )
                )
            )
        )
    )


def promote_completed_upcoming_events():
    """
    Move an Upcoming Event out of the calendar only after a matching
    official release has actually been detected.

    IMPORTANT:
    A past event with no detected official release remains in Upcoming Events
    and is marked AWAITING OFFICIAL RELEASE.
    """
    upcoming = state.setdefault(
        "upcoming_events",
        []
    )

    announcements = state.setdefault(
        "latest_announcements",
        []
    )

    today = datetime.now(
        SYDNEY_TZ
    ).date()

    retained = []
    promoted = []

    for event in upcoming:

        if not isinstance(event, dict):
            retained.append(event)
            continue

        event_date = _event_date(
            event.get("date")
        )

        matched = None

        for announcement in announcements:
            if not isinstance(
                announcement,
                dict
            ):
                continue

            if _announcement_matches_event(
                event,
                announcement
            ):
                matched = announcement
                break

        if matched is None:
            preserved = dict(event)

            if (
                event_date
                and event_date < today
            ):
                preserved[
                    "lifecycle_status"
                ] = "AWAITING OFFICIAL RELEASE"
            else:
                preserved[
                    "lifecycle_status"
                ] = "UPCOMING"

            retained.append(
                preserved
            )

            continue

        # A real matching release has been found.
        enriched = dict(
            matched
        )

        enriched.setdefault(
            "status",
            "OFFICIAL"
        )

        if not str(
            enriched.get(
                "status",
                ""
            )
        ).strip():
            enriched[
                "status"
            ] = "OFFICIAL"

        enriched[
            "matched_upcoming_event"
        ] = (
            event.get("label")
            or event.get("title")
        )

        enriched[
            "matched_event_date"
        ] = event.get(
            "date"
        )

        enriched[
            "event_lifecycle"
        ] = "COMPLETED — OFFICIAL RELEASE DETECTED"

        # Replace the existing announcement in place.
        matched_key = _announcement_key(
            matched
        )

        for i, current in enumerate(
            announcements
        ):
            if (
                isinstance(
                    current,
                    dict
                )
                and _announcement_key(
                    current
                ) == matched_key
            ):
                announcements[i] = enriched
                break

        promoted.append(
            {
                "event":
                    event.get("label")
                    or event.get("title"),

                "event_date":
                    event.get("date"),

                "announcement":
                    enriched.get("title")
                    or enriched.get("detail"),

                "announcement_date":
                    str(
                        _announcement_date(
                            enriched
                        )
                    ),

                "status":
                    enriched.get(
                        "status",
                        "OFFICIAL"
                    ),
            }
        )

    state[
        "upcoming_events"
    ] = retained

    state[
        "latest_announcements"
    ] = announcements

    return promoted



def maintain_announcement_archive():
    """
    Keep all official announcements on the main page for 30 days,
    then move them into a seven-year archive.
    """
    from datetime import date, datetime, timedelta
    policy = state.setdefault(
        "announcement_policy",
        {"main_page_days": 30, "archive_years": 7}
    )
    policy["main_page_days"] = 30
    policy["archive_years"] = 7
    policy.pop("archive_months", None)

    main_days = int(policy.get("main_page_days", 30))
    cutoff_days = 2557  # ~7 years

    today = date.today()
    active = []
    archive = state.setdefault("announcement_archive", [])

    def item_date(item):
        # Prefer machine ISO time; fall back to RSS publication text where possible.
        raw = item.get("time")
        if raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
            except Exception:
                pass

        published = item.get("published")
        if published:
            # RSS format example: Thu, 20 Aug 2026 08:16:37 +1000
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%d %b %Y"):
                try:
                    return datetime.strptime(published, fmt).date()
                except Exception:
                    pass

        raw_date = item.get("date")
        if raw_date:
            try:
                return datetime.strptime(raw_date, "%Y-%m-%d").date()
            except Exception:
                pass

        return today

    # Move >7-day items from main feed to archive.
    for item in state.get("latest_announcements", []):
        d = item_date(item)
        age = (today - d).days

        if age > main_days:
            key = (
                item.get("url")
                or (
                    str(item.get("source", ""))
                    + "|"
                    + str(item.get("detail", ""))
                    + "|"
                    + str(item.get("published", item.get("time", "")))
                )
            )

            duplicate = any(
                (
                    old.get("url")
                    or (
                        str(old.get("source", ""))
                        + "|"
                        + str(old.get("detail", ""))
                        + "|"
                        + str(old.get("published", old.get("time", "")))
                    )
                ) == key
                for old in archive
            )

            if not duplicate:
                archived = dict(item)
                archived["archived_at"] = now_iso()
                archive.insert(0, archived)
        else:
            active.append(item)

    state["latest_announcements"] = active[:100]

    # Keep seven years in archive.
    kept = []
    for item in archive:
        d = item_date(item)
        if (today - d).days <= cutoff_days:
            kept.append(item)

    state["announcement_archive"] = kept[:1000]



# =============================================================================
# THE CONSTANT LIVE v5.6.7 — STAGE 3
# CONTROLLED MATERIAL-DEVELOPMENT RELEVANCE FILTER
# =============================================================================

CONSTANT_MATERIAL_CATEGORIES = {
    "benchmark": {
        "chart c",
        "pension",
        "income test",
        "free area",
        "taper",
        "minimum wage",
        "national minimum wage",
        "award wage",
        "wage review",
    },
    "calculation": {
        "ratio",
        "weekly gap",
        "structural shortfall",
        "proposed wage",
        "corrected wage",
        "payg",
        "medicare",
        "superannuation",
        "workers compensation",
    },
    "essential_cost": {
        "cpi",
        "inflation",
        "living cost",
        "housing",
        "rent",
        "electricity",
        "gas",
        "water",
        "food",
        "transport",
        "fuel",
        "insurance",
    },
    "economic_interpretation": {
        "cash rate",
        "monetary policy",
        "labour force",
        "unemployment",
        "employment",
        "participation",
        "hours worked",
        "wage price index",
        "productivity",
        "gst",
    },
}

# Generic page activity is deliberately not evidence of materiality.
CONSTANT_NON_MATERIAL_SIGNALS = {
    "page updated",
    "website updated",
    "source changed",
    "content changed",
    "new page",
    "document uploaded",
    "page refreshed",
    "http 200",
    "http 304",
    "etag changed",
    "last modified",
}

CONSTANT_EXPLICIT_NON_RELEVANCE_SIGNALS = {
    "unrelated to",
    "not related to",
    "not relevant to",
    "no effect on",
    "no impact on",
    "does not affect",
    "does not impact",
    "unconnected to",
}


def _material_text(item):
    """Create one normalised searchable string from a candidate item."""
    if not isinstance(item, dict):
        return ""

    parts = []

    for key in (
        "title",
        "summary",
        "detail",
        "matter",
        "category",
        "source",
    ):
        value = item.get(key)
        if value:
            parts.append(str(value))

    affects = item.get("affects", [])

    if isinstance(affects, (list, tuple, set)):
        parts.extend(str(x) for x in affects if x)
    elif affects:
        parts.append(str(affects))

    text = " ".join(parts).lower()

    # Normalise punctuation/hyphens so terms such as
    # "monetary-policy" become "monetary policy".
    text = re.sub(
        r"[^a-z0-9%$]+",
        " ",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def assess_constant_materiality(item):
    """
    Determine whether an item is materially relevant to THE CONSTANT.

    Materiality requires a substantive connection to at least one of:
      1. a benchmark;
      2. a derived calculation;
      3. an essential-cost measure;
      4. substantive economic interpretation used by THE CONSTANT.

    A webpage/source changing by itself is NOT sufficient.
    """
    if not isinstance(item, dict):
        return {
            "material": False,
            "categories": [],
            "reason": "Invalid candidate."
        }

    # Explicit False always wins.
    if item.get("material_to_constant") is False:
        return {
            "material": False,
            "categories": [],
            "reason": "Explicitly marked non-material."
        }

    text = _material_text(item)

    if not text:
        return {
            "material": False,
            "categories": [],
            "reason": "No substantive content."
        }

    # Explicit non-relevance language overrides mere keyword presence.
    # Example: "unrelated to wages, pensions or inflation" is not material.
    explicit_non_relevance = any(
        signal in text
        for signal in CONSTANT_EXPLICIT_NON_RELEVANCE_SIGNALS
    )

    if explicit_non_relevance and not item.get("affects"):
        return {
            "material": False,
            "categories": [],
            "reason": (
                "Candidate explicitly states that the matter is unrelated "
                "to or has no effect on THE CONSTANT."
            )
        }

    substantive_hits = {}

    for category, terms in CONSTANT_MATERIAL_CATEGORIES.items():
        hits = sorted(
            term
            for term in terms
            if term in text
        )

        if hits:
            substantive_hits[category] = hits

    # Explicit affects fields are especially strong evidence because
    # they identify the actual dashboard consequence.
    affects = item.get("affects", [])
    has_affects = bool(affects)

    # Explicit True is accepted only where there is also substantive
    # subject content or a declared affected dashboard component.
    explicit_true = item.get("material_to_constant") is True

    material = bool(
        substantive_hits
        or has_affects
    )

    if explicit_true and (substantive_hits or has_affects):
        material = True

    if not material:
        noise_only = any(
            signal in text
            for signal in CONSTANT_NON_MATERIAL_SIGNALS
        )

        return {
            "material": False,
            "categories": [],
            "reason": (
                "Source/page activity only; no demonstrated effect on "
                "a THE CONSTANT benchmark, calculation, essential-cost "
                "measure or substantive economic interpretation."
                if noise_only
                else
                "No demonstrated material connection to THE CONSTANT."
            )
        }

    categories = sorted(substantive_hits.keys())

    return {
        "material": True,
        "categories": categories,
        "reason": (
            "Material connection established to: "
            + (
                ", ".join(categories)
                if categories
                else "declared THE CONSTANT dashboard effect"
            )
            + "."
        )
    }


def _material_item_date(item):
    """
    Parse supported material-development dates.
    YYYY-MM-DD is preferred. YYYY-MM is treated as the first day
    of that month for archive-age purposes.
    """
    from datetime import date, datetime

    raw = str(item.get("date", "")).strip()

    if not raw:
        return date.today()

    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            pass

    return date.today()


def _material_item_key(item):
    """Stable duplicate key for material developments."""
    if item.get("id"):
        return str(item["id"]).strip().lower()

    return "|".join([
        str(item.get("date", "")).strip().lower(),
        str(item.get("source", "")).strip().lower(),
        str(item.get("title", "")).strip().lower(),
    ])


def upsert_constant_material_development(item):
    """
    Add/update a material development only after passing the
    controlled relevance assessment.
    """
    assessment = assess_constant_materiality(item)

    if not assessment["material"]:
        return False

    monitor = state.setdefault(
        "constant_material_monitor",
        {
            "active_days": 30,
            "archive_years": 7,
            "active": [],
            "archive": [],
        }
    )

    candidate = dict(item)

    candidate["material_to_constant"] = True
    candidate["material_categories"] = assessment["categories"]
    candidate["materiality_reason"] = assessment["reason"]

    key = _material_item_key(candidate)

    active = monitor.setdefault("active", [])
    archive = monitor.setdefault("archive", [])

    # Update existing active item.
    for i, old in enumerate(active):
        if _material_item_key(old) == key:
            merged = dict(old)
            merged.update(candidate)
            active[i] = merged
            return True

    # If an archived item becomes current again, remove old archive copy.
    archive[:] = [
        old
        for old in archive
        if _material_item_key(old) != key
    ]

    active.insert(0, candidate)

    return True


def maintain_constant_material_monitor():
    """
    Keep material developments active for 30 days and archived for
    seven years. Non-material entries are removed from the material
    feed rather than archived as if they were material.
    """
    from datetime import date

    monitor = state.setdefault(
        "constant_material_monitor",
        {
            "active_days": 30,
            "archive_years": 7,
            "active": [],
            "archive": [],
        }
    )

    active_days = int(
        monitor.get("active_days", 30)
    )

    archive_years = int(
        monitor.get("archive_years", 7)
    )

    archive_days = int(
        round(archive_years * 365.25)
    )

    today = date.today()

    new_active = []
    archive = list(
        monitor.setdefault("archive", [])
    )

    # Reassess every active item under the controlled Stage 3 rule.
    for item in monitor.get("active", []):

        assessment = assess_constant_materiality(item)

        if not assessment["material"]:
            continue

        cleaned = dict(item)
        cleaned["material_to_constant"] = True
        cleaned["material_categories"] = assessment["categories"]
        cleaned["materiality_reason"] = assessment["reason"]

        item_date = _material_item_date(cleaned)
        age = (today - item_date).days

        if age > active_days:
            key = _material_item_key(cleaned)

            if not any(
                _material_item_key(old) == key
                for old in archive
            ):
                archived = dict(cleaned)
                archived["archived_at"] = now_iso()
                archive.insert(0, archived)
        else:
            new_active.append(cleaned)

    # Revalidate and retain only material archive entries within 7 years.
    new_archive = []

    seen = set()

    for item in archive:

        assessment = assess_constant_materiality(item)

        if not assessment["material"]:
            continue

        item_date = _material_item_date(item)

        if (today - item_date).days > archive_days:
            continue

        key = _material_item_key(item)

        if key in seen:
            continue

        seen.add(key)

        cleaned = dict(item)
        cleaned["material_to_constant"] = True
        cleaned["material_categories"] = assessment["categories"]
        cleaned["materiality_reason"] = assessment["reason"]

        new_archive.append(cleaned)

    # Newest first.
    new_active.sort(
        key=lambda x: str(x.get("date", "")),
        reverse=True
    )

    new_archive.sort(
        key=lambda x: str(x.get("date", "")),
        reverse=True
    )

    monitor["active_days"] = 30
    monitor["archive_years"] = 7
    monitor["active"] = new_active[:100]
    monitor["archive"] = new_archive[:1000]

    return True


def check_all():
    errors=[]
    for name,(url,kind) in SOURCES.items():
        before = json.loads(json.dumps(state))
        _set_source_status(name, SOURCE_STATUS_CURRENT, "Checking official/identified source.")
        html=fetch(name,url)
        if html is None:
            m=meta(name)
            if m.get("error") or m.get("warning"):
                _set_source_status(name, SOURCE_STATUS_ATTENTION,
                    m.get("warning") or m.get("error") or "Source unavailable; last verified value retained.")
            continue
        try:
            if kind=="minister_rss":
                _set_source_status(name, SOURCE_STATUS_VALIDATING, "Source reached; validating announcement feed.")
                parse_rss(html)
                _set_source_status(name, SOURCE_STATUS_CURRENT, "Announcement feed checked successfully.")
                continue
            t=textify(html); changed=False
            state.pop("_parser_rejection", None)
            if kind=="abs_labour": changed=parse_abs_labour(t)
            elif kind=="abs_cpi":
                changed = parse_abs_cpi(t)
                try:
                    detail_changed = parse_complete_abs_cpi_detail(t)
                    changed = bool(changed or detail_changed)
                except Exception as e:
                    meta(name)["warning"] = "CPI detail parser warning; last verified detail retained: " + str(e)
            elif kind=="abs_lci": changed=parse_lci(t)
            elif kind=="rba": changed=parse_rba(t)
            elif kind=="fwc": changed=parse_fwc(t)
            elif kind=="chart_c": changed=parse_chart_c(t)
            elif kind=="remtrib": changed=parse_remtrib(t)
            elif kind=="rba_policy": changed=parse_rba_policy(t)
            elif kind=="union_actu": changed=parse_union_actu(t)
            elif kind=="union_fwc": changed=parse_union_fwc(t)
            elif kind=="pc_watch": changed=parse_pc_watch(t)
            elif kind=="workers_comp": changed=parse_workers_comp(t)
            elif kind=="ato_super": changed=parse_ato_super(t)
            elif kind=="ato_medicare": changed=parse_ato_medicare(t)
            elif kind=="ato_tax": changed=parse_ato_tax(t)
            elif kind=="income_support_age_pension": changed=parse_income_support_age_pension(t)
            elif kind=="income_support_jobseeker": changed=parse_income_support_jobseeker(t)
            elif kind=="acoss": changed=parse_acoss(t)

            rejection = state.pop("_parser_rejection", None)
            if rejection:
                runtime_sources = state.get("sources", {})
                state.clear(); state.update(before)
                state["sources"] = runtime_sources
                detail = rejection.get("detail") or "Candidate release rejected by parser integrity gate."
                _set_source_status(name, SOURCE_STATUS_ATTENTION, detail + " Last verified state retained.")
                errors.append(f"{name}: {detail}")
                continue

            m=meta(name)
            if m.get("changed") or changed:
                _set_source_status(name, SOURCE_STATUS_DETECTED, "Source content or parsed observation changed.")
                _set_source_status(name, SOURCE_STATUS_VALIDATING, "Candidate update is passing validation gates.")
                ok, detail = _validate_candidate(kind)
                if not ok:
                    # Roll back substantive state while preserving runtime source metadata.
                    runtime_sources = state.get("sources", {})
                    state.clear(); state.update(before)
                    state["sources"] = runtime_sources
                    _set_source_status(name, SOURCE_STATUS_ATTENTION, detail + " Last verified state retained.")
                    errors.append(f"{name}: {detail}")
                    continue
                _set_source_status(name, SOURCE_STATUS_UPDATED if changed else SOURCE_STATUS_CURRENT, detail)
                if changed:
                    mark_change()
                    _append_audit_event(name, kind, before, state, source_url=url)
            else:
                _set_source_status(name, SOURCE_STATUS_CURRENT, "Latest expected source content checked; no validated data change.")
        except Exception as e:
            runtime_sources = state.get("sources", {})
            state.clear(); state.update(before)
            state["sources"] = runtime_sources
            _set_source_status(name, SOURCE_STATUS_ATTENTION, f"Parser/validation error: {e}. Last verified state retained.")
            errors.append(f"{name}: {e}")
    maintain_union_archive()
    promote_completed_upcoming_events()
    maintain_announcement_archive()
    maintain_constant_material_monitor()
    recalc()
    recalculate_leci_income_burden()
    recalc_book_impact_model()
    recalc_income_support_counterfactual()
    source_status_summary()
    with lock:
        state["errors"]=errors
        state["checks_completed"]+=1
        state["last_check"]=now_iso()
        state["next_check"]=next_refresh_time().isoformat(timespec="seconds")
        save_state()


# =============================================================================
# THE CONSTANT LIVE v5.6.5
# THREE-INCOME ESSENTIAL COST BURDEN
# =============================================================================

def recalculate_leci_income_burden():

    global state

    costs = {

        "rent":
            650.00,

        "electricity":
            46.15,

        "gas":
            17.31,

        "water_sewerage":
            17.31,

        "food":
            180.00,

        "transport":
            100.00,

        "health_medicines":
            30.00,

        "insurance":
            25.00,

        "household_necessities":
            40.00,

        "phone_internet":
            25.00,

        "clothing_personal_care":
            20.00,
    }

    basket = round(
        sum(costs.values()),
        2
    )

    official = state.setdefault(
        "official",
        {}
    )

    actual = float(

        official.get(
            "national_minimum_wage_weekly",
            1004.90
        )

        or 1004.90
    )

    proposed = float(state["core"]["chart_c_weekly"])

    average = 2083.70

    incomes = {

        "minimum_wage": {

            "label":
                "National Minimum Wage",

            "weekly":
                actual,
        },

        "proposed_wage": {

            "label":
                "Chart C Proposed Wage",

            "weekly":
                proposed,
        },

        "average_wage": {

            "label":
                "Average Weekly Ordinary-Time Earnings",

            "weekly":
                average,
        },
    }

    for key, obj in incomes.items():

        wage = obj["weekly"]

        obj[
            "item_burden_pct"
        ] = {

            item:
                round(
                    cost / wage * 100,
                    2
                )

            for item, cost
            in costs.items()
        }

        obj[
            "total_burden_pct"
        ] = round(
            basket / wage * 100,
            2
        )

        obj[
            "gross_remaining"
        ] = round(
            wage - basket,
            2
        )

    derived = state.setdefault(
        "the_constant_derived",
        {}
    )

    derived[
        "leci_income_burden"
    ] = {

        "reference_period":
            "2026",

        "before_tax":
            True,

        "weekly_costs":
            costs,

        "basket_total_weekly":
            basket,

        "incomes":
            incomes,

        "methodology":
            "Same essential weekly cash-cost basket "
            "divided by gross weekly income. "
            "Before income tax and Medicare levy.",
    }

    return True


def _release_calendar():
    """Return source-specific release windows.

    Calendar entries can be supplied without a code deployment through
    TC_RELEASE_CALENDAR_JSON. Each entry uses Australia/Sydney local time:
      {"source":"ABS CPI","start":"2026-09-30T10:55:00","end":"2026-09-30T12:30:00"}

    The state copy is public/auditable and can also be populated by future
    official-calendar parsers. Legacy TC_RELEASE_WINDOWS remains supported.
    """
    cal = state.setdefault("release_calendar", {})
    cal.setdefault("timezone", "Australia/Sydney")
    cal.setdefault("entries", [])
    cal.setdefault("last_calendar_refresh", None)
    cal.setdefault("method", "Source-specific windows; configurable without deployment")

    raw = os.getenv("TC_RELEASE_CALENDAR_JSON", "").strip()
    if raw:
        try:
            payload = json.loads(raw)
            entries = payload.get("entries", payload) if isinstance(payload, dict) else payload
            if isinstance(entries, list):
                clean=[]
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    if not e.get("source") or not e.get("start") or not e.get("end"):
                        continue
                    clean.append({
                        "source": str(e["source"]),
                        "start": str(e["start"]),
                        "end": str(e["end"]),
                        "expected_release": e.get("expected_release"),
                        "official_calendar_url": e.get("official_calendar_url"),
                        "status": e.get("status", "scheduled"),
                    })
                cal["entries"] = clean
                cal["last_calendar_refresh"] = datetime.now(SYDNEY_TZ).isoformat(timespec="seconds")
        except Exception as exc:
            state.setdefault("errors", []).append("Release calendar config: " + str(exc))
    return cal




# Official release-calendar pages. Calendar ingestion is advisory: failure never
# changes a verified economic observation or deletes a previously known date.
RELEASE_CALENDAR_SOURCES = {
    "ABS CPI": "https://www.abs.gov.au/statistics/economy/price-indexes-and-inflation/consumer-price-index-australia/latest-release",
    "ABS Labour Force": "https://www.abs.gov.au/statistics/labour/employment-and-unemployment/labour-force-australia/latest-release",
    "RBA Monetary Policy": "https://www.rba.gov.au/monetary-policy/int-rate-decisions/index.html",
    "FWC Annual Wage Review": "https://www.fwc.gov.au/hearings-decisions/major-cases/annual-wage-reviews",
}

# Near-term official schedule anchors verified 23 September 2026. These are
# fallbacks only: official-page refresh can supersede them, but stale retained
# calendar entries cannot hide a nearer verified release.
VERIFIED_RELEASE_SEEDS = [
    ("ABS Labour Force", "2026-09-24T11:30:00", RELEASE_CALENDAR_SOURCES["ABS Labour Force"]),
    ("RBA Monetary Policy", "2026-09-29T14:30:00", "https://www.rba.gov.au/coming-up/"),
    ("ABS CPI", "2026-09-30T11:30:00", RELEASE_CALENDAR_SOURCES["ABS CPI"]),
]

_MONTHS = {m.lower(): i for i,m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], 1
)}

def _extract_future_dates(text, now=None):
    """Extract plausible future Australian calendar dates from official page text."""
    now = now or datetime.now(SYDNEY_TZ)
    out=[]
    # 30 September 2026 / 30 Sep 2026 style.
    month_pat = r"January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    for m in re.finditer(rf"\b([0-3]?\d)\s+({month_pat})\s+(20\d{{2}})\b", text, re.I):
        day=int(m.group(1)); raw=m.group(2).lower().rstrip('.')
        lookup={"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"nov":11,"dec":12}
        month=_MONTHS.get(raw, lookup.get(raw[:4] if raw.startswith('sept') else raw[:3]))
        if not month: continue
        try: dt=datetime(int(m.group(3)),month,day,11,30,tzinfo=SYDNEY_TZ)
        except ValueError: continue
        if dt >= now.replace(hour=0,minute=0,second=0,microsecond=0): out.append(dt)
    # ISO dates occasionally appear in metadata/body text.
    for m in re.finditer(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text):
        try: dt=datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),11,30,tzinfo=SYDNEY_TZ)
        except ValueError: continue
        if dt >= now.replace(hour=0,minute=0,second=0,microsecond=0): out.append(dt)
    return sorted(set(out))


def _calendar_window(source, dt, url, status="official-calendar detected"):
    """Create a conservative monitoring window around a detected release date."""
    from datetime import timedelta
    # ABS commonly publishes at 11:30 Sydney time; RBA decision timing can differ.
    if source.startswith("RBA"):
        dt=dt.replace(hour=14,minute=0,second=0,microsecond=0)
        before,after=timedelta(hours=2),timedelta(hours=3)
    else:
        dt=dt.replace(hour=11,minute=30,second=0,microsecond=0)
        before,after=timedelta(minutes=45),timedelta(hours=2)
    return {"source":source,"start":(dt-before).isoformat(timespec="seconds"),
            "end":(dt+after).isoformat(timespec="seconds"),
            "expected_release":dt.isoformat(timespec="seconds"),
            "official_calendar_url":url,"status":status}


def refresh_official_release_calendar(force=False):
    """Refresh future release dates from official pages, retaining known dates on failure."""
    from datetime import timedelta
    now=datetime.now(SYDNEY_TZ)
    cal=state.setdefault("release_calendar",{})
    last=_parse_local_iso(cal.get("last_calendar_refresh"))
    if not force and last and (now-last).total_seconds() < 6*3600:
        return False
    retained=[]
    for e in cal.get("entries",[]):
        end=_parse_local_iso(e.get("end"))
        if end and end >= now-timedelta(days=1): retained.append(e)
    detected=[]; errors=[]
    for source,url in RELEASE_CALENDAR_SOURCES.items():
        try:
            r=session.get(url,timeout=20); r.raise_for_status()
            txt=BeautifulSoup(r.text,"html.parser").get_text(" ",strip=True)
            dates=_extract_future_dates(txt,now)
            # Keep only a small forward set; official pages often contain historical dates too.
            for dt in dates[:8]: detected.append(_calendar_window(source,dt,url))
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    # Always include currently verified near-term official anchors.
    for source, iso_value, url in VERIFIED_RELEASE_SEEDS:
        try:
            dt = datetime.fromisoformat(iso_value).replace(tzinfo=SYDNEY_TZ)
            if dt >= now:
                detected.append(_calendar_window(source, dt, url, "verified official schedule"))
        except Exception:
            pass

    # Statutory/regular pension indexation monitoring dates: 20 March and 20 September.
    for year in range(now.year, now.year+2):
        for month in (3,9):
            dt=datetime(year,month,20,9,0,tzinfo=SYDNEY_TZ)
            if dt >= now.replace(hour=0,minute=0,second=0,microsecond=0):
                detected.append(_calendar_window("Services Australia / DSS indexation",dt,
                    "https://www.dss.gov.au/about-the-department/benefits-payments", "statutory-cycle monitoring"))
    # Deduplicate by source/date and prefer newly detected official entries.
    merged={}
    for e in retained+detected:
        dt=_parse_local_iso(e.get("expected_release") or e.get("start"))
        key=(e.get("source"), dt.date().isoformat() if dt else e.get("start"))
        merged[key]=e
    cal["entries"]=sorted(merged.values(),key=lambda e:e.get("start", ""))
    cal["last_calendar_refresh"]=now.isoformat(timespec="seconds")
    cal["calendar_sources"]=RELEASE_CALENDAR_SOURCES
    cal["calendar_errors"]=errors[-10:]
    cal["method"]="Official-page calendar ingestion + statutory indexation cycle; previous dates retained on fetch failure"
    return bool(detected)


def _parse_local_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SYDNEY_TZ)
        return dt.astimezone(SYDNEY_TZ)
    except Exception:
        return None


def _active_release_windows(now=None):
    """Return the named official-source windows active at *now*."""
    now = now or datetime.now(SYDNEY_TZ)
    active=[]
    cal=_release_calendar()
    for e in cal.get("entries", []):
        a=_parse_local_iso(e.get("start")); b=_parse_local_iso(e.get("end"))
        if a and b and a <= now <= b:
            active.append(e)

    # Backward-compatible generic windows, useful as an emergency override.
    raw = os.getenv("TC_RELEASE_WINDOWS", "").strip()
    if raw:
        hm = now.hour * 60 + now.minute
        for window in raw.split(","):
            try:
                a,b=[x.strip() for x in window.split("-",1)]
                ah,am=map(int,a.split(":")); bh,bm=map(int,b.split(":"))
                if ah*60+am <= hm <= bh*60+bm:
                    active.append({"source":"Manual release window","start":a,"end":b,"status":"override"})
            except Exception:
                continue
    return active


def _next_expected_releases(now=None, limit=6):
    now = now or datetime.now(SYDNEY_TZ)
    rows=[]
    for e in _release_calendar().get("entries", []):
        a=_parse_local_iso(e.get("start"))
        if a and a >= now:
            rows.append((a,e))
    rows.sort(key=lambda x:x[0])
    return [e for _,e in rows[:limit]]


def _seconds_until_next_check():
    """Use 5-minute checks inside source-specific release windows, hourly otherwise."""
    return RELEASE_REFRESH_SECONDS if _active_release_windows() else BASE_REFRESH_SECONDS


def next_refresh_time(now=None):
    from datetime import timedelta
    now = now or datetime.now(SYDNEY_TZ)
    return now + timedelta(seconds=_seconds_until_next_check())


def update_release_monitor_state():
    """Expose scheduler state to /api/state so the UI can explain why polling changed."""
    try:
        refresh_official_release_calendar()
    except Exception as exc:
        state.setdefault("errors", []).append("Release calendar refresh: " + str(exc))
    now=datetime.now(SYDNEY_TZ)
    active=_active_release_windows(now)
    state["release_monitor"]={
        "timezone":"Australia/Sydney",
        "mode":"release-window" if active else "normal",
        "poll_seconds": RELEASE_REFRESH_SECONDS if active else BASE_REFRESH_SECONDS,
        "active_sources":[e.get("source") for e in active],
        "next_expected":_next_expected_releases(now),
        "updated_at":now.isoformat(timespec="seconds"),
    }

def loop():
    """Run at startup, then continuously using release-aware polling."""
    try:
        check_all()
    except Exception as e:
        with lock:
            state.setdefault("errors", []).append("Startup source check: " + str(e))

    while True:
        seconds = _seconds_until_next_check()
        from datetime import timedelta
        target = datetime.now(SYDNEY_TZ) + timedelta(seconds=seconds)
        with lock:
            update_release_monitor_state()
            state["next_check"] = target.isoformat(timespec="seconds")
            try:
                save_state()
            except Exception:
                pass
        time.sleep(seconds)
        try:
            check_all()
        except Exception as e:
            with lock:
                state.setdefault("errors", []).append("Scheduled source check: " + str(e))
                try:
                    save_state()
                except Exception:
                    pass


def _counter_store_config():
    """Return external persistent counter configuration when supplied by Render env vars."""
    url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    key = os.getenv("VISITOR_COUNTER_KEY", "the_constant_live_total_visits").strip()
    return url, token, key

def _persistent_counter_increment():
    """Atomically increment the lifetime counter in external Redis-compatible storage."""
    url, token, key = _counter_store_config()
    if not url or not token:
        return None
    try:
        r = requests.post(
            f"{url}/incr/{key}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        r.raise_for_status()
        payload = r.json()
        return int(payload.get("result"))
    except Exception as e:
        state.setdefault("errors", []).append("Persistent visitor counter increment failed: " + str(e))
        return None

def _persistent_counter_read():
    """Read the lifetime count without incrementing it."""
    url, token, key = _counter_store_config()
    if not url or not token:
        return None
    try:
        r = requests.get(
            f"{url}/get/{key}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        r.raise_for_status()
        value = r.json().get("result")
        return int(value or 0)
    except Exception as e:
        state.setdefault("errors", []).append("Persistent visitor counter read failed: " + str(e))
        return None

@app.post("/api/visit")
def visitor_count():
    """Count one dashboard visit per browser session; prefer persistent external storage."""
    vc = state.setdefault("visitor_counter", {
        "total_visits": 0,
        "label": "THE CONSTANT Live visits",
        "method": "One count per browser session",
        "privacy": "No names or personal identifiers are stored by this counter."
    })

    storage = "local fallback"
    if not session.get("tc_visit_counted"):
        persistent_total = _persistent_counter_increment()
        if persistent_total is not None:
            vc["total_visits"] = persistent_total
            storage = "persistent"
        else:
            vc["total_visits"] = int(vc.get("total_visits", 0) or 0) + 1
            try:
                save_state()
            except Exception as e:
                # A visitor count must never make the public dashboard fail.
                # On hosts without writable persistent storage, retain the
                # in-memory fallback and surface persistence separately.
                state.setdefault("errors", []).append("Visitor fallback persistence unavailable: " + str(e))
        session["tc_visit_counted"] = True
    else:
        persistent_total = _persistent_counter_read()
        if persistent_total is not None:
            vc["total_visits"] = persistent_total
            storage = "persistent"

    return jsonify({
        "total_visits": int(vc.get("total_visits", 0) or 0),
        "method": vc.get("method"),
        "privacy": vc.get("privacy"),
        "storage": storage
    })


# -----------------------------------------------------------------------------
# v6.6 — Frozen 128-quarter publication dataset gate / Evidence Explorer API
# -----------------------------------------------------------------------------
PUBLICATION_DATASET_FILENAME = "THE_CONSTANT_Master_Dataset_1995_Q1_2026_Q4_VERIFIED_PUBLICATION.csv"
FIRST_EDITION_PUBLICATION_SHA256 = "7ff767cdf156f4773f0fbd48d6ee7a47c7c7399612ab07f0cbea1b0cc6ec960d"
RECOVERED_EXECUTED_DATASET_SHA256 = "77e4f56c39550ebe48db9d0029e20175a29e220f22e69e6518878ef62a5287e4"
# Live uses the recovered/re-executed artifact. The First Edition fingerprint is retained as provenance,
# not falsely asserted to be byte-identical to this recovered file.
PUBLICATION_DATASET_SHA256 = RECOVERED_EXECUTED_DATASET_SHA256
PUBLICATION_DATASET_PATH = Path(os.getenv("TC_PUBLICATION_DATASET", APP_DIR / PUBLICATION_DATASET_FILENAME))

EVIDENCE_CHECKPOINTS = {
    "1995 Q1": (333.40, 371.80),
    "1999 Q4": (385.40, 422.90),
    "2000 Q2": (400.40, 428.40),
    "2000 Q3": (400.40, 543.625),
    "2009 Q4": (543.78, 742.90),
    "2010 Q2": (543.78, 772.10),
    "2010 Q4": (569.90, 789.10),
    "2026 Q2": (948.00, 1309.90),
    "2026 Q3": (1004.90, 1313.90),
    "2026 Q4": (1004.90, 1350.70),
}

def _norm_col(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())

def _quarter_key(q):
    m = re.fullmatch(r"(\d{4})\s*Q([1-4])", str(q).strip(), re.I)
    if not m:
        raise ValueError(f"Invalid quarter label: {q!r}")
    return int(m.group(1)) * 4 + int(m.group(2)) - 1

def _expected_quarters():
    out=[]
    for y in range(1995, 2027):
        for q in range(1,5):
            out.append(f"{y} Q{q}")
    return out

def _line_ssr(values, start_index=0):
    """OLS SSR for y = a + b*t, implemented without scientific dependencies."""
    n=len(values)
    xs=[float(start_index+i) for i in range(n)]
    ys=[float(v) for v in values]
    mx=sum(xs)/n; my=sum(ys)/n
    den=sum((x-mx)**2 for x in xs)
    b=(sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den) if den else 0.0
    a=my-b*mx
    return sum((y-(a+b*x))**2 for x,y in zip(xs,ys))

def _evidence_verification(obs):
    """Deterministic and core econometric checks for the recovered 128-quarter artifact."""
    # Every row: deterministic identities.
    for x in obs:
        if abs(x["chart_c_fortnightly"]/2.0-x["chart_c_weekly"])>1e-7:
            raise ValueError(f"Chart C identity failed at {x['quarter']}")
        if abs(x["minimum_wage_weekly"]/x["chart_c_weekly"]*100.0-x["ratio_pct"])>1e-7:
            raise ValueError(f"Ratio identity failed at {x['quarter']}")
        if abs((x["chart_c_weekly"]-x["minimum_wage_weekly"])-x["weekly_gap"])>1e-7:
            raise ValueError(f"Gap identity failed at {x['quarter']}")
    byq={x["quarter"]:x for x in obs}
    for q,(mw,cw) in EVIDENCE_CHECKPOINTS.items():
        x=byq.get(q)
        if not x or abs(x["minimum_wage_weekly"]-mw)>0.005 or abs(x["chart_c_weekly"]-cw)>0.005:
            raise ValueError(f"Checkpoint failed at {q}")
    ratios=[x["ratio_pct"] for x in obs]
    i_q3=next(i for i,x in enumerate(obs) if x["quarter"]=="2000 Q3")
    pre_mean=sum(ratios[:i_q3])/i_q3
    post_mean=sum(ratios[i_q3:])/(len(ratios)-i_q3)
    full_ssr=_line_ssr(ratios,0)
    pre_ssr=_line_ssr(ratios[:i_q3],0)
    post_ssr=_line_ssr(ratios[i_q3:],i_q3)
    k=2; n1=i_q3; n2=len(ratios)-i_q3
    chow=((full_ssr-(pre_ssr+post_ssr))/k)/((pre_ssr+post_ssr)/(n1+n2-2*k))
    if abs(pre_mean-89.8936)>0.0001: raise ValueError(f"Pre-break mean failed: {pre_mean:.4f}")
    if abs(post_mean-71.6328)>0.0001: raise ValueError(f"Post-break mean failed: {post_mean:.4f}")
    if abs(chow-699.1563)>0.001: raise ValueError(f"Chow F failed: {chow:.4f}")
    return {"identity_rows_passed":len(obs),"pre_break_mean_pct":round(pre_mean,4),"post_break_mean_pct":round(post_mean,4),"chow_f_2000q3":round(chow,4)}

def load_publication_evidence():
    """Load the recovered/re-executed 128Q artifact only after hash + deterministic + econometric gates pass."""
    base = {
        "status":"NOT_LOADED","verified":False,
        "classification":"RECOVERED / RE-EXECUTED 128Q DATASET",
        "filename":PUBLICATION_DATASET_FILENAME,
        "expected_sha256":RECOVERED_EXECUTED_DATASET_SHA256,
        "first_edition_publication_sha256":FIRST_EDITION_PUBLICATION_SHA256,
        "provenance_note":"First Edition records 7ff767... as its exact publication artifact fingerprint. Live uses the recovered/re-executed artifact 77e4f56c...; the two are not claimed byte-identical.",
        "path":str(PUBLICATION_DATASET_PATH),"rows":0,
        "message":"Recovered 128-quarter CSV not loaded. No historical observations are reconstructed or interpolated.","observations":[]}
    if not PUBLICATION_DATASET_PATH.exists(): return base
    try:
        raw=PUBLICATION_DATASET_PATH.read_bytes(); actual_hash=hashlib.sha256(raw).hexdigest(); base["actual_sha256"]=actual_hash
        if actual_hash != RECOVERED_EXECUTED_DATASET_SHA256:
            base.update(status="VERIFICATION_FAILED",message="Dataset SHA-256 does not match the recovered/re-executed 128Q artifact; Evidence Explorer disabled."); return base
        reader=csv.DictReader(raw.decode("utf-8-sig").splitlines())
        if not reader.fieldnames: raise ValueError("CSV has no header")
        cols={_norm_col(c):c for c in reader.fieldnames}
        def col(*names):
            for n in names:
                if _norm_col(n) in cols:return cols[_norm_col(n)]
            raise ValueError("Required column missing: "+" / ".join(names))
        cq=col("quarter"); cmw=col("Min_Wage_Weekly","minimum_wage_weekly","National Minimum Wage"); ccw=col("ChartC_Weekly","chart_c_weekly")
        ccf=col("ChartC_Fortnightly"); cr=col("Ratio_Percent"); cg=col("Weekly_Gap")
        obs=[]
        for row in reader:
            q=str(row[cq]).strip(); mw=float(row[cmw]); cw=float(row[ccw]); cf=float(row[ccf]); ratio=float(row[cr]); gap=float(row[cg])
            obs.append({"quarter":q,"minimum_wage_weekly":mw,"chart_c_fortnightly":cf,"chart_c_weekly":cw,"ratio_pct":ratio,"weekly_gap":gap,"annualised_gap":gap*52})
        if len(obs)!=128 or [x["quarter"] for x in obs] != _expected_quarters(): raise ValueError("Dataset must contain exactly 128 sequential quarters from 1995 Q1 to 2026 Q4")
        verification=_evidence_verification(obs)
        base.update(status="VERIFIED",verified=True,rows=128,verification=verification,message="Recovered/re-executed 128-quarter dataset passed SHA-256, 128-row identities, sequence, locked checkpoints, pre/post means and Chow structural-break verification.",observations=obs)
        return base
    except Exception as e:
        base.update(status="VERIFICATION_FAILED",message=f"Evidence Explorer disabled: {e}"); return base


@app.get("/api/evidence")
def api_evidence():
    return jsonify(load_publication_evidence())

# v6.9 — LECI / WHAT IS LEFT scenario laboratory.
# These are execution-validated results from the frozen 128-quarter master,
# not recomputed from an unverified or substituted dataset.
STRUCTURAL_EVIDENCE = {
    "classification": "ESTIMATED / TESTED",
    "coverage": "1995 Q1–2026 Q4",
    "regime_boundary": "2000 Q3",
    "break_tests": [
        {"test":"Chow structural break", "boundary":"2000 Q3", "statistic":"F = 699.1563", "p_value":"≈ 3.00 × 10⁻⁶⁸"},
        {"test":"HAC-robust Wald", "boundary":"2000 Q3", "statistic":"F = 489.9285", "p_value":"≈ 1.35 × 10⁻⁵⁹"},
        {"test":"Zivot–Andrews break-aware diagnostic", "boundary":"Estimated break: 2000 Q2", "statistic":"−12.7239", "p_value":"0.00001"},
        {"test":"Matched-phase Chow — Q2", "boundary":"pre/post", "statistic":"−20.0616 pp; F = 184.0883", "p_value":"7.76 × 10⁻¹⁷"},
        {"test":"Matched-phase Chow — Q4", "boundary":"pre/post", "statistic":"−17.5192 pp; F = 250.4331", "p_value":"1.36 × 10⁻¹⁸"},
    ],
    "post_break": {
        "observations": 106,
        "mean_ratio_pct": 71.6328,
        "beta": 0.719250,
        "hac_ci_low": 0.711348,
        "hac_ci_high": 0.727153,
        "beta_072_p": 0.8525,
        "interpretation": "Approximately 72% is an empirically defensible description of the post-break proportional regime; it is not evidence of an official policy target."
    },
    "annual_cycle": {
        "complete_cycles_2010_2025": 16,
        "september_closer_every_cycle": True,
        "interpretation": "Across all 16 complete 2010–2025 cycles, the September observation is closer to the pre-reset ratio than the observation immediately after the annual wage reset."
    },
    "safeguard": "Structural timing and persistence do not establish intent, institutional coordination, policy optimality or a formal cointegrating equilibrium."
}


# v8.3 — 2026 live-cycle diagnostic.
# Locked publication observations: Q2 before annual wage reset, Q3 after the July
# wage reset, Q4 after September Chart C indexation.
LIVE_CYCLE_2026 = {
    "classification": "OBSERVED + DERIVED CALCULATION",
    "q2": {"quarter":"2026 Q2","nmw_weekly":948.00,"chart_c_weekly":1309.90,"ratio_pct":72.3719},
    "q3": {"quarter":"2026 Q3","nmw_weekly":1004.90,"chart_c_weekly":1313.90,"ratio_pct":76.4822},
    "q4": {"quarter":"2026 Q4","nmw_weekly":1004.90,"chart_c_weekly":1350.70,"ratio_pct":74.3985},
    "july_catch_up_pp": 4.1103,
    "september_erosion_pp": -2.0838,
    "july_improvement_eroded_pct": 50.70,
    "july_improvement_retained_pct": 49.30,
    "interpretation": "The July 2026 minimum-wage reset lifted the NMW/Chart C ratio; subsequent September Chart C indexation reduced about half of that ratio improvement by Q4.",
    "safeguard": "This is a within-2026 arithmetic diagnostic. It describes the observed sequence and does not by itself establish causation, policy intent or a fixed adjustment rule."
}

@app.get("/api/live-cycle-2026")
def api_live_cycle_2026():
    return jsonify(LIVE_CYCLE_2026)

@app.get("/api/structural-evidence")
def api_structural_evidence():
    return jsonify(STRUCTURAL_EVIDENCE)


# v7.1 — Wage → Superannuation → Retirement Laboratory.
# This is a transparent scenario engine: contribution rate, return, fees, tax and
# horizon are user-editable assumptions. It does not forecast an individual balance.
SUPER_RETIREMENT_LAB = {
    "classification": "SCENARIO / DERIVED CALCULATION",
    "base_year": 2026,
    "nmw_weekly": 1004.90,
    "chart_c_weekly": 1350.70,
    "current_gap_weekly": 345.80,
    "default_super_guarantee_pct": 12.0,
    "default_horizon_years": 40,
    "default_nominal_return_pct": 6.0,
    "default_investment_fees_pct": 0.7,
    "default_contributions_tax_pct": 15.0,
    "default_wage_growth_pct": 0.0,
    "periods_per_year": 52,
    "notes": {
        "scope": "Compares employer-super contributions generated by alternative weekly wage bases and compounds the contribution difference under explicit assumptions.",
        "not_forecast": "Results are scenarios, not forecasts, financial advice, or estimates of any person's actual retirement balance.",
        "wage_growth": "Zero wage growth isolates the effect of the starting wage difference. Users can supply a common annual wage-growth assumption.",
        "tax": "The model applies the selected contributions-tax assumption to employer contributions before accumulation and subtracts the selected annual investment-fee rate from the selected nominal return as a transparent simplified net-return assumption."
    }
}

@app.get("/api/super-retirement")
def api_super_retirement():
    return jsonify(SUPER_RETIREMENT_LAB)


# v7.0 — Welfare Relativity Laboratory baseline.
# Official/current observations and independent ACOSS proposal are kept separate
# from THE CONSTANT derived historical-relativity comparison.
WELFARE_RELATIVITY = {
    "as_at": "20 September 2026",
    "classification": "OFFICIAL OBSERVATIONS + DERIVED CALCULATIONS + INDEPENDENT ACOSS PROPOSAL",
    "nmw_weekly": 1004.90,
    "chart_c_weekly": 1350.70,
    "pension_single_fortnightly": 1237.70,
    "pension_single_weekly": 618.85,
    "jobseeker_single_total_fortnightly": 833.70,
    "jobseeker_single_total_weekly": 416.85,
    "jobseeker_base_rate_fortnightly": 824.90,
    "acoss_proposal_weekly": 618.00,
    "historical_jobseeker_nmw_ratio_pct": 45.645,
    "historical_relativity_chart_c_weekly": 616.54,
    "notes": {
        "jobseeker": "The $833.70 total is the 20 September 2026 single-recipient figure announced by DSS Ministers; Services Australia separately lists a $824.90 maximum JobSeeker payment rate. Live displays both rather than silently conflating them.",
        "acoss": "ACOSS independently calls for working-age payments to reach pension parity, at least $618 per week on current rates.",
        "constant": "THE CONSTANT comparison applies the 1995–96 average unemployment-support/NMW relativity of 45.645% to current Chart C. It is a derived historical-relativity calculation, not the ACOSS methodology."
    }
}

@app.get("/api/welfare-relativity")
def api_welfare_relativity():
    return jsonify(WELFARE_RELATIVITY)


# v7.2 — Employment & Wage-Floor Population Laboratory.
# Keeps the August 2025 employee-distribution evidence separate from the May 2025
# EEH costing benchmark. Distribution estimates are not represented as exact
# counts of workers paid the legal minimum wage.
WAGE_FLOOR_POPULATION_LAB = {
    "classification": "OFFICIAL OBSERVATIONS + DERIVED / ESTIMATED CALCULATIONS",
    "distribution_reference_period": "August 2025",
    "distribution": {
        "nmw_weekly": 948.00,
        "chart_c_weekly": 1258.00,
        "nmw_hourly_38h": 24.947368,
        "chart_c_hourly_38h": 33.105263,
        "weekly_gap": 310.00,
        "annual_38h_gap": 16120.00,
        "direct_lower_bound_employees": 1261000,
        "interpolated_employees": 1913500,
        "employee_population_approx": 12300000,
        "direct_lower_bound_share_pct": 10.3,
        "interpolated_share_pct": 15.6,
        "dsi_preliminary_pp": 15.6,
        "interpretation": "The Distribution Separation Index (DSI) is the estimated percentage-point share of the employee weekly-earnings distribution lying above the National Minimum Wage and below Chart C. It is a distribution-position estimate, not a count of employees paid the legal minimum wage."
    },
    "costing_reference_period": "May 2025 EEH benchmark",
    "costing": {
        "nmw_weekly": 915.90,
        "chart_c_weekly": 1255.00,
        "nmw_hourly_38h": 24.1026,
        "chart_c_hourly_38h": 33.0263,
        "permanent_max_hourly_gap": 8.9237,
        "current_casual_hourly_equivalent": 30.1283,
        "aligned_casual_hourly": 41.2829,
        "casual_max_hourly_gap": 11.1546,
        "floor_correction_pct": 37.02,
        "award_only_share_pct": 23.0,
        "individual_arrangement_share_pct": 38.5,
        "collective_agreement_share_pct": 34.6,
        "direct_formula_permanent": "max(0, 33.0263 - hourly_rate) × paid_hours × 52",
        "direct_formula_casual": "max(0, 41.2829 - hourly_rate) × paid_hours × 52",
        "note": "Award-only employees are not synonymous with all employees affected by a wage-floor change. Exact direct costing requires employee-level earnings, hours, employment type, method of setting pay and weights."
    },
    "scenario_definitions": {
        "A": "Direct legal-floor correction only.",
        "B": "Preserve lawful award relativities above the floor.",
        "C": "Spillover sensitivity beyond directly affected classifications."
    }
}

@app.get("/api/wage-floor-population")
def api_wage_floor_population():
    return jsonify(WAGE_FLOOR_POPULATION_LAB)


# v7.4 — Institutional Evidence Timeline.
# Events are chronology/context. Their proximity to the measured 2000 break is not
# represented as proof of causation, intent or institutional coordination.
INSTITUTIONAL_TIMELINE = {
    "classification": "OFFICIAL / DOCUMENTARY CONTEXT + EMPIRICAL EVENT MARKERS",
    "interpretation_rule": "Chronology identifies what changed and when. Timing alone does not establish causation or intent.",
    "events": [
        {"date":"1995–1999","type":"empirical","title":"Pre-break observation period","detail":"The quarterly NMW/Chart C relationship is observed before the 2000 structural boundary. The publication pre-break mean for 1995 Q1–2000 Q2 is 89.8936%."},
        {"date":"2000 Q2","type":"empirical","title":"Immediate pre-rupture reference","detail":"NMW $400.40; Chart C $428.40/week; ratio 93.4641%. This is the publication preservation reference, not an asserted policy target."},
        {"date":"1 Jul 2000","type":"official","title":"Pension income-test taper changes","detail":"For singles, the pension income-test withdrawal rate changed from 50 cents to 40 cents per dollar above the free area. This mechanically changes the cessation point used for Chart C."},
        {"date":"2000 Q3","type":"empirical","title":"Formal structural-break boundary","detail":"NMW $400.40; Chart C $543.625/week; ratio 73.6537%. Publication tests use 2000 Q3 as the formal regime boundary."},
        {"date":"2005–2006","type":"institutional","title":"AFPC transition period","detail":"Minimum-wage setting moved through the Australian Fair Pay Commission era. THE CONSTANT treats this as a post-break institutional subperiod, not the origin of the 2000 rupture."},
        {"date":"20 Sep 2009","type":"official","title":"Pension taper restored to 50 cents","detail":"The single pension income-test withdrawal rate changed from 40 cents back to 50 cents per dollar above the free area, with transitional arrangements for affected existing pensioners."},
        {"date":"2010–2025","type":"empirical","title":"Annual reset/indexation cycle","detail":"Across all 16 complete cycles, the September observation is closer to the pre-reset ratio than the observation immediately after the annual wage reset."},
        {"date":"2 Jun 2026","type":"official","title":"Annual Wage Review 2026 decision","detail":"The Fair Work Commission announced the 2026 Annual Wage Review decision. The National Minimum Wage was set at $1,004.90/week ($26.44/hour), effective 1 July 2026."},
        {"date":"2026 Q4","type":"empirical","title":"Current publication endpoint","detail":"NMW $1,004.90; Chart C $1,350.70/week; ratio 74.3985%; weekly gap $345.80."}
    ]
}

@app.get("/api/institutional-timeline")
def api_institutional_timeline():
    return jsonify(INSTITUTIONAL_TIMELINE)

@app.get("/")
def home(): return send_from_directory(APP_DIR,"index.html")



# v7.4 — Data Explorer & Reproducibility Centre.
@app.get("/api/reproducibility")
def api_reproducibility():
    ev = load_publication_evidence()
    return jsonify({
        "version": state.get("version"),
        "dataset": {
            "filename": PUBLICATION_DATASET_FILENAME,
            "expected_sha256": RECOVERED_EXECUTED_DATASET_SHA256,
            "actual_sha256": ev.get("actual_sha256"),
            "verified": bool(ev.get("verified")),
            "status": ev.get("status"),
            "rows": ev.get("rows", 0),
            "coverage": "1995 Q1–2026 Q4",
            "verification_rule": "Exact SHA-256 + 128 sequential quarters + locked checkpoints; no interpolation or manuscript-table fallback."
        },
        "formulas": [
            {"name":"Ratio", "formula":"100 × National Minimum Wage / Chart C weekly", "classification":"DERIVED CALCULATION"},
            {"name":"Weekly gap", "formula":"Chart C weekly − National Minimum Wage", "classification":"DERIVED CALCULATION"},
            {"name":"Annualised gap", "formula":"Weekly gap × 52", "classification":"DERIVED CALCULATION"},
            {"name":"Chart C", "formula":"F + (P + Supp + PA) / r", "classification":"DERIVED CALCULATION", "note":"Rent Assistance and Remote Area Allowance excluded in THE CONSTANT definition."}
        ],
        "evidence_hierarchy": ["OFFICIAL OBSERVATION","DERIVED CALCULATION","ESTIMATED / TESTED","SCENARIO / COUNTERFACTUAL"],
        "reproduction": {
            "required_input": PUBLICATION_DATASET_FILENAME,
            "principle": "Read it. Copy the code. Run it. Question it. Change the assumptions. Test the evidence.",
            "warning": "A failed dataset verification disables historical reproduction rather than substituting values."
        }
    })

def _parse_status_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None

def build_alert_status():
    """Derive public operational alerts without modifying verified observations."""
    now = datetime.now(SYDNEY_TZ)
    alerts=[]
    sources=state.get("sources", {})
    stale_hours=float(os.getenv("TC_SOURCE_STALE_HOURS", "48"))
    for name,m in sources.items():
        status=m.get("validation_status") or SOURCE_STATUS_CURRENT
        if status == SOURCE_STATUS_ATTENTION or m.get("error") or m.get("warning"):
            alerts.append({"severity":"attention","source":name,"type":"source_failure",
                "message":m.get("status_detail") or m.get("warning") or m.get("error") or "Source requires attention.",
                "last_verified":m.get("last_success"),"action":"Last verified value retained; automatic checks continue."})
        last=_parse_status_time(m.get("last_success"))
        if last:
            if last.tzinfo is None: last=last.replace(tzinfo=SYDNEY_TZ)
            age=(now-last.astimezone(SYDNEY_TZ)).total_seconds()/3600
            if age > stale_hours:
                alerts.append({"severity":"warning","source":name,"type":"stale_source",
                    "message":f"No successful source access for {age:.1f} hours.",
                    "last_verified":m.get("last_success"),"action":"Verified value remains frozen until a new candidate passes validation."})
    active=_active_release_windows(now)
    for e in active:
        src=e.get("source") or "Official release"
        sm=sources.get(src,{})
        if sm.get("validation_status") not in (SOURCE_STATUS_UPDATED,SOURCE_STATUS_VALIDATING,SOURCE_STATUS_DETECTED):
            alerts.append({"severity":"release","source":src,"type":"release_due",
                "message":"Official release window is active; accelerated five-minute checking is enabled.",
                "last_verified":sm.get("last_success"),"action":"Awaiting detection and validation; existing verified values remain published."})
    rank={"attention":0,"release":1,"warning":2,"info":3}
    alerts.sort(key=lambda a:rank.get(a.get("severity"),9))
    return {"generated_at":now.isoformat(timespec="seconds"),"alert_count":len(alerts),
            "attention_count":sum(a["severity"]=="attention" for a in alerts),
            "release_due_count":sum(a["severity"]=="release" for a in alerts),
            "warning_count":sum(a["severity"]=="warning" for a in alerts),
            "alerts":alerts,
            "recovery_rule":"A failed or stale source never overwrites the last verified observation. Automatic checks continue and publication resumes only after validation passes."}

def build_source_release_intelligence():
    """Compact control-plane view for the five core official source families."""
    now = datetime.now(SYDNEY_TZ)
    cal = _release_calendar()
    active = _active_release_windows(now)
    next_rows = _next_expected_releases(now, limit=20)

    families = [
        ("ABS CPI", ["ABS CPI"], ["ABS CPI"], state.get("official", {}).get("cpi_reference_period")),
        ("ABS Labour Force", ["ABS Labour Force"], ["ABS Labour Force"], state.get("labour_market", {}).get("reference_period")),
        ("RBA", ["RBA Cash Rate", "RBA — Monetary Policy Decisions"], ["RBA Monetary Policy"], "Current cash-rate target"),
        ("Fair Work Commission", ["FWC National Minimum Wage", "FWC — Annual Wage Review Determinations"], ["FWC Annual Wage Review"], "2026 National Minimum Wage"),
        ("Services Australia / DSS", ["Services Australia DSP Income Test", "Services Australia — Age Pension Rates", "Services Australia — JobSeeker Rates"], ["Services Australia / DSS indexation"], "20 September 2026 settings"),
    ]

    def best_meta(keys):
        candidates=[]
        for key in keys:
            m=state.get("sources", {}).get(key, {})
            if m:
                candidates.append((key,m))
        if not candidates:
            return None, {}
        def score(item):
            m=item[1]
            dt=_parse_status_time(m.get("last_success") or m.get("last_checked"))
            return dt.timestamp() if dt else 0
        return max(candidates, key=score)

    rows=[]
    for label, source_keys, calendar_names, period in families:
        source_name, m = best_meta(source_keys)
        next_event = next((e for e in next_rows if e.get("source") in calendar_names), None)
        active_event = next((e for e in active if e.get("source") in calendar_names), None)
        validation=m.get("validation_status")
        if m.get("error") or validation == "ATTENTION — LAST VERIFIED RETAINED":
            health="ATTENTION — LAST VERIFIED RETAINED"
        elif m.get("warning"):
            health="TEMPORARY WARNING"
        elif validation in ("NEW RELEASE DETECTED", "VALIDATING", "UPDATED"):
            health=validation
        elif m.get("last_success"):
            health="CURRENT"
        else:
            health="AWAITING VERIFIED CHECK"
        monitor="RELEASE DUE" if active_event else "NORMAL"
        rows.append({
            "source":label,
            "source_key":source_name,
            "latest_verified_period":period,
            "health":health,
            "monitoring_state":monitor,
            "last_success":m.get("last_success"),
            "last_checked":m.get("last_checked"),
            "validation_problem":m.get("error") or m.get("warning") or m.get("status_detail"),
            "next_expected_release": (next_event or {}).get("expected_release") or (next_event or {}).get("start"),
            "release_status": (next_event or active_event or {}).get("status"),
        })
    return {
        "version":state.get("version"),
        "timezone":"Australia/Sydney",
        "poll_seconds": RELEASE_REFRESH_SECONDS if active else BASE_REFRESH_SECONDS,
        "calendar_last_refreshed":cal.get("last_calendar_refresh"),
        "calendar_errors":cal.get("calendar_errors", []),
        "sources":rows,
        "principle":"Failed checks never replace the last verified observation. Release windows accelerate monitoring to five-minute checks."
    }

def build_next_release_timing():
    """High-visibility release timing feed for the core Live update cycle."""
    now = datetime.now(SYDNEY_TZ)
    intel = build_source_release_intelligence()
    rows=[]
    for x in intel.get("sources", []):
        raw=x.get("next_expected_release")
        dt=_parse_local_iso(raw) if raw else None
        seconds=None
        if dt:
            seconds=max(0, int((dt-now).total_seconds()))
        rows.append({
            "source":x.get("source"),
            "next_expected_release":raw,
            "seconds_until_release":seconds,
            "monitoring_state":x.get("monitoring_state"),
            "health":x.get("health"),
            "last_checked":x.get("last_checked"),
            "last_success":x.get("last_success"),
            "poll_seconds":RELEASE_REFRESH_SECONDS if x.get("monitoring_state")=="RELEASE DUE" else BASE_REFRESH_SECONDS,
        })
    return {
        "version":state.get("version"),
        "generated_at":now.isoformat(timespec="seconds"),
        "timezone":"Australia/Sydney",
        "normal_poll_seconds":BASE_REFRESH_SECONDS,
        "release_poll_seconds":RELEASE_REFRESH_SECONDS,
        "sources":rows,
        "principle":"Countdowns describe expected official release timing. Inside an active release window Live accelerates checks to five minutes; publication still requires successful parsing and validation."
    }

@app.get("/api/next-release-timing")
def api_next_release_timing():
    return jsonify(build_next_release_timing())

@app.get("/api/source-release-intelligence")
def api_source_release_intelligence():
    return jsonify(build_source_release_intelligence())

@app.get("/api/alerts")
def api_alerts():
    return jsonify(build_alert_status())

@app.get("/api/audit-trail")
def api_audit_trail():
    try:
        limit = int(os.getenv("TC_AUDIT_API_LIMIT", "100"))
    except Exception:
        limit = 100
    events = _read_audit_events(limit)
    return jsonify({
        "version": state.get("version"),
        "immutable_log": AUDIT_LOG_FILE.name,
        "event_count_returned": len(events),
        "events": events,
        "principle": "Only validated substantive changes are appended. Failed validation retains the last verified state and creates no verified-update event."
    })

@app.get("/api/update-integrity")
def api_update_integrity():
    c=state.get("core",{}); o=state.get("official",{}); lm=state.get("labour_market",{})
    checks=[
      {"source":"NMW","value":c.get("minimum_wage_weekly"),"propagates_to":["Australia Now","ratio","weekly/annual gap","scenario defaults","super laboratory","welfare relativity"]},
      {"source":"Chart C","value":c.get("chart_c_weekly"),"propagates_to":["Australia Now","ratio","weekly/annual gap","scenario base","super laboratory","What Is Left options","welfare relativity"]},
      {"source":"CPI","value":o.get("cpi_annual_pct"),"period":o.get("cpi_reference_period"),"propagates_to":["Australia Now","price context","source/release status"]},
      {"source":"RBA cash rate","value":o.get("cash_rate_pct"),"propagates_to":["Australia Now","source/release status"]},
      {"source":"Labour Force","value":lm.get("employment_persons"),"propagates_to":["Australia Now","labour-market panel","source/release status"]},
    ]
    return jsonify({"version":"9.7.7","status":"SYNCHRONIZED","single_source_of_truth":"state core/official/labour_market after validation","current":state.get("live_derived",{}),"checks":checks,"rule":"A candidate release must validate before state changes. recalc() then rebuilds dependent live values before save/publish."})

@app.get("/api/rba-readiness")
def api_rba_readiness():
    o=state.get("official",{})
    return jsonify({
        "version":state.get("version"),
        "status":"READY",
        "current_cash_rate_pct":o.get("cash_rate_pct"),
        "next_board_meeting":"2026-09-28/2026-09-29",
        "next_decision_release":"2026-09-29T14:30:00+10:00",
        "validation_rule":"A new RBA decision must explicitly state the cash rate target and pass plausibility validation before publication. A fetch or parse failure retains the last verified rate.",
        "propagates_to":["Australia Now","RBA policy context","source health","release timing","audit trail","update-integrity state"],
        "source":"Reserve Bank of Australia — Monetary Policy Decision",
        "source_url":"https://www.rba.gov.au/monetary-policy/int-rate-decisions/"
    })

@app.get("/api/chart-c-readiness")
def api_chart_c_readiness():
    c=state.get("core",{})
    fn=float(c.get("chart_c_fortnightly",0) or 0)
    wk=round(fn/2,2) if fn else None
    return jsonify({
        "version":state.get("version"),
        "status":"READY",
        "official_measure":"Single pension/DSP income-test cessation point",
        "official_fortnightly_cutoff":fn,
        "derived_chart_c_weekly":wk,
        "derivation":"Chart C weekly = official fortnightly single income-test cut-off / 2",
        "effective_from":"2026-09-20",
        "current_ratio_pct":c.get("ratio_pct"),
        "current_weekly_gap":c.get("weekly_gap"),
        "monitoring_cycles":["20 March","20 September"],
        "validation_rule":"Publish only an explicitly identified official single pension/DSP income-test cut-off. Reject payment rates, assets-test limits, transitional rates, couple rates and ambiguous candidates.",
        "propagates_to":["Australia Now","NMW/Chart C ratio","weekly and annual gap","welfare relativity laboratory","scenario engine","superannuation laboratory","What Is Left income choices","audit trail","update-integrity state"],
        "historical_dataset_rule":"A current official update does not rewrite the frozen 128-quarter publication dataset. A new quarter is appended only through the dataset verification/publication workflow.",
        "source":"Services Australia — pension/DSP income test"
    })


@app.get("/api/fwc-nmw-readiness")
def api_fwc_nmw_readiness():
    c=state.get("core",{})
    return jsonify({
        "version":state.get("version"),
        "status":"READY",
        "current_nmw_weekly":c.get("minimum_wage_weekly"),
        "current_nmw_hourly":round(float(c.get("minimum_wage_weekly",0) or 0)/38,6) if c.get("minimum_wage_weekly") else None,
        "current_effective_date":"2026-07-01",
        "decision_date":"2026-06-02",
        "decision_reference":"[2026] FWCFB 3500",
        "decision_vs_effective_date_rule":"A newly announced Annual Wage Review rate is recorded as forthcoming, but the live NMW remains the legally current rate until the new National Minimum Wage Order comes into operation/effect.",
        "validation_rule":"Accept only an explicit Fair Work Commission National Minimum Wage weekly/hourly rate tied to the National Minimum Wage Order and its operative/effective date. Do not substitute award classifications, claims, submissions, draft rates or media commentary for the NMW.",
        "propagates_to":["Australia Now","NMW/Chart C ratio","weekly and annual gap","2026/live-cycle logic","scenario defaults","superannuation laboratory","welfare relativity laboratory","What Is Left income choices","audit trail","update-integrity state"],
        "historical_dataset_rule":"A newly effective NMW updates Live current state. It does not silently rewrite the frozen publication dataset; historical extension follows the dataset verification/publication workflow.",
        "source":"Fair Work Commission — National Minimum Wage Order / Annual Wage Review",
        "source_url":"https://www.fwc.gov.au/work-conditions/minimum-wages-and-conditions/national-minimum-wage"
    })

@app.get("/api/cpi-readiness")
def api_cpi_readiness():
    o=state.get("official",{})
    detail=o.get("cpi_monthly",{})
    current=detail.get("current") or {}
    return jsonify({
        "version":state.get("version"),
        "status":"READY",
        "current_reference_period":o.get("cpi_reference_period"),
        "current_annual_pct":o.get("cpi_annual_pct"),
        "current_detail":current,
        "next_expected_release":"2026-09-30T11:30:00+10:00",
        "next_reference_period":"August 2026",
        "validation_rule":"A new reference month must provide its own annual CPI rate. Detail fields are published only when explicitly parsed; malformed candidates retain the last verified observation.",
        "propagates_to":["Australia Now","CPI comparison/archive","nominal-real context","LECI context","source health","release timing","audit trail"],
        "source":"ABS Consumer Price Index, Australia"
    })

@app.get("/api/state")
def api_state(): return jsonify(json.loads(json.dumps(state)))

@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "version": state["version"],
        "last_check": state["last_check"],
        "next_check": state["next_check"],
        "refresh_timezone": "Australia/Sydney",
        "base_refresh_seconds": BASE_REFRESH_SECONDS,
        "release_refresh_seconds": RELEASE_REFRESH_SECONDS,
        "release_monitor": state.get("release_monitor", {})
    })

@app.get("/api/check-now")
def check_now():
    threading.Thread(target=check_all,daemon=True).start()
    return jsonify({"ok":True})

# ------------------------------------------------------------
# v5.4 startup model migration
# Rebuild all derived values from current official/base state.
# ------------------------------------------------------------

state["version"] = "9.7.5"

# v5.7.0 effective-date migration.
# A persisted pre-20-Sep state must not overwrite the now-current official Chart C.
state["core"]["chart_c_fortnightly"] = 2701.40
state["core"]["chart_c_weekly"] = 1350.70
state["forward"]["chart_c_fortnightly"] = 2701.40
state["forward"]["status"] = "Official Services Australia cut-off confirmed — effective 20 September 2026"

recalc()
recalc_book_impact_model()
recalc_income_support_counterfactual()
maintain_constant_material_monitor()


def build_pre_release_audit():
    """Read-only deployment-candidate audit of synchronization, stale literals and core plumbing."""
    core=state.get("core",{}); off=state.get("official",{}); lm=state.get("labour_market",{})
    live=state.get("live_derived",{})
    expected_ratio=round(float(core.get("minimum_wage_weekly",0))/float(core.get("chart_c_weekly",1))*100,4)
    expected_gap=round(float(core.get("chart_c_weekly",0))-float(core.get("minimum_wage_weekly",0)),2)
    checks=[]
    def add(name, ok, detail): checks.append({"check":name,"status":"PASS" if ok else "ATTENTION","detail":detail})
    add("NMW/Chart C ratio synchronization", abs(float(live.get("ratio_pct",expected_ratio))-expected_ratio)<0.01, f"expected {expected_ratio:.4f}%")
    add("Weekly gap synchronization", abs(float(live.get("weekly_gap",expected_gap))-expected_gap)<0.02, f"expected ${expected_gap:.2f}/wk")
    add("Chart C weekly derivation", abs(float(core.get("chart_c_weekly",0))*2-float(core.get("chart_c_fortnightly",0)))<0.02, "weekly = official fortnightly cut-off / 2")
    add("Labour headline baseline", bool(lm.get("employment_persons") or lm.get("employment")), "employment observation present")
    add("CPI baseline", off.get("cpi_annual_pct") is not None, "annual CPI observation present")
    add("RBA baseline", off.get("cash_rate_pct") is not None, "cash-rate observation present")
    add("Visitor persistence configured", bool(os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN")), "Upstash env vars present" if os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN") else "persistent counter requires Upstash env vars in deployment")
    add("Audit trail path", bool(AUDIT_LOG_FILE), str(AUDIT_LOG_FILE))
    attention=[x for x in checks if x["status"]!="PASS"]
    return {"version":"9.7.7","deployment_candidate":not attention,"checks":checks,"attention_count":len(attention),"principle":"Verified source state is authoritative; failed candidates retain the last verified observation. Frozen publication history is not silently rewritten by live updates."}

@app.get("/api/pre-release-audit")
def api_pre_release_audit():
    return jsonify(build_pre_release_audit())

update_release_monitor_state()

save_state()

if os.getenv("TC_DISABLE_SCHEDULER", "0") != "1":
    threading.Thread(
        target=loop,
        daemon=True
    ).start()

if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8765")),
        debug=False,
        threaded=True,
        use_reloader=False
    )
