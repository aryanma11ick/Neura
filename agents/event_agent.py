from services.google_calendar import add_calendar_event, update_calendar_event
from groq import Groq
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta
import pytz, json, re, os
from datetime import datetime

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

async def handle_event(msg, whatsapp_id):
    try:
        system_prompt = f"""
        You are a Google Calendar event manager.
        Current time: {datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()}.
        Return only JSON in one of the following formats:

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
        """

        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg},
            ],
            temperature=0.15
        )

        text = (r.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group(0))

        tz = pytz.timezone("Asia/Kolkata")

        if data.get("action") == "create_event":
            start_dt = dateutil_parser.isoparse(data["start_time"]).astimezone(tz)
            end_dt = dateutil_parser.isoparse(data["end_time"]).astimezone(tz)
            now = datetime.now(tz)
            if start_dt <= now:
                while start_dt <= now:
                    start_dt += relativedelta(days=1)
                    end_dt += relativedelta(days=1)
            return await add_calendar_event(whatsapp_id, data["summary"], start_dt.isoformat(), end_dt.isoformat(), data.get("description", ""))

        elif data.get("action") == "update_event":
            return await update_calendar_event(
                whatsapp_id,
                data.get("match_summary", ""),
                data.get("new_start_time"),
                data.get("new_end_time"),
                data.get("description")
            )

        return "⚠️ I couldn’t determine what to do with that event."

    except Exception as e:
        print(f"❌ Event agent error: {e}")
        return "⚠️ I couldn’t process that completely. Try again later."
