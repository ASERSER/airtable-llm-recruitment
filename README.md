# airtable-llm-recruitment

End-to-end Airtable automation pipeline for candidate intake, evaluation, and shortlisting with LLM (Gemini) integration. Includes form handling, prefilled link emailing, and Python scripts for data compression, evaluation, and backfilling.

## Project Overview

This project automates the recruitment workflow from initial form submission through evaluation and data expansion using Airtable and Gemini-powered Python scripts.

### Data Flow

- Form submission → Airtable intake.
- `compress_and_evaluate.py` generates summaries and scores via the Gemini API.
- `decompress_from_json.py` expands compressed JSON back into Airtable tables.
- `backfill_all.py` iterates through all applicants.

```text
Form submission
    ↓
Airtable intake
    ↓
compress_and_evaluate.py (Gemini API)
    ↓
decompress_from_json.py
    ↓
backfill_all.py
```
