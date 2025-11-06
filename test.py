from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Allow http for local dev
CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE")
SCOPES = [os.getenv("GOOGLE_SCOPES")]
REDIRECT_URI = "https://delma-palpitant-subtilely.ngrok-free.dev/callback"

flow = Flow.from_client_secrets_file(
    CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

credentials = None


@app.get("/")
async def index():
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)


@app.get("/callback")
async def callback(request: Request):
    global credentials
    code = request.query_params.get("code")

    flow.fetch_token(code=code)
    credentials = flow.credentials

    return RedirectResponse(url="/events")


@app.get("/events")
async def list_events():
    if not credentials:
        return HTMLResponse("<h3>Not authorized yet. Go to '/' to sign in.</h3>")

    service = build("calendar", "v3", credentials=credentials)
    events_result = (
        service.events()
        .list(calendarId="primary", maxResults=5, singleEvents=True, orderBy="startTime")
        .execute()
    )
    events = events_result.get("items", [])

    html = "<h2>Next 5 Events</h2><ul>"
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        html += f"<li>{start} — {event['summary']}</li>"
    html += "</ul>"

    return HTMLResponse(html)
