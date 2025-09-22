from flask import Flask, request, jsonify
import os
import openai
import json
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import dateparser

# Flask App starten
app = Flask(__name__)

# OpenAI konfigurieren
openai.api_key = os.getenv("OPENAI_API_KEY")

# Google Credentials laden
creds_json = os.environ.get("GOOGLE_CREDS_JSON")
if not creds_json:
    raise ValueError("Fehlende GOOGLE_CREDS_JSON Umgebungsvariable")

creds_dict = json.loads(creds_json)
credentials = Credentials.from_service_account_info(creds_dict)
calendar_service = build("calendar", "v3", credentials=credentials)

# Google Calendar ID aus Env
calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")


# OpenAI Antwort generieren
def get_openai_response(user_message):
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Du bist ein Assistent, der Termine für den Kunden einträgt."},
            {"role": "user", "content": user_message}
        ]
    )
    return response.choices[0].message.content


# Termin im Google Kalender erstellen
def create_calendar_event(date_text, summary="Kundentermin"):
    date = dateparser.parse(date_text)
    if not date:
        return None

    event = {
        "summary": summary,
        "start": {"dateTime": date.isoformat(), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": (dateparser.parse(date_text) + timedelta(hours=1)).isoformat(), "timeZone": "Europe/Berlin"},
    }

    created_event = calendar_service.events().insert(calendarId=calendar_id, body=event).execute()
    return created_event.get("htmlLink")


# 📩 Twilio SMS Webhook
@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming_msg = request.form.get("Body", "")
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

    reply = get_openai_response(incoming_msg)

    vr = VoiceResponse()
    vr.say(reply, voice="alice", language="de-DE")
    vr.listen()  # erlaubt weitere Eingabe
    return str(vr)


# 🧪 Test-Endpoint (für curl)
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    reply = get_openai_response(user_message)
    return jsonify({"reply": reply})


# App starten
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
