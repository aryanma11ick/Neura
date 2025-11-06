# services/google_auth.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import google_auth_oauthlib.flow
import google.oauth2.credentials
from db.models import GoogleToken
from db.init_db import async_session
from sqlalchemy import select
from twilio.rest import Client
import os

router = APIRouter()

# ────────── Twilio Setup ──────────
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# ────────── Google OAuth Setup ──────────
GOOGLE_CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
]
NGROK_URL = os.getenv("NGROK_URL")
oauth_state_map = {}

# ────────── Helper: Normalize WhatsApp Number ──────────
def normalize_whatsapp_id(whatsapp_id: str) -> str:
    """
    Normalize a WhatsApp number to the canonical +<number> format.
    """
    if not whatsapp_id:
        return ""
    whatsapp_id = whatsapp_id.strip()
    if whatsapp_id.startswith("whatsapp:"):
        whatsapp_id = whatsapp_id.replace("whatsapp:", "")
    if not whatsapp_id.startswith("+"):
        whatsapp_id = f"+{whatsapp_id}"
    return whatsapp_id


def format_whatsapp_number(raw_number: str) -> str:
    """
    Ensure correct Twilio WhatsApp format: whatsapp:+<number>
    """
    num = normalize_whatsapp_id(raw_number)
    return f"whatsapp:{num}"


# ────────── Step 1: OAuth Auth Link ──────────
@router.get("/auth", response_class=HTMLResponse)
async def auth(whatsapp_id: str):
    """
    Generates a Google OAuth authorization link for the user.
    """
    whatsapp_id = normalize_whatsapp_id(whatsapp_id)

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE, scopes=SCOPES
    )
    flow.redirect_uri = f"{NGROK_URL}/callback"

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    # Map state to the normalized WhatsApp ID
    oauth_state_map[state] = whatsapp_id

    print(f"🌐 OAuth flow started for {whatsapp_id}")
    return HTMLResponse(f"""
    <html>
    <body style="font-family:sans-serif;text-align:center;padding-top:40vh;">
        <h2>Connect Google Calendar</h2>
        <a href="{authorization_url}"
           style="padding:10px 20px;background:#4285F4;color:white;border-radius:8px;text-decoration:none;">
           🔗 Connect with Google
        </a>
    </body>
    </html>
    """)


# ────────── Step 2: OAuth Callback ──────────
@router.get("/callback", response_class=HTMLResponse)
async def callback(request: Request):
    """
    Handles Google's OAuth callback, saves tokens to DB, and notifies the user.
    """
    state = request.query_params.get("state")
    whatsapp_id = oauth_state_map.pop(state, None)

    if not whatsapp_id:
        return HTMLResponse("❌ Invalid or expired OAuth session.", status_code=400)

    whatsapp_id = normalize_whatsapp_id(whatsapp_id)

    try:
        # Exchange authorization code for access/refresh tokens
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            GOOGLE_CLIENT_SECRETS_FILE, scopes=SCOPES
        )
        flow.redirect_uri = f"{NGROK_URL}/callback"
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials

        async with async_session() as session:
            result = await session.execute(
                select(GoogleToken).where(GoogleToken.whatsapp_id == whatsapp_id)
            )
            token = result.scalars().first()

            if token:
                token.access_token = creds.token
                token.refresh_token = getattr(creds, "refresh_token", token.refresh_token)
                token.token_uri = creds.token_uri
                token.client_id = creds.client_id
                token.client_secret = creds.client_secret
                token.scopes = creds.scopes
                token.expiry = creds.expiry
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

        # Send WhatsApp confirmation
        to_number = format_whatsapp_number(whatsapp_id)
        twilio_client.messages.create(
            from_=TWILIO_FROM,
            to=to_number,
            body="✅ Google Calendar linked! You can now add or view your events."
        )
        print(f"📤 Sent confirmation to {to_number}")

        return HTMLResponse("<h2>✅ Linked successfully! You can return to WhatsApp now.</h2>")

    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        return HTMLResponse(f"❌ Something went wrong: {e}", status_code=500)
