import os
import json
import requests
import argparse
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TOKEN = os.getenv("AIRTABLE_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

TBL_APPLICANTS = os.getenv("TBL_APPLICANTS", "Applicants")
TBL_PERSONAL   = os.getenv("TBL_PERSONAL_DETAILS", "Personal Details")
TBL_WORK       = os.getenv("TBL_WORK_EXPERIENCE", "Work Experience")
TBL_SALARY     = os.getenv("TBL_SALARY_PREFERENCES", "Salary Preferences")

APPLICANT_LINK_FIELD = os.getenv("APPLICANT_LINK_FIELD", "Applicant")

def fetch_records(table: str, formula: Optional[str] = None):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
    params = {}
    if formula:
        params["filterByFormula"] = formula
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("records", [])

def update_record(table: str, record_id: str, fields: dict) -> None:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}/{record_id}"
    r = requests.patch(url, headers=HEADERS, json={"fields": fields}, timeout=30)
    r.raise_for_status()

def create_record(table: str, fields: dict) -> None:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
    r = requests.post(url, headers=HEADERS, json={"fields": fields}, timeout=30)
    r.raise_for_status()

def update_or_create(table: str, applicant_id_str: str, fields: dict, unique: bool = True) -> None:
    if unique:
        formula = f"FIND('{applicant_id_str}', ARRAYJOIN({{{APPLICANT_LINK_FIELD}}}))"
        existing = fetch_records(table, formula)
        if existing:
            update_record(table, existing[0]["id"], fields)
            return
    create_record(table, fields)

def main(applicant_id: str) -> None:
    apps = fetch_records(TBL_APPLICANTS, f"{{Applicant ID}}='{applicant_id}'")
    if not apps:
        raise SystemExit(f"Applicant not found: {applicant_id}")
    app = apps[0]
    app_rec_id = app["id"]
    data = (app.get("fields") or {}).get("Compressed JSON")
    if not data:
        raise SystemExit("Compressed JSON is empty for this applicant.")
    try:
        doc = json.loads(data)
    except Exception as e:
        raise SystemExit(f"Compressed JSON is not valid JSON: {e}")
    personal = (doc.get("personal") or {})
    if personal:
        fields = {
            APPLICANT_LINK_FIELD: [app_rec_id],
            "Full Name": personal.get("name"),
            "Location": personal.get("location"),
        }
        update_or_create(TBL_PERSONAL, applicant_id, fields, unique=True)
    salary = (doc.get("salary") or {})
    if salary:
        fields = {
            APPLICANT_LINK_FIELD: [app_rec_id],
            "Preferred Rate": salary.get("rate"),
            "Currency": salary.get("currency"),
            "Availability (hrs/wk)": salary.get("availability"),
        }
        update_or_create(TBL_SALARY, applicant_id, fields, unique=True)
    existing_exp = fetch_records(TBL_WORK, f"FIND('{applicant_id}', ARRAYJOIN({{{APPLICANT_LINK_FIELD}}}))")
    index = defaultdict(list)
    for r in existing_exp:
        f = r.get("fields", {}) or {}
        key = (str(f.get("Company", "")).strip().lower(), str(f.get("Title", "")).strip().lower())
        index[key].append(r)
    for item in (doc.get("experience") or []):
        company = (item.get("company") or "").strip()
        title   = (item.get("title") or "").strip()
        key = (company.lower(), title.lower())
        if index[key]:
            rec = index[key].pop(0)
            patch = {APPLICANT_LINK_FIELD: [app_rec_id]}
            if company:
                patch["Company"] = company
            if title:
                patch["Title"] = title
            update_record(TBL_WORK, rec["id"], patch)
        else:
            create_record(TBL_WORK, {
                APPLICANT_LINK_FIELD: [app_rec_id],
                "Company": company or None,
                "Title": title or None,
            })
    print("Decompression complete (dates preserved).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--applicant-id", required=True, help="Value from Applicants.'Applicant ID' (e.g., TEST-001)")
    args = parser.parse_args()
    main(args.applicant_id)
