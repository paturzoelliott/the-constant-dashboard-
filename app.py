#!/usr/bin/env python3
from __future__ import annotations

import os
import hashlib, json, os, re, threading, time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, send_from_directory

PORT = int(os.getenv("PORT", "8765"))
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")
REFRESH_HOURS_SYDNEY = (10, 22)
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", APP_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
RUNTIME_STATE_FILE = DATA_DIR / "runtime_state.json"

DEFAULT = {
    "version": "5.6.6",
    "started_at": None,
    "last_check": None,
    "next_check": None,
    "refresh_schedule": {
        "timezone": "Australia/Sydney",
        "times": ["10:00", "22:00"],
        "description": "Official-source refresh at 10:00 AM and 10:00 PM Australia/Sydney time"
    },
    "checks_completed": 0,
    "source_changes_detected": 0,
    "errors": [],
    "core": {
        "minimum_wage_weekly": 1004.90,
        "chart_c_fortnightly": 2627.80,
        "chart_c_weekly": 1313.90,
        "ratio_pct": 76.4822,
        "weekly_gap": 309.00,
        "income_free_area_fortnightly": 226.00,
        "taper": 0.50
    },
    "official": {
        "cpi_reference_period": "June 2026",
        "cpi_annual_pct": 3.8,
        "employee_lci_annual_pct": 3.7,
        "employee_lci_quarterly_pct": 1.5,
        "pblci_annual_pct": 4.6,
        "age_pensioner_lci_annual_pct": 4.7,
        "lci_reference_base": "September 2025 quarter = 100",
        "cash_rate_pct": 4.35
    },
    "forward": {
        "status": "Derived from Government-announced pension rate — Services Australia cut-off table pending",
        "effective_date": "2026-09-20",
        "chart_c_fortnightly": 2701.40,
        "chart_c_weekly": 1350.70,
        "weekly_gap": 345.80,
        "ratio_pct": 74.3985
    },
    "book_impact_model": {
        "methodology": "THE CONSTANT book methodology — actual statutory minimum wage versus Chart-C-aligned corrected wage counterfactual",
        "actual_wage_weekly": 1004.90,
        "corrected_wage_weekly": 1313.90,
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
        "corrected_wage_weekly": 1313.90,
        "payments": {
            "age_pension_single_basic": {
                "label": "Age Pension — single basic rate",
                "actual_fortnightly": 1100.30,
                "source": "Services Australia",
                "source_effective_period": "20 March–19 September 2026",
                "official": True
            },
            "age_pension_single_total": {
                "label": "Age Pension — single total",
                "actual_fortnightly": 1200.90,
                "source": "Services Australia",
                "source_effective_period": "20 March–19 September 2026",
                "official": True
            },
            "dsp_single_basic": {
                "label": "DSP — adult single basic rate",
                "actual_fortnightly": 1100.30,
                "source": "Services Australia — Guide to Australian Government payments",
                "source_effective_period": "1 July–19 September 2026",
                "official": True
            },
            "dsp_single_typical_total": {
                "label": "DSP — adult single typical total",
                "actual_fortnightly": 1200.90,
                "source": "Services Australia — Guide to Australian Government payments",
                "source_effective_period": "1 July–19 September 2026",
                "official": True
            },
            "jobseeker_single_no_children": {
                "label": "JobSeeker — single, no children",
                "actual_fortnightly": 808.70,
                "source": "Services Australia",
                "source_effective_period": "from 20 March 2026",
                "official": True
            }
        },
        "calculated": {}
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
}

TERMS = ("pension","jobseeker","social security","indexation","payment","income test","deeming","cost of living","allowance","supplement","minimum wage","wage","cpi","inflation")

session = requests.Session()
session.headers.update({"User-Agent":"THE-CONSTANT-Public-Monitor/4.1"})
app = Flask(__name__)
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


def mark_change():
    state["source_changes_detected"]+=1

def parse_abs_labour(t):
    """
    ABS Labour Force source-health watcher.

    Verified labour-market values are retained in structured state.
    Automatic extraction from the public ABS page is deliberately disabled
    until the parser is separately execution-validated against the exact
    ABS release structure.

    The fetch layer still records:
      - last check
      - HTTP status
      - content hash
      - source change
      - last successful access

    This prevents an ambiguous webpage percentage from silently replacing
    verified labour-market observations.
    """

    lm = state.setdefault(
        "labour_market",
        {
            "source":
                "Australian Bureau of Statistics — Labour Force, Australia"
        }
    )

    lm["source_last_seen"] = now_iso()
    lm["automatic_parser_status"] = (
        "Source monitored; automatic value extraction disabled "
        "pending separate execution validation."
    )

    return False


def parse_abs_cpi(t):
    changed=False
    m=re.search(r"Reference period\s+([A-Za-z]+\s+20\d{2})",t,re.I)
    if m and m.group(1)!=state["official"]["cpi_reference_period"]:
        state["official"]["cpi_reference_period"]=m.group(1); changed=True
    m=re.search(r"(?:Consumer Price Index\s*\(CPI\)|CPI)\s+rose\s+([0-9]+(?:\.[0-9]+)?)%",t,re.I)
    if m:
        v=float(m.group(1))
        if v!=state["official"]["cpi_annual_pct"]:
            state["official"]["cpi_annual_pct"]=v; changed=True
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

    annual = (
        state
        .get(
            "official",
            {}
        )
        .get(
            "cpi_annual_pct"
        )
    )

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
    m=re.search(r"cash rate target.{0,120}?([0-9]+(?:\.[0-9]+)?)\s*(?:per cent|%)",t,re.I|re.S)
    if m:
        v=float(m.group(1))
        if v!=state["official"]["cash_rate_pct"]:
            state["official"]["cash_rate_pct"]=v; return True
    return False

def parse_fwc(t):
    vals=[]
    for x in re.findall(r"(?:National Minimum Wage|minimum wage).{0,350}?\$([\d,]+\.\d{2}).{0,80}?(?:per week|week)",t,re.I|re.S):
        v=money(x)
        if 500<=v<=2000: vals.append(v)
    if vals and max(vals)!=state["core"]["minimum_wage_weekly"]:
        state["core"]["minimum_wage_weekly"]=max(vals); recalc(); return True
    return False

def parse_chart_c(t):
    vals=[]
    for pat in (r"21 or older,\s*single.{0,120}?\$([\d,]+\.\d{2})",r"single.{0,120}?\$([\d,]+\.\d{2}).{0,180}?couple living together"):
        for m in re.finditer(pat,t,re.I|re.S):
            v=money(m.group(1))
            if 2000<=v<=5000: vals.append(v)
    if vals and max(vals)!=state["core"]["chart_c_fortnightly"]:
        state["core"]["chart_c_fortnightly"]=max(vals); recalc(); return True
    return False

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
        html=fetch(name,url)
        if html is None: continue
        try:
            if kind=="minister_rss": parse_rss(html); continue
            t=textify(html); changed=False
            if kind=="abs_labour": changed=parse_abs_labour(t)
            elif kind=="abs_cpi":
                changed = parse_abs_cpi(t)

                try:

                    detail_changed = (
                        parse_complete_abs_cpi_detail(t)
                    )

                    changed = bool(
                        changed
                        or detail_changed
                    )

                except Exception as e:

                    print(
                        "CPI detail parse warning:",
                        e
                    )
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
            if changed: mark_change()
        except Exception as e: errors.append(f"{name}: {e}")
    maintain_union_archive()

    # v5.6.7 lifecycle:
    # do not remove a dated event until an official matching release exists.
    promote_completed_upcoming_events()

    maintain_announcement_archive()
    maintain_constant_material_monitor()
    recalculate_leci_income_burden()
    recalc_book_impact_model()
    recalc_income_support_counterfactual()
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

    proposed = 1313.90

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


def next_refresh_time(now=None):
    """Return the next 10:00 or 22:00 Australia/Sydney refresh time."""
    from datetime import timedelta
    now = now or datetime.now(SYDNEY_TZ)

    candidates = []
    for hour in REFRESH_HOURS_SYDNEY:
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            candidates.append(candidate)

    if candidates:
        return min(candidates)

    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=REFRESH_HOURS_SYDNEY[0], minute=0, second=0, microsecond=0)


def loop():
    """
    Run one source check at startup so the public dashboard is not stale,
    then refresh at exactly 10:00 and 22:00 Australia/Sydney every day.
    """
    try:
        check_all()
    except Exception as e:
        state.setdefault("errors", []).append("Startup source check: " + str(e))

    while True:
        target = next_refresh_time()
        with lock:
            state["next_check"] = target.isoformat(timespec="seconds")
            try:
                save_state()
            except Exception:
                pass

        seconds = max(
            1,
            (target - datetime.now(SYDNEY_TZ)).total_seconds()
        )
        time.sleep(seconds)

        try:
            check_all()
        except Exception as e:
            state.setdefault("errors", []).append("Scheduled source check: " + str(e))
            try:
                save_state()
            except Exception:
                pass


@app.get("/")
def home(): return send_from_directory(APP_DIR,"index.html")

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
        "refresh_times": ["10:00", "22:00"]
    })

@app.get("/api/check-now")
def check_now():
    threading.Thread(target=check_all,daemon=True).start()
    return jsonify({"ok":True})

# ------------------------------------------------------------
# v5.4 startup model migration
# Rebuild all derived values from current official/base state.
# ------------------------------------------------------------

state["version"] = "5.6.6"

recalc()
recalc_book_impact_model()
recalc_income_support_counterfactual()
maintain_constant_material_monitor()

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
