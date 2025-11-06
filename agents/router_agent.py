from groq import Groq
import json, re, os

# ────────── Lazy-load environment variables ──────────
from dotenv import load_dotenv
load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

async def route_message(msg: str) -> str:
    """
    Classify message intent for routing.
    Possible intents:
    - link_google
    - create_event
    - update_event
    - show_schedule
    - casual_chat
    """
    prompt = """
    You are a routing assistant for a WhatsApp-based AI assistant (Neura)
    that can manage Google Calendar.

    Classify the user's intent into one of the following categories:

    1. "link_google" — when the user mentions linking, connecting, logging in, 
       authorizing, or syncing their Google or Calendar account.
       Examples:
       - "link my google account"
       - "connect google calendar"
       - "authorize google"
       - "sign in to google"
       - "login to calendar"

    2. "create_event" — when the user wants to add or create a meeting or event.
       Examples:
       - "add meeting tomorrow at 5pm"
       - "schedule call with John"

    3. "update_event" — when the user wants to modify or reschedule an existing event.
       Examples:
       - "move meeting to 6pm"
       - "update project review time"

    4. "show_schedule" — when the user wants to view their calendar or events.
       Examples:
       - "show my schedule for tomorrow"
       - "what’s on my calendar today"

    5. "casual_chat" — everything else (small talk, greetings, questions, etc.)

    Return ONLY valid JSON in this format:
    {"intent": "<one_of_the_above>"}
    """

    # Call LLM
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": msg},
        ],
        temperature=0
    )

    # Parse JSON safely
    text = r.choices[0].message.content.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)

    try:
        data = json.loads(match.group(0))
        intent = data.get("intent", "casual_chat").strip()
        return intent
    except Exception:
        # 🔹 Fallback: manual keyword detection
        m = msg.lower()
        if any(word in m for word in ["link", "connect", "google", "login", "authorize", "auth"]):
            return "link_google"
        elif any(word in m for word in ["add", "create", "schedule", "meeting", "event"]):
            return "create_event"
        elif any(word in m for word in ["update", "move", "change", "reschedule"]):
            return "update_event"
        elif any(word in m for word in ["show", "calendar", "schedule", "events"]):
            return "show_schedule"
        else:
            return "casual_chat"
