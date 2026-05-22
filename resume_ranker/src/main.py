"""FastAPI app.

Endpoints:
    GET  /                    -> serves the frontend (static/index.html)
    POST /jobs/{jd_id}/rank   -> scores all applications, returns ranked list

Run:
    uvicorn src.main:app --reload
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from src.db import get_pool, close_pool
from src.scoring import score_candidate


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse("static/index.html")


async def score_one(pool, application, jd):
    resume = application["resume_data"]
    if isinstance(resume, str):
        resume = json.loads(resume)

    try:
        total, breakdown = await score_candidate(jd, resume)
    except Exception as exc:
        print(f"Failed to score {application['candidate_name']}: {exc}")
        return

    await pool.execute(
        "UPDATE applications SET total_score=$1, criterion_scores=$2 WHERE id=$3",
        total,
        json.dumps(breakdown),
        application["id"],
    )


@app.post("/jobs/{jd_id}/rank")
async def rank_job(jd_id: int):
    pool = await get_pool()

    job = await pool.fetchrow("SELECT description FROM jobs WHERE id=$1", jd_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job with id {jd_id}")

    jd = job["description"]
    if isinstance(jd, str):
        jd = json.loads(jd)

    applications = await pool.fetch(
        "SELECT id, candidate_name, resume_data FROM applications WHERE jd_id=$1",
        jd_id,
    )
    if not applications:
        return {"job_id": jd_id, "ranked": []}

    await asyncio.gather(*[score_one(pool, a, jd) for a in applications])

    rows = await pool.fetch(
        "SELECT candidate_name, candidate_email, total_score, criterion_scores "
        "FROM applications WHERE jd_id=$1 AND total_score IS NOT NULL "
        "ORDER BY total_score DESC",
        jd_id,
    )

    ranked = []
    for row in rows:
        breakdown = row["criterion_scores"]
        if isinstance(breakdown, str):
            breakdown = json.loads(breakdown)
        ranked.append(
            {
                "name": row["candidate_name"],
                "email": row["candidate_email"],
                "total_score": row["total_score"],
                "criterion_scores": {
                    k: v for k, v in breakdown.items() if k != "reasoning"
                },
                "reasoning": breakdown.get("reasoning"),
            }
        )

    return {"job_id": jd_id, "ranked": ranked}
