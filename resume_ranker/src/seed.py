"""Create the schema and insert sample data.

Run once before `rank.py`. Drops and recreates the tables so it's safe to
re-run.
"""

import asyncio
import json

from src.db import get_pool, close_pool


SCHEMA_SQL = """
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS jobs;

CREATE TABLE jobs (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    description JSONB NOT NULL
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

CREATE INDEX idx_apps_ranking ON applications(jd_id, total_score DESC)
    WHERE scoring_status = 'scored';
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
        "email": "alice.chen@example.com",
        "resume": {
            "skills": ["Python", "PostgreSQL", "REST APIs", "AWS",
                       "Kubernetes", "Redis"],
            "experience": [
                {"title": "Senior Backend Engineer", "company": "PayLane",
                 "domain": "fintech", "years": 4},
                {"title": "Backend Engineer", "company": "Stripe-adjacent startup",
                 "domain": "fintech", "years": 3},
            ],
            "total_years": 7,
            "education": [{"degree": "BS Computer Science",
                           "school": "Carnegie Mellon"}],
        },
    },
    {
        "name": "Bob Martinez",
        "email": "bob.martinez@example.com",
        "resume": {
            "skills": ["Python", "PostgreSQL", "REST APIs", "Docker"],
            "experience": [
                {"title": "Backend Engineer", "company": "RetailCo",
                 "domain": "e-commerce", "years": 5},
            ],
            "total_years": 5,
            "education": [{"degree": "BS Computer Science",
                           "school": "State University"}],
        },
    },
    {
        "name": "Carol Singh",
        "email": "carol.singh@example.com",
        "resume": {
            "skills": ["Python", "Django", "MySQL", "REST APIs"],
            "experience": [
                {"title": "Full Stack Developer", "company": "AgencyCorp",
                 "domain": "marketing", "years": 3},
            ],
            "total_years": 3,
            "education": [{"degree": "BS Information Systems",
                           "school": "City College"}],
        },
    },
    {
        "name": "David Kim",
        "email": "david.kim@example.com",
        "resume": {
            "skills": ["Python", "PostgreSQL", "REST APIs", "AWS",
                       "GraphQL", "Redis", "Kubernetes"],
            "experience": [
                {"title": "Staff Engineer", "company": "BankTech",
                 "domain": "fintech", "years": 6},
                {"title": "Senior Backend Engineer", "company": "Square",
                 "domain": "fintech", "years": 4},
            ],
            "total_years": 10,
            "education": [{"degree": "MS Computer Science",
                           "school": "Stanford"}],
        },
    },
    {
        "name": "Eve Patel",
        "email": "eve.patel@example.com",
        "resume": {
            "skills": ["JavaScript", "Node.js", "MongoDB", "React"],
            "experience": [
                {"title": "Frontend Engineer", "company": "AdTechCo",
                 "domain": "advertising", "years": 4},
            ],
            "total_years": 4,
            "education": [{"degree": "BS Computer Science",
                           "school": "University of Texas"}],
        },
    },
    {
        "name": "Frank Wu",
        "email": "frank.wu@example.com",
        "resume": {
            "skills": ["Python", "PostgreSQL", "AWS", "REST APIs"],
            "experience": [
                {"title": "Backend Engineer", "company": "LendingPro",
                 "domain": "fintech", "years": 5},
            ],
            "total_years": 5,
            "education": [{"degree": "BS Software Engineering",
                           "school": "UC Davis"}],
        },
    },
]


async def main() -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

            job_id = await conn.fetchval(
                "INSERT INTO jobs (title, description) VALUES ($1, $2) RETURNING id",
                SAMPLE_JD["title"],
                json.dumps(SAMPLE_JD),
            )
            print(f"Inserted job {job_id}: {SAMPLE_JD['title']}")

            for app in SAMPLE_APPLICATIONS:
                await conn.execute(
                    """
                    INSERT INTO applications
                        (jd_id, candidate_name, candidate_email, resume_data)
                    VALUES ($1, $2, $3, $4)
                    """,
                    job_id,
                    app["name"],
                    app["email"],
                    json.dumps(app["resume"]),
                )
            print(f"Inserted {len(SAMPLE_APPLICATIONS)} applications")
            print(f"\nNext step: python -m src.rank {job_id}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
