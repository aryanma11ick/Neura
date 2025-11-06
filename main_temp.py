from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text, ARRAY, TIMESTAMP, select
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from groq import Groq
from twilio.rest import Client
from datetime import datetime
from dotenv import load_dotenv
import json, os, re, pytz, difflib
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta

# ----------------------------
# Load environment variables
# ----------------------------
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
NGROK_URL = os.getenv("NGROK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

if not all([DATABASE_URL, NGROK_URL, GROQ_API_KEY, TWILIO_SID, TWILIO_TOKEN, TWILIO_WHATSAPP_NUMBER]):
    raise ValueError("❌ Missing required environment variables")

# ----------------------------
# App, DB, and Clients
# ----------------------------
app = FastAPI()
engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()
async_session = async_sessionmaker(engine, expire_on_commit=False)
groq_client = Groq(api_key=GROQ_API_KEY)
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

oauth_state_map = {}

# ----------------------------
# Google setup
# ----------------------------
GOOGLE_CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# ----------------------------
# Database Model
# ----------------------------
class GoogleToken(Base):
    __tablename__ = "google_tokens"
    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String(50), unique=True)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_uri = Column(Text)
    client_id = Column(Text)
    client_secret = Column(Text)
    scopes = Column(ARRAY(String))
    expiry = Column(TIMESTAMP)

# ----------------------------
# Startup: Initialize DB
# ----------------------------
@app.on_event("startup")
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database ready.")

# ----------------------------
# Google Auth
# ----------------------------
@app.get("/auth", response_class=HTMLResponse)
async def auth(whatsapp_id: str):
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE, scopes=SCOPES
    )
    flow.redirect_uri = f"{NGROK_URL}/callback"
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    oauth_state_map[state] = whatsapp_id.strip()
    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;text-align:center;padding-top:40vh;">
        <h2>Connect Google Calendar</h2>
        <a href="{authorization_url}"
           style="padding:10px 20px;background:#4285F4;color:white;border-radius:8px;text-decoration:none;">
           🔗 Connect with Google
        </a>
    </body></html>
    """)

# ----------------------------
# OAuth Callback
# ----------------------------
@app.get("/callback", response_class=HTMLResponse)
async def callback(request: Request):
    state = request.query_params.get("state")
    whatsapp_id = oauth_state_map.pop(state, None)
    if not whatsapp_id:
        return HTMLResponse("❌ Invalid or expired OAuth session.", status_code=400)

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE, scopes=SCOPES
    )
    flow.redirect_uri = f"{NGROK_URL}/callback"
    flow.fetch_token(authorization_response=str(request.url))
    creds = flow.credentials

    async with async_session() as session:
        whatsapp_id = whatsapp_id.strip()
        if not whatsapp_id.startswith("+"):
            whatsapp_id = f"+{whatsapp_id}"

        result = await session.execute(select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id))
        existing = result.scalars().first()

        if existing:
            existing.access_token = creds.token
            existing.refresh_token = getattr(creds, "refresh_token", existing.refresh_token)
            existing.token_uri = creds.token_uri
            existing.client_id = creds.client_id
            existing.client_secret = creds.client_secret
            existing.scopes = creds.scopes
            existing.expiry = creds.expiry
            print(f"🔁 Updated Google tokens for {whatsapp_id}")
        else:
            new_token = GoogleToken(
                whatsapp_id=whatsapp_id,
                access_token=creds.token,
                refresh_token=getattr(creds, "refresh_token", ""),
                token_uri=creds.token_uri,
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                scopes=creds.scopes,
                expiry=creds.expiry
            )
            session.add(new_token)
            print(f"🆕 Added new Google token for {whatsapp_id}")
        await session.commit()

    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{whatsapp_id}",
        body="✅ Google Calendar linked! You can now ask me to show, add, or update events."
    )

    return HTMLResponse("<h2>✅ Linked! You can return to WhatsApp now.</h2>")

# ----------------------------
# Internal: Add Event
# ----------------------------
async def add_calendar_event(whatsapp_id: str, summary: str, start_time: str, end_time: str, description: str = ""):
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
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
        }
        service.events().insert(calendarId="primary", body=event).execute()
        return f"✅ Event '{summary}' created successfully for {start_time}!"

# ----------------------------
# Internal: Update Event
# ----------------------------
async def update_calendar_event(whatsapp_id: str, match_summary: str, new_start_time: str = None, new_end_time: str = None, description: str = None):
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
        now = datetime.utcnow().isoformat() + "Z"
        events_result = service.events().list(
            calendarId="primary", timeMin=now, maxResults=20, singleEvents=True, orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return "⚠️ You have no upcoming events to update."

        summaries = [e.get("summary", "").lower() for e in events]
        best_match = difflib.get_close_matches(match_summary.lower(), summaries, n=1, cutoff=0.5)
        if not best_match:
            return f"❌ No matching event found for '{match_summary}'."

        target_summary = best_match[0]
        event = next(e for e in events if e.get("summary", "").lower() == target_summary)
        event_id = event["id"]

        if new_start_time:
            event["start"]["dateTime"] = new_start_time
        if new_end_time:
            event["end"]["dateTime"] = new_end_time
        if description:
            event["description"] = description

        service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return f"✅ Updated event '{target_summary}' successfully!"

# ----------------------------
# WhatsApp Webhook
# ----------------------------
@app.post("/webhook")
async def webhook(From: str = Form(...), Body: str = Form(...)):
    whatsapp_id = From.replace("whatsapp:", "").strip()
    if not whatsapp_id.startswith("+"):
        whatsapp_id = f"+{whatsapp_id}"

    msg = Body.lower().strip()
    print(f"📩 Incoming from {whatsapp_id}: {msg}")
    reply = ""

    # 🔗 Linking
    if "link" in msg or "connect" in msg:
        reply = f"🔗 Tap here to link your Google Calendar:\n{NGROK_URL}/auth?whatsapp_id={whatsapp_id}"

    # 📆 Show Schedule / Show Events Added
    elif any(phrase in msg for phrase in ["show my schedule", "show events", "show events added", "my meetings", "my calendar", "list events", "what’s on my calendar", "upcoming events"]):
        try:
            async with async_session() as session:
                result = await session.execute(select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id))
                token = result.scalars().first()

                if not token:
                    reply = "⚠️ Please link your Google Calendar first using the link command."
                else:
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
                    events_result = service.events().list(
                        calendarId="primary",
                        timeMin=now,
                        maxResults=10,
                        singleEvents=True,
                        orderBy="startTime"
                    ).execute()
                    events = events_result.get("items", [])

                    if not events:
                        reply = "📭 You have no upcoming events!"
                    else:
                        tz = pytz.timezone("Asia/Kolkata")
                        lines = []
                        for e in events:
                            start = e["start"].get("dateTime", e["start"].get("date"))
                            dt = dateutil_parser.isoparse(start).astimezone(tz)
                            summary = e.get("summary", "(No Title)")
                            lines.append(f"🗓️ {summary} – {dt.strftime('%d %b, %I:%M %p')}")
                        reply = "Here’s your upcoming schedule:\n\n" + "\n".join(lines)

        except Exception as e:
            print(f"❌ Schedule fetch error: {e}")
            reply = "⚠️ I couldn’t fetch your schedule right now. Try again later."

    # 📅 Add or Update Event
    elif any(word in msg for word in ["add", "meeting", "event", "create", "update", "move", "change", "reschedule"]):
        try:
            system_prompt = f"""
            You are a Google Calendar assistant. 
            Current time: {datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()}.
            Determine if the user wants to CREATE or UPDATE an event.
            Return ONLY one JSON object as shown below.
            """

            llm_response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": msg}
                ],
                temperature=0.15
            )

            text = (llm_response.choices[0].message.content or "").strip()
            print("🧠 LLM output:", text)

            data = None
            try:
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON decode failed: {e}")

            if not data or not isinstance(data, dict):
                raise ValueError("Empty or invalid LLM output")

            tz = pytz.timezone("Asia/Kolkata")

            if data.get("action") == "create_event":
                start_dt = dateutil_parser.isoparse(data["start_time"]).astimezone(tz)
                end_dt = dateutil_parser.isoparse(data["end_time"]).astimezone(tz)
                now = datetime.now(tz)
                if start_dt <= now:
                    while start_dt <= now:
                        start_dt += relativedelta(years=1)
                        end_dt += relativedelta(years=1)
                reply = await add_calendar_event(
                    whatsapp_id,
                    data["summary"],
                    start_dt.isoformat(),
                    end_dt.isoformat(),
                    data.get("description", "")
                )

            elif data.get("action") == "update_event":
                reply = await update_calendar_event(
                    whatsapp_id,
                    data.get("match_summary", ""),
                    data.get("new_start_time"),
                    data.get("new_end_time"),
                    data.get("description")
                )
            else:
                reply = "⚠️ I couldn’t determine whether to add or update an event."

        except Exception as e:
            print(f"❌ Event handling error: {e}")
            reply = "⚠️ I couldn’t process that completely. Try 'Add meeting tomorrow at 4 PM'."

    # 💬 Casual Chat
    else:
        try:
            r = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are Neura, a friendly WhatsApp assistant that manages Google Calendar and chats casually."},
                    {"role": "user", "content": Body}
                ],
                temperature=0.6
            )
            reply = r.choices[0].message.content.strip()
        except Exception as e:
            reply = f"❌ AI error: {e}"

    twilio_client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=reply, to=From)
    print(f"🤖 Replied to {whatsapp_id}: {reply}")
    return "OK"
