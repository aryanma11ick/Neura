import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()  # Load .env file

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_message(to, text):
    print(f"From: {TWILIO_PHONE_NUMBER}")
    print(f"To: {to}")
    message = client.messages.create(
        from_=TWILIO_PHONE_NUMBER,
        body=text,
        to=to
    )
    print(f"✅ Message sent! SID: {message.sid}")

# Example test
if __name__ == "__main__":
    send_message("whatsapp:+919903541340", "Hello from your AI assistant 👋")