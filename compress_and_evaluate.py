import os
import json
import time
import argparse
from datetime import datetime
from google import genai
from typing import Any, Dict, List, Optional, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TOKEN = os.getenv("AIRTABLE_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

TBL_APPLICANTS = os.getenv("TBL_APPLICANTS", "Applicants")
TBL_PERSONAL   = os.getenv("TBL_PERSONAL_DETAILS", "Personal Details")
TBL_WORK       = os.getenv("TBL_WORK_EXPERIENCE", "Work Experience")
TBL_SALARY     = os.getenv("TBL_SALARY_PREFERENCES", "Salary Preferences")
TBL_SHORTLIST  = os.getenv("TBL_SHORTLISTED_LEADS", "Shortlisted Leads")

APPLICANT_LINK_FIELD = os.getenv("APPLICANT_LINK_FIELD", "Applicant")

GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL     = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
RUN_LLM_ALWAYS   = os.getenv("RUN_LLM_ALWAYS") == "1"
MOCK_LLM         = os.getenv("MOCK_LLM") == "1"

LLM_SUMMARY_FIELD   = os.getenv("LLM_SUMMARY_FIELD", "LLM Summary")
LLM_SCORE_FIELD     = os.getenv("LLM_SCORE_FIELD", "LLM Score")
LLM_ISSUES_FIELD    = os.getenv("LLM_ISSUES_FIELD", "LLM Issues")
LLM_FOLLOWUPS_FIELD = os.getenv("LLM_FOLLOWUPS_FIELD", "LLM Follow-Ups")

TIER1_COMPANIES = {
    "google","alphabet","meta","facebook","openai","apple","amazon","aws",
    "microsoft","netflix","stripe","airbnb","uber","lyft","databricks",
    "nvidia","tesla","doordash","snowflake"
}
ALLOWED_LOCATIONS = {
    "us","usa","united states","canada","ca","uk","united kingdom","great britain",
    "gb","germany","de","india","in"
}

def fetch_records(table: str, formula: Optional[str] = None):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
    params = {}
    if formula:
        params["filterByFormula"] = formula
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("records", [])

def update_record(table: str, record_id: str, fields: dict):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}/{record_id}"
    r = requests.patch(url, headers=HEADERS, json={"fields": fields}, timeout=30)
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        print("\n--- Airtable 4xx Debug ---")
        print("Table:", table)
        print("Record:", record_id)
        print("Fields we tried to write:", list(fields.keys()))
        print("Response:", r.status_code, r.text)
        print("--------------------------\n")
        raise
    return r.json()

def create_record(table: str, fields: dict):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
    r = requests.post(url, headers=HEADERS, json={"fields": fields}, timeout=30)
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        print("\n--- Airtable 4xx Debug (create) ---")
        print("Table:", table)
        print("Fields we tried to write:", list(fields.keys()))
        print("Response:", r.status_code, r.text)
        print("-------------------------------\n")
        raise
    return r.json()

def build_spec_json(personal_rows, exp_rows, salary_rows) -> Dict[str, Any]:
    personal = {}
    if personal_rows:
        f = personal_rows[0].get("fields", {})
        personal = {
            "name": f.get("Full Name"),
            "location": f.get("Location"),
        }
    experience = []
    for r in exp_rows:
        f = r.get("fields", {})
        company = f.get("Company")
        title = f.get("Title")
        if company or title:
            experience.append({"company": company, "title": title})
    salary = {}
    if salary_rows:
        f = salary_rows[0].get("fields", {})
        rate_val = f.get("Preferred Rate", f.get("Minimum Rate"))
        salary = {
            "rate": rate_val,
            "currency": f.get("Currency"),
            "availability": f.get("Availability (hrs/wk)"),
        }
    return {"personal": personal, "experience": experience, "salary": salary}

def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except:
            return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(value[:10], fmt)
            except:
                continue
    return None

def _total_years_experience(work_rows: List[Dict[str, Any]]) -> float:
    total_days = 0
    for r in work_rows:
        f = r.get("fields", {})
        start = _parse_date(f.get("Start"))
        end   = _parse_date(f.get("End")) or datetime.utcnow()
        if start:
            d = (end - start).days
            if d > 0:
                total_days += d
    return round(total_days / 365.25, 2)

def _worked_at_tier1(work_rows: List[Dict[str, Any]]) -> bool:
    for r in work_rows:
        company = str(r.get("fields", {}).get("Company", "")).strip().lower()
        if company and any(b in company for b in TIER1_COMPANIES):
            return True
    return False

def _num(v: Any, default: float = 0.0) -> float:
    try:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            digits = "".join(c for c in v if (c.isdigit() or c == "."))
            return float(digits) if digits else default
    except:
        pass
    return default

def shortlist_rules(personal_row: Dict[str, Any], work_rows: List[Dict[str, Any]], salary_row: Dict[str, Any]) -> Tuple[bool, str]:
    personal_f = (personal_row or {}).get("fields", {})
    salary_f   = (salary_row or {}).get("fields", {})
    years_exp = _total_years_experience(work_rows)
    tier1     = _worked_at_tier1(work_rows)
    rate  = _num(salary_f.get("Preferred Rate", salary_f.get("Minimum Rate")), 999.0)
    avail = _num(salary_f.get("Availability (hrs/wk)"), 0.0)
    location_raw = str(personal_f.get("Location", "")).lower()
    location_ok  = any(tok in location_raw for tok in ALLOWED_LOCATIONS)
    exp_ok   = (years_exp >= 4.0) or tier1
    rate_ok  = rate <= 100
    avail_ok = avail >= 20
    passed = exp_ok and rate_ok and avail_ok and location_ok
    reason = (
        f"Experience: {'OK' if exp_ok else 'Insufficient'} ({years_exp} yrs; tier1={'yes' if tier1 else 'no'}); "
        f"Comp: {'OK' if rate_ok else 'Too high'} (rate={rate}/hr; avail={avail} hrs/wk); "
        f"Location: {'OK' if location_ok else 'Not target'} ({personal_f.get('Location','')})"
    )
    return passed, reason

def _parse_llm_output(text: str) -> Tuple[str, int, str, List[str]]:
    summary, score, issues, followups = "", 0, "", []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower()
        if low.startswith("summary:"):
            summary = line.split(":", 1)[1].strip()
        elif low.startswith("score:"):
            val = line.split(":", 1)[1].strip()
            try:
                score = int("".join(ch for ch in val if ch.isdigit()))
            except:
                score = 0
        elif low.startswith("issues:"):
            issues = line.split(":", 1)[1].strip()
        elif low.startswith("follow-ups") or low.startswith("follow ups"):
            i += 1
            while i < len(lines) and (lines[i].startswith("-") or lines[i].startswith("•")):
                fu = lines[i][1:].strip()
                if fu:
                    followups.append(fu)
                i += 1
            continue
        i += 1
    return summary, score, issues, followups

def call_llm(spec_json: Dict[str, Any]) -> Optional[Tuple[str, int, str, List[str]]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    prompt = (
        "You are a recruiting analyst. Given this applicant profile JSON, do four things:"
        "\n1) 75-word summary."
        "\n2) Score 1-10."
        "\n3) Issues/gaps."
        "\n4) Up to three follow-ups."
        "\nReturn exactly:\n"
        "Summary: <text>\n"
        "Score: <integer>\n"
        "Issues: <text or 'None'>\n"
        "Follow-Ups:\n- <q1>\n- <q2>\n- <q3>\n\n"
        f"JSON:\n{json.dumps(spec_json, ensure_ascii=False)}"
    )
    last_err = None
    try:
        import google.generativeai as genai_legacy
        genai_legacy.configure(api_key=api_key)
        legacy_model_candidates = [
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "gemini-1.5-flash",
            "gemini-1.0-pro",
        ]
        for model_name in legacy_model_candidates:
            try:
                model = genai_legacy.GenerativeModel(model_name)
                resp = model.generate_content(prompt)
                text = getattr(resp, "text", "") or ""
                if not text and getattr(resp, "candidates", None):
                    text = "".join(getattr(c, "text", "") for c in resp.candidates)
                text = (text or "").strip()
                if text:
                    return _parse_llm_output(text)
            except Exception as e:
                last_err = e
                continue
    except Exception as e:
        last_err = e
    try:
        client = genai.Client(api_key=api_key)
        model_id = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        for attempt in range(3):
            try:
                try:
                    resp = client.models.generate_content(model=model_id, contents=prompt)
                except TypeError:
                    resp = client.models.generate_content(
                        model=model_id,
                        contents={"role": "user", "parts": [{"text": prompt}]},
                    )
                text = ""
                if hasattr(resp, "text") and resp.text:
                    text = resp.text
                elif getattr(resp, "candidates", None):
                    parts = getattr(resp.candidates[0].content, "parts", None) or []
                    text = "".join(getattr(p, "text", "") for p in parts)
                text = (text or "").strip()
                if not text:
                    raise RuntimeError("Empty response text")
                return _parse_llm_output(text)
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
    except Exception as e:
        last_err = e
    print("LLM (Gemini) failed:", last_err)
    return None

def main(applicant_id: str):
    applicants = fetch_records(TBL_APPLICANTS, f"{{Applicant ID}}='{applicant_id}'")
    if not applicants:
        raise SystemExit(f"Applicant ID '{applicant_id}' not found in {TBL_APPLICANTS}.")
    applicant = applicants[0]
    rec_id = applicant["id"]
    personal_rows = fetch_records(TBL_PERSONAL, f"FIND('{applicant_id}', ARRAYJOIN({{{APPLICANT_LINK_FIELD}}}))")
    work_rows     = fetch_records(TBL_WORK,     f"FIND('{applicant_id}', ARRAYJOIN({{{APPLICANT_LINK_FIELD}}}))")
    salary_rows   = fetch_records(TBL_SALARY,   f"FIND('{applicant_id}', ARRAYJOIN({{{APPLICANT_LINK_FIELD}}}))")
    spec_json = build_spec_json(personal_rows, work_rows, salary_rows)
    new_json = json.dumps(spec_json, ensure_ascii=False, indent=2)
    existing_json = (applicant.get("fields", {}) or {}).get("Compressed JSON")
    changed = new_json != existing_json
    if changed:
        update_record(TBL_APPLICANTS, rec_id, {"Compressed JSON": new_json})
    personal_row = personal_rows[0] if personal_rows else {}
    salary_row   = salary_rows[0] if salary_rows else {}
    passed, reason = shortlist_rules(personal_row, work_rows, salary_row)
    update_record(TBL_APPLICANTS, rec_id, {
        "Shortlist Status": "Shortlisted" if passed else "Rejected"
    })
    if passed:
        existing_shortlist = fetch_records(TBL_SHORTLIST, f"FIND('{applicant_id}', ARRAYJOIN({{{APPLICANT_LINK_FIELD}}}))")
        if not existing_shortlist:
            create_record(TBL_SHORTLIST, {
                APPLICANT_LINK_FIELD: [rec_id],
                "Compressed JSON": new_json,
                "Score Reason": reason,
            })
    if (MOCK_LLM or GEMINI_API_KEY) and (RUN_LLM_ALWAYS or changed):
        llm = call_llm(spec_json)
        if llm:
            summary, score, issues, followups = llm
            fields = {}
            if LLM_SUMMARY_FIELD:
                fields[LLM_SUMMARY_FIELD] = summary
            if LLM_SCORE_FIELD:
                fields[LLM_SCORE_FIELD] = score
            if LLM_ISSUES_FIELD:
                fields[LLM_ISSUES_FIELD] = issues
            if LLM_FOLLOWUPS_FIELD and followups:
                fields[LLM_FOLLOWUPS_FIELD] = "\n".join(f"- {q}" for q in followups)
            if fields:
                update_record(TBL_APPLICANTS, rec_id, fields)
    print("Done.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--applicant-id", required=True)
    args = p.parse_args()
    main(args.applicant_id)
