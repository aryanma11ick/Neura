from groq import Groq
import os

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

async def handle_chat(msg):
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are Neura, a helpful AI chat assistant for WhatsApp."},
            {"role": "user", "content": msg}
        ],
        temperature=0.7
    )
    # safely extract content, default to empty string if missing
    try:
        content = r.choices[0].message.content
    except Exception:
        content = None
    return (content or "").strip()
