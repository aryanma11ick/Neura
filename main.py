# main.py

from fastapi import FastAPI, Form
from twilio.rest import Client
from dotenv import load_dotenv
import os

# ────────── Load environment variables ──────────
load_dotenv()

# ────────── Import Agents ──────────
from agents.router_agent import route_message
from agents.event_agent import handle_event
from agents.calendar_agent import handle_calendar
from agents.chat_agent import handle_chat

# ────────── Database ──────────
from db.init_db import init_db

# ────────── Import Google OAuth Routes ──────────
from services.google_auth import router as google_auth_router

# ────────── Twilio Setup ──────────
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_PHONE_NUMBER")

if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM]):
    raise ValueError("❌ Missing Twilio environment variables.")

twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# ────────── FastAPI App ──────────
app = FastAPI()
app.include_router(google_auth_router)

# ────────── Startup ──────────
@app.on_event("startup")
async def on_startup():
    await init_db()
    print("✅ Database initialized successfully.")

# ────────── WhatsApp Webhook ──────────
@app.post("/webhook")
async def webhook(From: str = Form(...), Body: str = Form(...)):
    """
    Handles incoming WhatsApp messages and routes to appropriate agents.
    """
    whatsapp_id = From.replace("whatsapp:", "").strip()
    if not whatsapp_id.startswith("+"):
        whatsapp_id = f"+{whatsapp_id}"

    msg = Body.strip()
    print(f"📩 Incoming from {whatsapp_id}: {msg}")

    # ───── Detect Linking Keywords ─────
    if any(word in msg.lower() for word in ["link", "connect", "google", "login", "authorize", "auth", "account"]):
        NGROK_URL = os.getenv("NGROK_URL")
        reply = f"🔗 Tap here to link Google Calendar:\n{NGROK_URL}/auth?whatsapp_id={whatsapp_id}"

    else:
        # ───── Route Message Intent ─────
        intent = await route_message(msg)
        print(f"🧭 Routed intent: {intent}")

        try:
            if intent in ["create_event", "update_event"]:
                reply = await handle_event(msg, whatsapp_id)
            elif intent == "show_schedule":
                reply = await handle_calendar(msg, whatsapp_id)
            elif intent == "link_google":
                NGROK_URL = os.getenv("NGROK_URL")
                reply = f"🔗 Tap here to link Google Calendar:\n{NGROK_URL}/auth?whatsapp_id={whatsapp_id}"
            else:
                reply = await handle_chat(msg)
        except Exception as e:
            print(f"❌ Agent error: {e}")
            reply = "⚠️ Something went wrong while processing your request."

    # ───── Send Reply via Twilio ─────
    try:
        to_number = f"whatsapp:{whatsapp_id}"
        twilio_client.messages.create(
            from_=TWILIO_FROM,
            body=reply,
            to=to_number
        )
        print(f"🤖 Replied to {whatsapp_id}: {reply}")
    except Exception as e:
        print(f"❌ Twilio send error: {e}")

    return "OK"

# ────────── Health Check ──────────
@app.get("/")
async def root():
    return {"status": "✅ Neura Assistant running", "phase": "1.3 - Clean Multi-Agent + Shared Twilio Utils"}
