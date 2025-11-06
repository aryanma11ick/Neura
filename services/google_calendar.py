# services/google_calendar.py

import os
import pytz
import googleapiclient.discovery
import google.oauth2.credentials
from db.init_db import async_session
from db.models import GoogleToken
from sqlalchemy import select
from datetime import datetime, timedelta
from twilio.rest import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dateutil import parser as dateutil_parser

# ────────── Global Setup ──────────
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
]

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# Scheduler for reminders
scheduler = AsyncIOScheduler()
try:
    if not scheduler.running:
        scheduler.start()
except Exception:
    try:
        scheduler.start()
    except Exception as e:
        print(f"⚠️ Could not start scheduler: {e}")


# ────────── Helpers ──────────
def normalize_whatsapp_id(raw: str) -> str:
    if not raw:
        return ""
    v = raw.replace("whatsapp:", "").strip()
    if not v.startswith("+"):
        v = f"+{v}"
    return v


def twilio_whatsapp_format(raw: str) -> str:
    return f"whatsapp:{normalize_whatsapp_id(raw)}"


def parse_iso_datetime(dt_str: str) -> datetime:
    if not dt_str:
        raise ValueError("Empty datetime string")
    dt = dateutil_parser.isoparse(dt_str)
    if dt.tzinfo is None:
        tz = pytz.timezone("Asia/Kolkata")
        dt = tz.localize(dt)
    return dt


# ────────── Reminder ──────────
def schedule_meeting_reminder(whatsapp_id: str, title: str, start_time: str, meet_link: str = None, minutes_before: int = 10):
    """
    Schedule a WhatsApp reminder minutes_before minutes before the event start.
    """
    try:
        start_dt = parse_iso_datetime(start_time)
    except Exception as e:
        print(f"⚠️ Invalid start_time for reminder: {start_time} ({e})")
        return

    reminder_time = start_dt - timedelta(minutes=minutes_before)
    now = datetime.now(pytz.timezone("Asia/Kolkata"))

    if reminder_time <= now:
        print(f"⏩ Skipping reminder for past event '{title}'")
        return

    def send_reminder():
        try:
            msg = f"⏰ Reminder: '{title}' starts in {minutes_before} minutes!"
            if meet_link:
                msg += f"\n🔗 Join: {meet_link}"
            to_number = twilio_whatsapp_format(whatsapp_id)
            twilio_client.messages.create(from_=TWILIO_FROM, to=to_number, body=msg)
            print(f"📤 Reminder sent for '{title}' to {to_number}")
        except Exception as e:
            print(f"❌ Reminder send failed for {title}: {e}")

    scheduler.add_job(send_reminder, 'date', run_date=reminder_time)
    print(f"🕒 Reminder scheduled for '{title}' at {reminder_time.isoformat()}")


def is_meeting(summary: str, description: str = "") -> bool:
    meeting_keywords = ["meet", "meeting", "google meet", "call", "video call", "zoom", "discussion"]
    text = f"{summary or ''} {description or ''}".lower()
    return any(word in text for word in meeting_keywords)


# ────────── Create Event ──────────
async def add_calendar_event(
    whatsapp_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    attendees: list | None = None,
    request_meet: bool | None = None,
    reminder_minutes_before: int = 10
):
    """
    Create a Google Calendar event.
    Automatically creates a Google Meet link and schedules WhatsApp reminders.
    """
    if not whatsapp_id:
        return "⚠️ Invalid WhatsApp ID."

    norm_whatsapp = normalize_whatsapp_id(whatsapp_id)

    async with async_session() as session:
        result = await session.execute(select(GoogleToken).where(GoogleToken.whatsapp_id == norm_whatsapp))
        token = result.scalars().first()
        if not token:
            return "⚠️ Please link your Google Calendar first."

        creds = google.oauth2.credentials.Credentials.from_authorized_user_info({
            "token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": token.scopes
        }, SCOPES)

        service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)

        start_dt = parse_iso_datetime(start_time)
        end_dt = parse_iso_datetime(end_time)

        event_body = {
            "summary": summary,
            "description": description or "",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        }

        if attendees:
            event_body["attendees"] = [{"email": e} for e in attendees if "@" in e]

        need_meet = request_meet if request_meet is not None else is_meeting(summary, description)
        if need_meet:
            event_body["conferenceData"] = {
                "createRequest": {
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    "requestId": f"meet-{norm_whatsapp.replace('+','')}-{int(datetime.now().timestamp())}"
                }
            }

        try:
            created_event = service.events().insert(
                calendarId="primary",
                body=event_body,
                conferenceDataVersion=1 if need_meet else 0
            ).execute()
        except Exception as e:
            print(f"❌ Google Calendar API error creating event: {e}")
            return "⚠️ Could not create calendar event."

        print("📝 Google created_event response:", created_event)

        meet_link = created_event.get("hangoutLink")
        if not meet_link:
            conf = created_event.get("conferenceData")
            if conf and conf.get("entryPoints"):
                for ep in conf["entryPoints"]:
                    if ep.get("uri") and "meet.google.com" in ep.get("uri"):
                        meet_link = ep["uri"]
                        break
            if not meet_link and conf and conf.get("conferenceId"):
                meet_link = f"https://meet.google.com/{conf['conferenceId']}"

        schedule_meeting_reminder(norm_whatsapp, summary, start_dt.isoformat(), meet_link, reminder_minutes_before)

        reply = f"✅ Event '{summary}' created for {start_dt.isoformat()}."
        if meet_link:
            reply += f"\n🔗 Google Meet: {meet_link}"
        else:
            reply += "\n(🛈 No Meet link was attached — may be restricted by Workspace settings.)"
        reply += f"\n🕒 I’ll remind you {reminder_minutes_before} minutes before it starts."
        return reply


# ────────── Update Event ──────────
async def update_calendar_event(
    whatsapp_id: str,
    match_summary: str,
    new_start_time: str | None = None,
    new_end_time: str | None = None,
    description: str | None = None
):
    whatsapp_id = normalize_whatsapp_id(whatsapp_id)
    async with async_session() as session:
        result = await session.execute(
            select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id)
        )
        token = result.scalars().first()
        if not token:
            return "⚠️ Please link your Google Calendar first."

        creds = google.oauth2.credentials.Credentials.from_authorized_user_info({
            "token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": token.scopes
        }, SCOPES)

        service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)
        now = datetime.utcnow().isoformat() + "Z"
        events = service.events().list(calendarId="primary", timeMin=now, singleEvents=True, orderBy="startTime").execute().get("items", [])
        for e in events:
            if e.get("summary", "").lower() == match_summary.lower():
                if new_start_time:
                    e["start"]["dateTime"] = new_start_time
                    e["start"]["timeZone"] = "Asia/Kolkata"
                if new_end_time:
                    e["end"]["dateTime"] = new_end_time
                    e["end"]["timeZone"] = "Asia/Kolkata"
                if description:
                    e["description"] = description

                updated_event = service.events().update(calendarId="primary", eventId=e["id"], body=e).execute()
                title = updated_event.get("summary", match_summary)
                start = updated_event["start"].get("dateTime")
                return f"✅ Updated '{title}' to start at {start}."
        return f"❌ Event '{match_summary}' not found."


# ────────── Fetch Upcoming Events ──────────
async def fetch_upcoming_events(whatsapp_id, date):
    """
    Fetch all events for the specified date (YYYY-MM-DD or ISO).
    """
    whatsapp_id = normalize_whatsapp_id(whatsapp_id)
    async with async_session() as session:
        result = await session.execute(select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id))
        token = result.scalars().first()
        if not token:
            return "⚠️ Please link your Google Calendar first."

        creds = google.oauth2.credentials.Credentials.from_authorized_user_info({
            "token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": token.scopes
        }, SCOPES)

        service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)
        tz = pytz.timezone("Asia/Kolkata")

        try:
            base_date = dateutil_parser.isoparse(date)
        except Exception:
            base_date = datetime.now(tz)

        start = tz.localize(base_date.replace(hour=0, minute=0, second=0, microsecond=0))
        end = start + timedelta(days=1)

        events = service.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute().get("items", [])

        if not events:
            return f"📭 No events found for {start.strftime('%d %b %Y')}."

        lines = []
        for e in events:
            title = e.get("summary", "(No title)")
            start_time = e["start"].get("dateTime", e["start"].get("date"))
            time_fmt = dateutil_parser.isoparse(start_time).astimezone(tz).strftime("%I:%M %p")
            lines.append(f"🗓️ {title} – {time_fmt}")

        return "Here’s your schedule:\n\n" + "\n".join(lines)
