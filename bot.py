from flask import Flask, request, jsonify
import os
import openai
import json
import logging
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import dateparser
from datetime import timedelta

# Logging aktivieren
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# OpenAI API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Google Calendar Setup
creds_json = os.environ.get("GOOGLE_CREDS_JSON")
if not creds_json:
    raise ValueError("Fehlende GOOGLE_CREDS_JSON Umgebungsvariable")

creds_dict = json.loads(creds_json)
credentials = Credentials.from_service_account_info(creds_dict)
calendar_service = build("calendar", "v3", credentials=credentials)
calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")

# OpenAI Antwort generieren + Kalender eintragen
def get_openai_response(user_message):
    logging.info(f"User-Message: {user_message}")

    # AI-Antwort holen
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Du bist ein Assistent, der Termine für den Kunden einträgt."},
            {"role": "user", "content": user_message}
        ]
    )
    ai_reply = response.choices[0].message.content

    # Datum erkennen
    date = dateparser.parse(user_message, settings={'PREFER_DATES_FROM': 'future'})
    if date:
        try:
            event_link = create_calendar_event(date, summary="Kundentermin")
            if event_link:
                ai_reply += f"\n✅ Termin wurde eingetragen: {event_link}"
        except Exception as e:
            ai_reply += f"\n⚠️ Konnte Termin nicht eintragen: {str(e)}"

    return ai_reply

# Kalender-Eintrag erstellen
def create_calendar_event(date, summary="Kundentermin"):
    if not date:
        return None

    event = {
        "summary": summary,
        "start": {"dateTime": date.isoformat(), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": (date + timedelta(hours=1)).isoformat(), "timeZone": "Europe/Berlin"},
    }

    created_event = calendar_service.events().insert(calendarId=calendar_id, body=event).execute()
    return created_event.get("htmlLink")

# 📩 Twilio SMS Webhook
@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming_msg = request.form.get("Body", "")
    logging.info(f"SMS eingehend: {incoming_msg}")
    reply = get_openai_response(incoming_msg)

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

# 📞 Twilio Voice Webhook
@app.route("/voice", methods=["POST"])
def voice_reply():
    incoming_msg = request.form.get("SpeechResult", "")
    if not incoming_msg:
        incoming_msg = "Hallo, ich möchte einen Termin vereinbaren."
    logging.info(f"Voice eingehend: {incoming_msg}")

    reply = get_openai_response(incoming_msg)

    vr = VoiceResponse()
    vr.say(reply, voice="alice", language="de-DE")
    vr.listen()
    return str(vr)

# 🧪 Test-Endpoint (für curl)
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    reply = get_openai_response(user_message)
    return jsonify({"reply": reply})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
