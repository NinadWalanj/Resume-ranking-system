"""Create the schema and insert sample data.

Run once before using the app. Drops and recreates the tables so it's safe
to re-run (existing data is wiped).
"""

import os
import asyncio
import json

from dotenv import load_dotenv
from src.db import get_pool, close_pool

load_dotenv()

# In this demo every email is delivered to your Resend signup inbox.
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "you@example.com")


SCHEMA_SQL = """
DROP TABLE IF EXISTS interviews;
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS jobs;

CREATE TABLE jobs (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    description     JSONB NOT NULL,
    recruiter_email TEXT NOT NULL
);

CREATE TABLE applications (
    id                SERIAL PRIMARY KEY,
    jd_id             INT NOT NULL REFERENCES jobs(id),
    candidate_name    TEXT,
    candidate_email   TEXT,
    resume_data       JSONB NOT NULL,
    total_score       FLOAT,
    criterion_scores  JSONB,
    scoring_status    TEXT NOT NULL DEFAULT 'pending',
    scored_at         TIMESTAMPTZ
);

CREATE TABLE interviews (
    id              SERIAL PRIMARY KEY,
    application_id  INT NOT NULL REFERENCES applications(id),
    recruiter_email TEXT NOT NULL,
    candidate_email TEXT NOT NULL,
    scheduled_for   TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL DEFAULT 'scheduled',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

SAMPLE_JD = {
    "title": "Senior Backend Engineer",
    "required_skills": ["Python", "PostgreSQL", "REST APIs", "AWS"],
    "nice_to_haves": ["Kubernetes", "Redis", "GraphQL"],
    "experience_level": "5+ years",
    "domain": "fintech",
    "responsibilities": [
        "Design and build backend services",
        "Own database schema and query performance",
        "Mentor mid-level engineers",
    ],
}

SAMPLE_APPLICATIONS = [
    {
        "name": "Alice Chen",
        "resume": {
            "skills": ["Python", "PostgreSQL", "REST APIs", "AWS", "Kubernetes", "Redis"],
            "experience": [
                {"title": "Senior Backend Engineer", "company": "PayLane",
                 "domain": "fintech", "years": 4},
                {"title": "Backend Engineer", "company": "Stripe-adjacent startup",
                 "domain": "fintech", "years": 3},
            ],
            "total_years": 7,
            "education": [{"degree": "BS Computer Science", "school": "Carnegie Mellon"}],
        },
    },
    {
        "name": "Bob Martinez",
        "resume": {
            "skills": ["Python", "PostgreSQL", "REST APIs", "Docker"],
            "experience": [
                {"title": "Backend Engineer", "company": "RetailCo",
                 "domain": "e-commerce", "years": 5},
            ],
            "total_years": 5,
            "education": [{"degree": "BS Computer Science", "school": "State University"}],
        },
    },
    {
        "name": "Carol Singh",
        "resume": {
            "skills": ["Python", "Django", "MySQL", "REST APIs"],
            "experience": [
                {"title": "Full Stack Developer", "company": "AgencyCorp",
                 "domain": "marketing", "years": 3},
            ],
            "total_years": 3,
            "education": [{"degree": "BS Information Systems", "school": "City College"}],
        },
    },
    {
        "name": "David Kim",
        "resume": {
            "skills": ["Python", "PostgreSQL", "REST APIs", "AWS", "GraphQL", "Redis", "Kubernetes"],
            "experience": [
                {"title": "Staff Engineer", "company": "BankTech",
                 "domain": "fintech", "years": 6},
                {"title": "Senior Backend Engineer", "company": "Square",
                 "domain": "fintech", "years": 4},
            ],
            "total_years": 10,
            "education": [{"degree": "MS Computer Science", "school": "Stanford"}],
        },
    },
    {
        "name": "Eve Patel",
        "resume": {
            "skills": ["JavaScript", "Node.js", "MongoDB", "React"],
            "experience": [
                {"title": "Frontend Engineer", "company": "AdTechCo",
                 "domain": "advertising", "years": 4},
            ],
            "total_years": 4,
            "education": [{"degree": "BS Computer Science", "school": "University of Texas"}],
        },
    },
    {
        "name": "Frank Wu",
        "resume": {
            "skills": ["Python", "PostgreSQL", "AWS", "REST APIs"],
            "experience": [
                {"title": "Backend Engineer", "company": "LendingPro",
                 "domain": "fintech", "years": 5},
            ],
            "total_years": 5,
            "education": [{"degree": "BS Software Engineering", "school": "UC Davis"}],
        },
    },
]


async def main() -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

            # Recruiter email = DEMO_EMAIL so real delivery works.
            job_id = await conn.fetchval(
                "INSERT INTO jobs (title, description, recruiter_email) "
                "VALUES ($1, $2, $3) RETURNING id",
                SAMPLE_JD["title"],
                json.dumps(SAMPLE_JD),
                DEMO_EMAIL,
            )
            print(f"Inserted job {job_id}: {SAMPLE_JD['title']}")
            print(f"All demo emails will be delivered to: {DEMO_EMAIL}")

            for app in SAMPLE_APPLICATIONS:
                # Candidate email = DEMO_EMAIL too, so any candidate works.
                await conn.execute(
                    "INSERT INTO applications "
                    "(jd_id, candidate_name, candidate_email, resume_data) "
                    "VALUES ($1, $2, $3, $4)",
                    job_id,
                    app["name"],
                    DEMO_EMAIL,
                    json.dumps(app["resume"]),
                )
            print(f"Inserted {len(SAMPLE_APPLICATIONS)} applications")
            print("\nNext step: uvicorn src.main:app --reload")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())