from fastapi import FastAPI, Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    # Get the incoming WhatsApp message data
    form_data = await request.form()
    sender = form_data.get("From")
    message_body = form_data.get("Body")

    print(f"📩 New message from {sender}: {message_body}")

    # Create a Twilio response
    resp = MessagingResponse()
    reply = resp.message("Hi there! 👋 Your message was received successfully.")

    # Send the TwiML response back to Twilio
    return Response(content=str(resp), media_type="application/xml")

@app.get("/")
def root():
    return {"status": "Neura WhatsApp bot is running ✅"}
