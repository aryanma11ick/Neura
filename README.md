
# Neura

Neura is a WhatsApp-based AI personal assistant built using a multi-agent AI workflow.
It helps users manage schedules, reminders, notes, and planning tasks through natural language conversations on WhatsApp.

The system leverages Groq LLMs for fast reasoning, integrates with the Google Calendar API for real event scheduling, and communicates via the Twilio WhatsApp API.



- 💬 **WhatsApp Interface**  
  Chat with the assistant directly on WhatsApp using Twilio.

- 🧩 **Multi-Agent Architecture**  
  Specialized agents handle different tasks:
  - Planner Agent — scheduling & reminders  
  - Calendar Agent — Google Calendar integration  
  - Notes Agent — saving and retrieving notes  
  - Memory Agent — persistent user context  

- 📆 **Google Calendar Integration**  
  Create and manage calendar events using natural language.

- 🧠 **LLM-Powered Reasoning**  
  Uses the Groq API for low-latency, context-aware responses.

- 💾 **Persistent Storage**  
  Stores reminders, notes, and memory using PostgreSQL / SQLite.

- ⏰ **Automated Reminders**  
  Background scheduler sends reminders automatically via WhatsApp.
## Tech Stack
- **Backend:** Python, FastAPI  
- **LLM:** Groq API  
- **Messaging:** Twilio WhatsApp API  
- **Calendar:** Google Calendar API (OAuth2)  
- **Database:** PostgreSQL / SQLite  
- **Scheduler:** APScheduler  
- **Tunneling (Development):** ngrok  
