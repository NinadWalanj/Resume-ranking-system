"""FastAPI app.

Endpoints:
    GET  /                                   -> frontend
    POST /jobs/{jd_id}/rank                  -> score and return ranked list
    POST /applications/{app_id}/schedule     -> schedule interview, send emails

Run:
    uvicorn src.main:app --reload
"""

import os
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from src.db import get_pool, close_pool
from src.scoring import score_candidate
from src.emails import send_interview_emails

load_dotenv()

DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "you@example.com")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse("static/index.html")


# ---------- Ranking ----------

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
        total, json.dumps(breakdown), application["id"],
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
        "SELECT a.id AS application_id, a.candidate_name, a.candidate_email, "
        "       a.total_score, a.criterion_scores, "
        "       i.id AS interview_id, i.scheduled_for "
        "FROM applications a "
        "LEFT JOIN interviews i "
        "    ON i.application_id = a.id AND i.status = 'scheduled' "
        "WHERE a.jd_id = $1 AND a.total_score IS NOT NULL "
        "ORDER BY a.total_score DESC",
        jd_id,
    )

    ranked = []
    for row in rows:
        breakdown = row["criterion_scores"]
        if isinstance(breakdown, str):
            breakdown = json.loads(breakdown)
        entry = {
            "application_id": row["application_id"],
            "name": row["candidate_name"],
            "email": row["candidate_email"],
            "total_score": row["total_score"],
            "criterion_scores": {k: v for k, v in breakdown.items() if k != "reasoning"},
            "reasoning": breakdown.get("reasoning"),
            "interview": None,
        }
        if row["interview_id"]:
            entry["interview"] = {
                "interview_id": row["interview_id"],
                "scheduled_for": row["scheduled_for"].isoformat(),
            }
        ranked.append(entry)

    return {"job_id": jd_id, "ranked": ranked}


# ---------- Interview scheduling ----------

class ScheduleRequest(BaseModel):
    scheduled_for: datetime


@app.post("/applications/{application_id}/schedule")
async def schedule_interview(application_id: int, req: ScheduleRequest):
    pool = await get_pool()

    scheduled_for = req.scheduled_for
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)

    info = await pool.fetchrow(
        "SELECT a.candidate_name, a.candidate_email, "
        "       j.title AS job_title, j.recruiter_email "
        "FROM applications a JOIN jobs j ON j.id = a.jd_id "
        "WHERE a.id = $1",
        application_id,
    )
    if info is None:
        raise HTTPException(status_code=404, detail=f"No application with id {application_id}")

    # Guard: don't double-book the same candidate.
    existing = await pool.fetchrow(
        "SELECT scheduled_for FROM interviews "
        "WHERE application_id = $1 AND status = 'scheduled'",
        application_id,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This candidate already has an interview scheduled "
                   f"for {existing['scheduled_for'].isoformat()}",
        )

    interview_id = await pool.fetchval(
        "INSERT INTO interviews "
        "(application_id, recruiter_email, candidate_email, scheduled_for) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        application_id, info["recruiter_email"], info["candidate_email"], scheduled_for,
    )

    # Send the two emails with the .ics attachment.
    try:
        await send_interview_emails(
            job_title=info["job_title"],
            candidate_name=info["candidate_name"],
            recruiter_email=info["recruiter_email"],
            candidate_email=info["candidate_email"],
            demo_email=DEMO_EMAIL,
            scheduled_for=scheduled_for,
        )
    except Exception as exc:
        # Roll back the interview row if sending failed, so the user can retry.
        await pool.execute("DELETE FROM interviews WHERE id=$1", interview_id)
        raise HTTPException(status_code=502, detail=f"Failed to send emails: {exc}")

    return {
        "interview_id": interview_id,
        "scheduled_for": scheduled_for.isoformat(),
        "recruiter_email": info["recruiter_email"],
        "candidate_email": info["candidate_email"],
    }