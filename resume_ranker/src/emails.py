"""Email sending via Resend, with an .ics calendar attachment.

Both the recruiter copy and candidate copy are sent to DEMO_EMAIL in this
demo (Resend's no-domain free tier only delivers to your signup address).
"""

import os
import base64
import uuid
import asyncio
from datetime import timedelta

import resend
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.environ.get("RESEND_API_KEY")

FROM_ADDRESS = "onboarding@resend.dev"
INTERVIEW_MINUTES = 45


def _format_human(dt):
    return dt.strftime("%A, %B %d, %Y at %I:%M %p")


def _format_ics_utc(dt):
    # iCalendar wants UTC times like 20260622T150000Z
    return dt.strftime("%Y%m%dT%H%M%SZ")


def build_ics(summary, description, start_dt, organizer_email, attendee_email):
    """Hand-build a minimal valid .ics string for one event."""
    end_dt = start_dt + timedelta(minutes=INTERVIEW_MINUTES)
    uid = f"{uuid.uuid4()}@resume-ranker"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Resume Ranker//Interview//EN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_format_ics_utc(start_dt)}",
        f"DTSTART:{_format_ics_utc(start_dt)}",
        f"DTEND:{_format_ics_utc(end_dt)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"ORGANIZER:mailto:{organizer_email}",
        f"ATTENDEE;RSVP=TRUE:mailto:{attendee_email}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


def _ics_attachment(ics_text):
    """Resend attachment: base64 content + filename."""
    return {
        "filename": "interview.ics",
        "content": base64.b64encode(ics_text.encode("utf-8")).decode("utf-8"),
    }


def build_recruiter_email(job_title, candidate_name, candidate_email, scheduled_for):
    subject = f"Interview scheduled with {candidate_name}"
    body = (
        "<p>Hi,</p>"
        f"<p>You have an interview scheduled with <b>{candidate_name}</b> "
        f"({candidate_email}) for the <b>{job_title}</b> role.</p>"
        f"<p><b>Time:</b> {_format_human(scheduled_for)}</p>"
        "<p>The calendar invite is attached.</p>"
    )
    return subject, body


def build_candidate_email(job_title, candidate_name, recruiter_email, scheduled_for):
    subject = f"Interview invitation: {job_title}"
    body = (
        f"<p>Hi {candidate_name},</p>"
        f"<p>You have been invited to an interview for the <b>{job_title}</b> role.</p>"
        f"<p><b>Time:</b> {_format_human(scheduled_for)}<br>"
        f"<b>Interviewer:</b> {recruiter_email}</p>"
        "<p>The calendar invite is attached. Looking forward to speaking with you.</p>"
    )
    return subject, body


def _send(to_address, subject, html, ics_text):
    """Synchronous Resend send. Called via asyncio.to_thread."""
    return resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_address],
        "subject": subject,
        "html": html,
        "attachments": [_ics_attachment(ics_text)],
    })


async def send_interview_emails(
    job_title, candidate_name, recruiter_email, candidate_email,
    demo_email, scheduled_for,
):
    """Build the .ics and send both emails (to demo_email in this demo)."""
    summary = f"Interview: {candidate_name} - {job_title}"
    description = (
        f"Interview for the {job_title} role. "
        f"Candidate: {candidate_name}. Interviewer: {recruiter_email}."
    )
    ics_text = build_ics(
        summary, description, scheduled_for, recruiter_email, candidate_email,
    )

    r_subject, r_html = build_recruiter_email(
        job_title, candidate_name, candidate_email, scheduled_for,
    )
    c_subject, c_html = build_candidate_email(
        job_title, candidate_name, recruiter_email, scheduled_for,
    )

    # Both go to demo_email (free-tier, no-domain restriction).
    await asyncio.gather(
        asyncio.to_thread(_send, demo_email, r_subject, r_html, ics_text),
        asyncio.to_thread(_send, demo_email, c_subject, c_html, ics_text),
    )