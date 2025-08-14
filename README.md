# airtable-llm-recruitment
End-to-end Airtable automation pipeline for candidate intake, evaluation, and shortlisting with LLM (Gemini) integration. Includes form handling, prefilled link emailing, and Python scripts for data compression, evaluation, and backfilling.

## Setup

### Requirements

- Python 3.10+

### Installation

```bash
pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```env
# Required
AIRTABLE_BASE_ID=xxx
AIRTABLE_TOKEN=xxx
GEMINI_API_KEY=xxx

# Optional overrides
TBL_APPLICANTS=Applicants
TBL_PERSONAL_DETAILS=Personal Details
TBL_WORK_EXPERIENCE=Work Experience
TBL_SALARY_PREFERENCES=Salary Preferences
TBL_SHORTLISTED_LEADS=Shortlisted Leads
APPLICANT_LINK_FIELD=Applicant
GEMINI_MODEL=gemini-2.5-flash
RUN_LLM_ALWAYS=0
MOCK_LLM=0
LLM_SUMMARY_FIELD=LLM Summary
LLM_SCORE_FIELD=LLM Score
LLM_ISSUES_FIELD=LLM Issues
LLM_FOLLOWUPS_FIELD=LLM Follow-Ups
```

Run the scripts with the environment configured:

```bash
python backfill_all.py
```
