from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
import datetime
import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest

app = FastAPI()

# Scopes needed to create calendar events
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# Path to credentials
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'

def get_calendar_service():
    creds = None
    # Load saved credentials
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    # If no valid credentials, log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for next time
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    service = build('calendar', 'v3', credentials=creds)
    return service

@app.post("/add_event")
async def add_event():
    service = get_calendar_service()
    
    # Example event
    event = {
      'summary': "Aakash's Birthday",
      'location': 'Home',
      'description': "Celebrate Aakash's birthday 🎉",
      'start': {
        'dateTime': '2025-06-17T10:00:00+05:30',
        'timeZone': 'Asia/Kolkata',
      },
      'end': {
        'dateTime': '2025-06-17T12:00:00+05:30',
        'timeZone': 'Asia/Kolkata',
      },
    }

    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return {"status": "Event created", "event_id": created_event['id']}
