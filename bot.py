from flask import Flask, request, jsonify
import os
import openai
from twilio.twiml.messaging_response import MessagingResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# === API KEYS & CONFIG ===
openai.api_key = os.getenv("OPENAI_API_KEY")

twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_auth = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")

# === GOOGLE CALENDAR SETUP ===
google_credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
creds_dict = json.loads(google_credentials_json)

creds = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=["https://www.googleapis.com/auth/calendar"]
)

calendar_service = build("calendar", "v3", credentials=creds)
calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")


# === HILFSFUNKTION: TERMIN EINTRAGEN ===
def create_event(summary="Kunden-Termin", minutes_from_now=60):
    start_time = datetime.utcnow() + timedelta(minutes=minutes_from_now)
    end_time = start_time + timedelta(minutes=30)

    event = {
        "summary": summary,
        "start": {"dateTime": start_time.isoformat() + "Z", "timeZone": "UTC"},
        "end": {"dateTime": end_time.isoformat() + "Z", "timeZone": "UTC"},
    }

    event_result = calendar_service.events().insert(
        calendarId=calendar_id, body=event
    ).execute()

    return event_result.get("htmlLink")


# === ROUTE: TWILIO WEBHOOK ===
@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming_msg = request.values.get("Body", "").strip()

    # Antwort von OpenAI holen
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": incoming_msg}]
    )

    reply_text = response.choices[0].message.content

    # Wenn Kunde "Termin" schreibt -> neuen Termin anlegen
    if "termin" in incoming_msg.lower():
        event_link = create_event()
        reply_text = f"Ich habe einen Termin für dich eingetragen! 📅 Hier der Link: {event_link}"

    # Twilio-Antwort
    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp)


# === START ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
