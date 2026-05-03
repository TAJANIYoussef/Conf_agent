import logging
import os
import pickle
from datetime import datetime, timedelta
from typing import Optional
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from agent.config import CALENDAR_ID, GCAL_CREDS_FILE, GCAL_TOKEN_FILE, GCAL_SCOPES
from agent.models import Conference

logger = logging.getLogger(__name__)

def get_calendar_service():
    """
    Build the Calendar v3 service using OAuth2 desktop flow.

    On first run, opens a browser to authenticate. The token is saved to
    GCAL_TOKEN_FILE and reused on subsequent runs.

    Requires gcal_credentials.json downloaded from:
      Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client (Desktop)
    """
    creds = None
    if os.path.exists(GCAL_TOKEN_FILE):
        with open(GCAL_TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GCAL_CREDS_FILE):
                raise FileNotFoundError(
                    f"{GCAL_CREDS_FILE} not found. Download it from Google Cloud Console:\n"
                    "  APIs & Services → Credentials → OAuth 2.0 Client ID (Desktop app) → Download JSON\n"
                    f"  then place it at: {os.path.abspath(GCAL_CREDS_FILE)}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(GCAL_CREDS_FILE, GCAL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GCAL_TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def write_conference_to_calendar(conf: Conference, service) -> str:
    """
    Creates calendar events for:
    - Abstract deadline
    - Full paper deadline
    - Camera ready deadline
    - Conference date
    Returns event ID of the full paper deadline event.
    colorId 11 = tomato red in Google Calendar.
    """
    def _make_event(summary: str, deadline, description: str) -> dict:
        d = deadline.isoformat()
        end = (datetime.fromisoformat(d) + timedelta(days=1)).date().isoformat()
        return {
            "summary": summary,
            "description": description,
            "start": {"date": d},
            "end":   {"date": end},
            "colorId": "11",
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 20160},
                    {"method": "popup", "minutes": 4320},
                ],
            },
        }

    desc = (
        f"Conference: {conf.name}\n"
        f"URL: {conf.url}\n"
        f"Venue: {conf.venue or 'TBA'}\n"
        f"Relevance: {conf.relevance_score}/10\n"
        f"Why: {conf.relevance_reason}\n"
        f"Source: conference_agent (automated weekly)"
    )

    event_id = ""
    successes = 0
    failures: list[str] = []

    def _try_insert(label: str, summary: str, when) -> Optional[str]:
        try:
            res = service.events().insert(
                calendarId=CALENDAR_ID,
                body=_make_event(summary, when, desc),
            ).execute()
            return res.get("id", "")
        except Exception as e:
            failures.append(f"{label}: {e}")
            return None

    if conf.abstract_deadline:
        rid = _try_insert("abstract",
                          f"[ABSTRACT DEADLINE] {conf.acronym} {conf.year}",
                          conf.abstract_deadline)
        if rid is not None:
            successes += 1
    if conf.full_paper_deadline:
        rid = _try_insert("paper",
                          f"[PAPER DEADLINE] {conf.acronym} {conf.year}",
                          conf.full_paper_deadline)
        if rid is not None:
            successes += 1
            event_id = rid or event_id
    if conf.camera_ready_deadline:
        rid = _try_insert("camera_ready",
                          f"[CAMERA READY] {conf.acronym} {conf.year}",
                          conf.camera_ready_deadline)
        if rid is not None:
            successes += 1
    if conf.conference_date:
        rid = _try_insert("conference",
                          f"[CONFERENCE] {conf.acronym} {conf.year}",
                          conf.conference_date)
        if rid is not None:
            successes += 1

    # If every single insert failed, raise so the agent loop reports the
    # conference as NOT added — instead of silently logging "Added: …".
    if successes == 0 and failures:
        raise RuntimeError(
            f"all calendar inserts failed for {conf.acronym}: {failures[0]}"
        )
    return event_id
