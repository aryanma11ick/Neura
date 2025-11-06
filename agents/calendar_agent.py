# agents/calendar_agent.py

import pytz
from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser
from services.google_calendar import fetch_upcoming_events
from db.init_db import async_session
from db.models import GoogleToken
from sqlalchemy import select


async def handle_calendar(msg: str, whatsapp_id: str) -> str:
    """
    Handles user requests to show or summarize their calendar schedule.
    Example messages:
    - "show my schedule"
    - "what are my events tomorrow"
    - "show meetings for next week"
    """

    try:
        # ────────── Check if user is linked ──────────
        async with async_session() as session:
            result = await session.execute(
                select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id)
            )
            token = result.scalars().first()
            if not token:
                return "⚠️ No linked Google account. Please link it first using: 'link my Google account'."

        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)

        # ────────── Detect Day from Message ──────────
        msg_lower = msg.lower()
        target_date = now

        if "tomorrow" in msg_lower:
            target_date = now + timedelta(days=1)
        elif "next week" in msg_lower:
            target_date = now + timedelta(days=7)
        elif "day after" in msg_lower:
            target_date = now + timedelta(days=2)
        elif "yesterday" in msg_lower:
            target_date = now - timedelta(days=1)
        else:
            # Try to extract a specific date if mentioned (e.g., "show my schedule on 10 Nov")
            try:
                parsed_date = dateutil_parser.parse(msg, fuzzy=True)
                target_date = parsed_date.astimezone(tz)
            except Exception:
                target_date = now  # fallback to today

        # ────────── Fetch Events ──────────
        response = await fetch_upcoming_events(whatsapp_id, target_date.isoformat())
        return response

    except Exception as e:
        print(f"❌ Calendar agent error: {e}")
        return "⚠️ I couldn’t fetch your schedule right now."
