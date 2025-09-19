import os
import json
from flask import Flask, request, jsonify
from twilio.twiml.voice_response import VoiceResponse, Say, Gather
from twilio.twiml.messaging_response import MessagingResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
import openai
from datetime import datetime
import dateparser  # für flexible Datum/Uhrzeit-Erkennung

app = Flask(__name__)

# ------------------------
# OpenAI Setup
# ------------------------
openai.api_key = os.getenv("OPENAI_API_KEY")

# ------------------------
# Google Calendar Setup
# ------------------------
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")  # JSON als String
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")  # z.B. 'primary'

creds_dict = json.loads(GOOGLE_CREDS_JSON)
credentials = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=credentials)

# ------------------------
# Hilfsfunktionen
# ------------------------
def create_event(summary, start_time, end_time):
    event = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "Europe/Berlin"},
        "end": {"dateTime": end_time, "timeZone": "Europe/Berlin"},
    }
    calendar_service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    return f"Termin '{summary}' wurde für {start_time} bis {end_time} erstellt."

def get_openai_response(message):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": message}]
    )
    return response.choices[0].message.content

def parse_datetime(text):
    dt = dateparser.parse(text, settings={"TIMEZONE": "Europe/Berlin", "RETURN_AS_TIMEZONE_AWARE": True})
    return dt

# ------------------------
# REST Endpoint: Chat
# ------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    reply = get_openai_response(message)
    
    # Prüfen, ob der Benutzer einen Termin erstellt
    if "Termin" in message or "treffen" in message or "Buchung" in message:
        # GPT-4 kann z.B. ein JSON zurückgeben wie {"summary": "...", "start": "...", "end": "..."}
        try:
            event_data = json.loads(reply)
            start = parse_datetime(event_data.get("start"))
            end = parse_datetime(event_data.get("end"))
            create_event(event_data.get("summary"), start.isoformat(), end.isoformat())
            reply += "\nDer Termin wurde eingetragen!"
        except:
            pass

    return jsonify({"reply": reply})

# ------------------------
# Twilio SMS Webhook
# ------------------------
@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming_msg = request.values.get("Body", "")
    reply_text = get_openai_response(incoming_msg)

    # Prüfen, ob Termin erstellt werden soll
    if "Termin" in incoming_msg or "treffen" in incoming_msg or "Buchung" in incoming_msg:
        try:
            event_data = json.loads(reply_text)
            start = parse_datetime(event_data.get("start"))
            end = parse_datetime(event_data.get("end"))
            create_event(event_data.get("summary"), start.isoformat(), end.isoformat())
            reply_text += "\nDer Termin wurde eingetragen!"
        except:
            pass

    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp)

# ------------------------
# Twilio Voice Webhook
# ------------------------
@app.route("/voice", methods=["POST"])
def voice_reply():
    resp = VoiceResponse()
    gather = Gather(input="speech", action="/process-voice", language="de-DE", timeout=5)
    gather.say("Hallo! Ich bin dein Termin-Bot. Sag mir, wann du einen Termin möchtest.", voice="alice")
    resp.append(gather)
    resp.say("Ich habe dich leider nicht verstanden. Bitte versuche es erneut.", voice="alice")
    return str(resp)

@app.route("/process-voice", methods=["POST"])
def process_voice():
    speech_text = request.values.get("SpeechResult", "")
    reply_text = get_openai_response(speech_text)

    # Prüfen, ob Termin erstellt werden soll
    if "Termin" in speech_text or "treffen" in speech_text or "Buchung" in speech_text:
        try:
            event_data = json.loads(reply_text)
            start = parse_datetime(event_data.get("start"))
            end = parse_datetime(event_data.get("end"))
            create_event(event_data.get("summary"), start.isoformat(), end.isoformat())
            reply_text += "\nDer Termin wurde eingetragen!"
        except:
            pass

    resp = VoiceResponse()
    resp.say(reply_text, voice="alice", language="de-DE")
    return str(resp)

# ------------------------
# Main
# ------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
