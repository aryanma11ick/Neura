import google.oauth2.credentials
import googleapiclient.discovery
from sqlalchemy import select
from db.models import GoogleToken
from db.init_db import async_session
from datetime import datetime, timedelta
import pytz
from dateutil import parser as dateutil_parser

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
]

async def _get_creds(whatsapp_id):
    async with async_session() as session:
        result = await session.execute(select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id))
        token = result.scalars().first()
        if not token:
            raise Exception("No linked Google account.")
        return google.oauth2.credentials.Credentials.from_authorized_user_info({
            "token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": token.scopes
        }, SCOPES)

async def add_calendar_event(whatsapp_id, summary, start_time, end_time, description=""):
    creds = await _get_creds(whatsapp_id)
    service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
    }
    service.events().insert(calendarId="primary", body=event).execute()
    return f"✅ Event '{summary}' created for {start_time}."

async def update_calendar_event(whatsapp_id, match_summary, new_start_time=None, new_end_time=None, description=None):
    creds = await _get_creds(whatsapp_id)
    service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)
    now = datetime.utcnow().isoformat() + "Z"
    events = service.events().list(calendarId="primary", timeMin=now, singleEvents=True, orderBy="startTime").execute().get("items", [])
    for e in events:
        if e.get("summary", "").lower() == match_summary.lower():
            if new_start_time:
                e["start"]["dateTime"] = new_start_time
            if new_end_time:
                e["end"]["dateTime"] = new_end_time
            if description:
                e["description"] = description
            service.events().update(calendarId="primary", eventId=e["id"], body=e).execute()
            return f"✅ Updated '{match_summary}'."
    return f"❌ Event '{match_summary}' not found."

async def fetch_upcoming_events(whatsapp_id, date):
    creds = await _get_creds(whatsapp_id)
    service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)
    tz = pytz.timezone("Asia/Kolkata")
    start = tz.localize(dateutil_parser.isoparse(date).replace(hour=0, minute=0, second=0))
    end = start + timedelta(days=1)
    events = service.events().list(calendarId="primary", timeMin=start.isoformat(), timeMax=end.isoformat(),
                                   singleEvents=True, orderBy="startTime").execute().get("items", [])
    if not events:
        return f"📭 No events found for {start.strftime('%d %b %Y')}."
    lines = [f"🗓️ {e.get('summary', '(No title)')} – {dateutil_parser.isoparse(e['start'].get('dateTime', e['start'].get('date'))).astimezone(tz).strftime('%I:%M %p')}" for e in events]
    return "Here’s your schedule:\n\n" + "\n".join(lines)
