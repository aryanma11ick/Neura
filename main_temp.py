from fastapi import FastAPI, Request, Body
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text, ARRAY, TIMESTAMP, select
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import Optional

# --------------------
# Load environment variables
# --------------------
load_dotenv()

DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
NGROK_URL: Optional[str] = os.getenv("NGROK_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL is not set in .env")

if not NGROK_URL:
    raise ValueError("❌ NGROK_URL is not set in .env")

# --------------------
# FastAPI setup
# --------------------
app = FastAPI()

# --------------------
# PostgreSQL setup
# --------------------
engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()

# ✅ use async_sessionmaker (no need for bind= or class_=AsyncSession)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# --------------------
# Google setup
# --------------------
GOOGLE_CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly"
]

# --------------------
# Database Model
# --------------------
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

# --------------------
# Initialize DB
# --------------------
@app.on_event("startup")
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database initialized and connected!")

# --------------------
# Google Auth
# --------------------
@app.get("/auth")
async def auth(whatsapp_id: str):
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES
    )
    flow.redirect_uri = f"{NGROK_URL}/callback"

    # ✅ Must be lowercase string "true"
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",  # ← Google expects a string, not bool
        prompt="consent"
    )

    print(f"🔗 Redirecting to Google Auth: {authorization_url}")
    print(f"🧩 State: {state}")

    return RedirectResponse(url=authorization_url)
# --------------------
# Callback to store tokens
# --------------------
@app.get("/callback")
async def callback(request: Request):
    state = request.query_params.get("state")
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state
    )
    flow.redirect_uri = f"{NGROK_URL}/callback"
    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials

    async with async_session() as session:
        token = GoogleToken(
            whatsapp_id="test_user",  # Replace later with actual WhatsApp user ID
            access_token=creds.token,
            refresh_token=getattr(creds, "refresh_token", ""),
            token_uri=getattr(creds, "token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            scopes=creds.scopes,
            expiry=creds.expiry
        )
        await session.merge(token)
        await session.commit()

    return {"message": "✅ Calendar linked & saved to DB"}

# --------------------
# Fetch Calendar Events
# --------------------
@app.get("/events")
async def get_events(whatsapp_id: str):
    async with async_session() as session:
        result = await session.execute(
            select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id)
        )
        token = result.scalars().first()
        if not token:
            return {"error": "User not authenticated."}

        creds_data = {
            "token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": token.scopes,
        }

        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
            creds_data, SCOPES
        )

        service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)

        events_result = service.events().list(
            calendarId="primary",
            maxResults=5,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        formatted = [
            f"{e.get('summary', 'No title')} at {e['start'].get('dateTime', e['start'].get('date'))}"
            for e in events
        ]
        return {"events": formatted}
    
@app.post("/addevent")
async def add_event(
    whatsapp_id: str,
    summary: str = Body(..., embed=True),
    start_time: str = Body(..., embed=True),
    end_time: str = Body(..., embed=True),
    description: str = Body(None, embed=True)
):
    async with async_session() as session:
        # ✅ Fetch stored tokens
        result = await session.execute(
            select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id)
        )
        token = result.scalars().first()
        if not token:
            return {"error": "User not authenticated. Please link your calendar first."}

        # ✅ Prepare credentials
        creds_data = {
            "token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": token.scopes,
        }
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
            creds_data, SCOPES
        )

        # ✅ Initialize Google Calendar API
        service = googleapiclient.discovery.build("calendar", "v3", credentials=creds)

        # ✅ Create the event body
        event = {
            "summary": summary,
            "description": description or "",
            "start": {
                "dateTime": start_time,
                "timeZone": "Asia/Kolkata"
            },
            "end": {
                "dateTime": end_time,
                "timeZone": "Asia/Kolkata"
            },
        }

        # ✅ Insert event
        created_event = service.events().insert(
            calendarId="primary",
            body=event
        ).execute()

        return {
            "message": "✅ Event created successfully!",
            "event_link": created_event.get("htmlLink")
        }

