"""Provision a Google Meet link for an interview. STRETCH ONLY.

The browser client in this service is the media path. A Meet link is *not* how
the agent hears the candidate: Google gives no supported, free way for a bot to
pull raw Meet audio (see services/gateway/README.md and plan.md §8). This script
exists only for the stretch case where a real Meet link is wanted as the
human-facing / official link, provisioned via Google Calendar.

Setup:
    pip install -e ".[meet]"     # from services/gateway
    # OAuth 2.0 "Desktop app" client in Google Cloud Console, Calendar API
    # enabled, JSON saved as credentials.json next to this file. First run opens
    # a browser to authorize; the token is cached in token.json.

Usage:
    python meet_provision.py --summary "Screening: Jane Doe" \
        --start 2026-09-12T15:00:00 --minutes 30 [--invite jane@example.com]
"""

import argparse
import datetime
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_path = os.path.join(HERE, "token.json")
    creds_path = os.path.join(HERE, "credentials.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES).run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def provision_meet(summary, start_iso, minutes=30, invite=None, tz="America/New_York"):
    svc = _service()
    start = datetime.datetime.fromisoformat(start_iso)
    end = start + datetime.timedelta(minutes=minutes)
    body = {
        "summary": summary,
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "conferenceData": {
            "createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    if invite:
        body["attendees"] = [{"email": invite}]
    event = svc.events().insert(
        calendarId="primary",
        body=body,
        conferenceDataVersion=1,
        sendUpdates="all" if invite else "none",
    ).execute()
    return {
        "meet_link": event.get("hangoutLink"),
        "event_link": event.get("htmlLink"),
        "event_id": event.get("id"),
    }


def main():
    ap = argparse.ArgumentParser(description="Create a Google Meet link (stretch)")
    ap.add_argument("--summary", default="zeg screening interview")
    ap.add_argument("--start", required=True, help="ISO local time, e.g. 2026-09-12T15:00:00")
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--invite", default=None, help="candidate email (sends a calendar invite)")
    ap.add_argument("--tz", default="America/New_York")
    args = ap.parse_args()
    r = provision_meet(args.summary, args.start, args.minutes, args.invite, args.tz)
    print("Meet link : %s" % r["meet_link"])
    print("Event     : %s" % r["event_link"])
    print("Event id  : %s" % r["event_id"])


if __name__ == "__main__":
    main()
