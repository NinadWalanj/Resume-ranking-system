# Resume Ranker (Demo)

A backend service that ranks resumes against a job description using an LLM-driven
rubric. This demo version skips the parsing/extraction pipeline — sample data is
seeded directly into Postgres.

## Setup

1. Copy `.env.example` to `.env` and fill in your `GEMINI_API_KEY`.

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start Postgres:
   ```bash
   docker compose up -d
   ```

4. Seed the database (creates tables + sample JD + sample applications):
   ```bash
   python -m src.seed
   ```

5. Run the ranker:
   ```bash
   python -m src.rank 1
   ```
   (`1` is the job ID. Use whatever `seed` printed.)

## How it works

- `src/db.py` — async Postgres connection pool.
- `src/models.py` — Pydantic schema for the LLM response.
- `src/scoring.py` — pure async function: takes a JD + resume, returns a score.
- `src/seed.py` — creates schema and inserts sample data.
- `src/rank.py` — entry point: scores all pending applications concurrently
  with `asyncio.gather`, then prints the ranked list.

## What gets scored

The LLM returns per-criterion scores (1–5 each) for:
- `required_skills`
- `experience_level`
- `domain_fit`
- `education`

Plus a `reasoning` field for explainability. The weighted total is computed in
Python (weights in `scoring.py`), not by the LLM.
