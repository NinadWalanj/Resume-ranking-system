"""Score all applications for a job concurrently, then print them ranked.

Usage: python -m src.rank 1
"""

import asyncio
import json
import sys

from src.db import get_pool
from src.scoring import score_candidate


# This function handles ONE application: score it, save the score.
async def score_one(pool, app, jd):
    resume = app["resume_data"]
    if isinstance(resume, str):
        resume = json.loads(resume)

    total, breakdown = await score_candidate(jd, resume)

    await pool.execute(
        "UPDATE applications SET total_score=$1, criterion_scores=$2 WHERE id=$3",
        total,
        json.dumps(breakdown),
        app["id"],
    )
    print(f"Scored {app['candidate_name']}: {total}")


async def rank_job(jd_id):
    pool = await get_pool()

    # 1. Get the job description.
    job = await pool.fetchrow("SELECT description FROM jobs WHERE id=$1", jd_id)
    if job is None:
        print(f"No job found with id {jd_id}")
        return
    jd = job["description"]
    if isinstance(jd, str):
        jd = json.loads(jd)

    # 2. Get all applications for this job.
    apps = await pool.fetch(
        "SELECT id, candidate_name, resume_data FROM applications WHERE jd_id=$1",
        jd_id,
    )

    if not apps:
        print(f"No applications found for job {jd_id}")
        return

    # 3. Run score_one for EVERY application at the same time.
    await asyncio.gather(*[score_one(pool, app, jd) for app in apps])

    # 4. Get them back sorted by score, and print.
    ranked = await pool.fetch(
        "SELECT candidate_name, total_score FROM applications "
        "WHERE jd_id=$1 ORDER BY total_score DESC",
        jd_id,
    )

    print("\n--- Ranking ---")
    for i, row in enumerate(ranked, 1):
        print(f"{i}. {row['candidate_name']} - {row['total_score']}")


if __name__ == "__main__":
    jd_id = int(sys.argv[1])
    asyncio.run(rank_job(jd_id))
