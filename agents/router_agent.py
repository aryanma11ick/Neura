from groq import Groq
import json, re, os
from dotenv import load_dotenv

# ────────── Load environment ──────────
load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ────────── Router Function ──────────
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
    system_prompt = """
    You are a routing assistant for Neura — a WhatsApp-based AI assistant that manages Google Calendar.

    Your task: Classify the user's message into ONE of the following categories:

    1. "link_google" → when the user explicitly talks about linking, connecting, logging in,
       authorizing, or granting access to their Google account or Calendar.
       Examples:
       - "link my google account"
       - "connect to google calendar"
       - "authorize my calendar"
       - "sign in to google"
       - "login to calendar"

    2. "create_event" → when the user wants to add, create, or schedule an event or meeting.
       Examples:
       - "add meeting tomorrow at 5pm"
       - "schedule google meet with Aakash"
       - "create event for project review"

    3. "update_event" → when the user wants to change, move, or reschedule an existing event.
       Examples:
       - "move meeting to 6pm"
       - "change the time for jogging with Aakash"

    4. "show_schedule" → when the user wants to view their calendar or upcoming events.
       Examples:
       - "show my schedule for today"
       - "what's on my calendar tomorrow"
       - "see upcoming meetings"

    5. "casual_chat" → all other kinds of conversation not related to calendar actions.

    ⚠️ Rules:
    - If the message includes 'google meet', 'meet with', or a time expression like 'at 5pm' or 'tomorrow',
      it is almost always 'create_event', NOT 'link_google'.
    - Only classify as 'link_google' if the intent clearly involves authorization or linking.
    - Always respond with a single valid JSON object: {"intent": "<one_of_the_above>"}
    """

    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg},
            ],
            temperature=0
        )

        text = r.choices[0].message.content.strip()
        print("🧠 Router LLM raw output:", text)

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            intent = data.get("intent", "casual_chat").strip()
        else:
            intent = "casual_chat"

    except Exception as e:
        print(f"⚠️ LLM router error: {e}")
        intent = "casual_chat"

    # ────────── Fallback: Manual Keyword Rules ──────────
    m = msg.lower()

    if intent == "link_google" and any(
        kw in m for kw in ["meet", "meeting", "at ", "schedule", "event", "tomorrow", "today"]
    ):
        # looks like event creation instead of linking
        intent = "create_event"

    elif intent == "casual_chat":
        if any(kw in m for kw in ["add", "schedule", "create", "meeting", "event", "meet", "at "]):
            intent = "create_event"
        elif any(kw in m for kw in ["update", "move", "change", "reschedule"]):
            intent = "update_event"
        elif any(kw in m for kw in ["show", "calendar", "schedule", "events", "today", "tomorrow"]):
            intent = "show_schedule"
        elif any(kw in m for kw in ["link", "connect", "authorize", "login", "sign in"]):
            intent = "link_google"

    print(f"🔍 Final routed intent: {intent}")
    return intent
