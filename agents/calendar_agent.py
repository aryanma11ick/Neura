# agents/calendar_agent.py
from groq import Groq
import os, json, re, pytz
from dateutil import parser as dateutil_parser
from datetime import datetime, timedelta
from services.google_calendar import fetch_upcoming_events  # your existing helper

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# small helper: try to safely parse a YYYY-MM-DD like string,
# returns None if invalid
def safe_iso_date(date_str: str):
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()
    # reject obvious placeholders like 'YYYY' or 'YYYY-MM-DD'
    if re.fullmatch(r"Y{2,}|YYYY(-MM(-DD)?)?", date_str, re.IGNORECASE):
        return None
    try:
        # parse only the date part and return YYYY-MM-DD
        dt = dateutil_parser.isoparse(date_str)
        return dt.date().isoformat()
    except Exception:
        # try general parse (natural language)
        try:
            dt = dateutil_parser.parse(date_str, default=datetime.now(pytz.timezone("Asia/Kolkata")))
            return dt.date().isoformat()
        except Exception:
            return None

# If user text contains words like "today"/"tomorrow" etc, map them
def detect_simple_natural_date(msg: str):
    m = msg.lower()
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    if "tomorrow" in m:
        return (now + timedelta(days=1)).date().isoformat()
    if "today" in m:
        return now.date().isoformat()
    if "next week" in m:
        # return the date for next Monday
        weekday = now.weekday()  # 0=Mon
        days_until_next_monday = (7 - weekday) % 7
        days_until_next_monday = days_until_next_monday or 7
        next_monday = (now + __import__('datetime').timedelta(days=days_until_next_monday)).date()
        return next_monday.isoformat()
    return None

async def handle_calendar(msg: str, whatsapp_id: str):
    """
    Attempt to use the LLM to extract a date; if that fails, fall back to
    natural-language detection; if that fails, default to today.
    Then call fetch_upcoming_events(whatsapp_id, date) which returns formatted text.
    """
    try:
        # 1) Ask LLM to extract a date if you want to rely on the model
        prompt = """
        Extract which single date the user wants to view from the message.
        Return JSON exactly like: {"date": "YYYY-MM-DD"}
        If the user did not specify a date, return {"date": ""}.
        Do NOT include any other text.
        """
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": msg}],
            temperature=0
        )

        text = (r.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        extracted_date = None
        if match:
            try:
                data = json.loads(match.group(0))
                extracted_date = safe_iso_date(data.get("date", "") if isinstance(data, dict) else "")
            except Exception:
                extracted_date = None

        # 2) If LLM gave nothing useful, try simple natural date detection from the text
        if not extracted_date:
            extracted_date = detect_simple_natural_date(msg)

        # 3) Final fallback: use today (Asia/Kolkata)
        if not extracted_date:
            tz = pytz.timezone("Asia/Kolkata")
            extracted_date = datetime.now(tz).date().isoformat()
            info_note = True
        else:
            info_note = False

        # 4) Fetch events using the normalized date string (YYYY-MM-DD)
        return_text = await fetch_upcoming_events(whatsapp_id, extracted_date)

        # If we defaulted to today, let user know
        if info_note:
            return f"(Showing calendar for {extracted_date})\n\n{return_text}"
        return return_text

    except Exception as e:
        print(f"❌ Calendar agent error: {e}")
        return "⚠️ I couldn’t fetch your schedule right now."
