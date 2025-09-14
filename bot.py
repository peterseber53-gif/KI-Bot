from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import openai
import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import datetime

# Lade Umgebungsvariablen
load_dotenv()# --- BEGIN: write Google service account json from env if provided ---
import os
gsa = os.getenv("GOOGLE_SERVICE_ACCOUNT")
if gsa:
    with open("service_account.json", "w", encoding="utf-8") as f:
        f.write(gsa)
# --- END ---

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

# Twilio Client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# OpenAI Key
openai.api_key = OPENAI_API_KEY

# Flask App
app = Flask(__name__)

# Google Calendar Setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
import json
service_account_info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)

service = build('calendar', 'v3', credentials=credentials)

# Hilfsfunktion: Termin in Kalender eintragen
def add_event_to_calendar(summary, start_time, duration_minutes):
    start = start_time.isoformat()
    end = (start_time + datetime.timedelta(minutes=duration_minutes)).isoformat()
    event = {
        'summary': summary,
        'start': {'dateTime': start, 'timeZone': 'Europe/Berlin'},
        'end': {'dateTime': end, 'timeZone': 'Europe/Berlin'},
    }
    event = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    return event.get('id')

# Flask Route für SMS
@app.route("/sms", methods=['POST'])
def sms_reply():
    incoming_msg = request.form.get('Body')
    from_number = request.form.get('From')
    resp = MessagingResponse()

    # OpenAI Anfrage
    prompt = f"Du bist ein freundlicher Rezeptionist. Kunde schreibt: {incoming_msg}. Antworte kurz und frage nach Name, Datum, Uhrzeit, Dauer."
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=150
    )
    answer = response.choices[0].text.strip()

    # Sende Antwort zurück
    resp.message(answer)
    return str(resp)

if __name__ == "__main__":
    app.run(if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))  # Render gibt den Port vor
    app.run(host="0.0.0.0", port=port)
