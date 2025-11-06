# agents/event_agent.py

from services.google_calendar import add_calendar_event, update_calendar_event
from groq import Groq
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta
import pytz, json, re, os
from datetime import datetime
from dotenv import load_dotenv

# ────────── Setup ──────────
load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ────────── Main Handler ──────────
async def handle_event(msg, whatsapp_id):
    """
    Handles both creation and updating of calendar events.
    Automatically attaches Google Meet links for meetings/calls.
    """
    try:
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)

        system_prompt = f"""
        You are a Google Calendar event manager AI.

        Current time: {now.isoformat()} (Asia/Kolkata)
        Extract structured JSON for event creation or update.

        Return ONLY one of the following JSON formats:

        For new events:
        {{
          "action": "create_event",
          "summary": "Event title",
          "start_time": "YYYY-MM-DDTHH:MM:SS+05:30",
          "end_time": "YYYY-MM-DDTHH:MM:SS+05:30",
          "description": "Optional"
        }}

        For updates:
        {{
          "action": "update_event",
          "match_summary": "Existing event title",
          "new_start_time": "YYYY-MM-DDTHH:MM:SS+05:30",
          "new_end_time": "YYYY-MM-DDTHH:MM:SS+05:30",
          "description": "Optional"
        }}

        Notes:
        - Always use Asia/Kolkata timezone.
        - If message contains 'Google Meet', 'video call', or 'call', mark this as a meeting.
        - If no end time is given, assume the event lasts 1 hour.
        """

        # ────────── LLM Call ──────────
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg},
            ],
            temperature=0.15
        )

        text = (r.choices[0].message.content or "").strip()
        print("🧠 Event Agent LLM output:", text)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group(0))

        # ────────── Handle CREATE EVENT ──────────
        if data.get("action") == "create_event":
            start_dt = dateutil_parser.isoparse(data["start_time"]).astimezone(tz)
            end_dt = dateutil_parser.isoparse(data["end_time"]).astimezone(tz)
            now = datetime.now(tz)

            # 🔹 If start time is in the past, shift it to tomorrow
            if start_dt <= now:
                while start_dt <= now:
                    start_dt += relativedelta(days=1)
                    end_dt += relativedelta(days=1)

            summary = data.get("summary", "Untitled Event")
            description = data.get("description", "")

            # 🔹 Detect if Google Meet link is required
            meet_keywords = ["google meet", "video call", "call", "meet with", "meeting"]
            request_meet = any(word in msg.lower() for word in meet_keywords)

            # 🔹 Call the calendar creation service
            reply = await add_calendar_event(
                whatsapp_id=whatsapp_id,
                summary=summary,
                start_time=start_dt.isoformat(),
                end_time=end_dt.isoformat(),
                description=description,
                request_meet=request_meet
            )
            return reply

        # ────────── Handle UPDATE EVENT ──────────
        elif data.get("action") == "update_event":
            new_start = data.get("new_start_time")
            new_end = data.get("new_end_time")

            return await update_calendar_event(
                whatsapp_id=whatsapp_id,
                match_summary=data.get("match_summary", ""),
                new_start_time=new_start,
                new_end_time=new_end,
                description=data.get("description", "")
            )

        # ────────── Fallback ──────────
        return "⚠️ I couldn’t determine what to do with that event."

    except Exception as e:
        print(f"❌ Event agent error: {e}")
        return "⚠️ I couldn’t process that completely. Try again later."
