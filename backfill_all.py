import os
import requests
import subprocess
from dotenv import load_dotenv

load_dotenv()

BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TOKEN = os.getenv("AIRTABLE_TOKEN")
TBL_APPLICANTS = os.getenv("TBL_APPLICANTS", "Applicants")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def fetch_all_applicants():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_APPLICANTS}"
    applicants = []
    params = {}
    while True:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for record in data.get("records", []):
            applicant_id = record["fields"].get("Applicant ID")
            if applicant_id:
                applicants.append(applicant_id)
        if "offset" in data:
            params["offset"] = data["offset"]
        else:
            break
    return applicants

def main():
    applicants = fetch_all_applicants()
    print(f"Found {len(applicants)} applicants.")
    for applicant_id in applicants:
        print(f"\n=== Processing {applicant_id} ===")
        subprocess.run(
            ["python", "compress_and_evaluate.py", "--applicant-id", applicant_id],
            check=True
        )
        subprocess.run(
            ["python", "decompress_from_json.py", "--applicant-id", applicant_id],
            check=True
        )

if __name__ == "__main__":
    main()
