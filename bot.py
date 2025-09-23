# bot.py - Vollständiger Bot: SMS + Voice + Kalender
from flask import Flask, request, jsonify
import os, json, logging
from datetime import timedelta
import dateparser

# OpenAI new client
from openai import OpenAI

# Twilio responses
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse

# Google Calendar
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ----- OpenAI konfigurieren (neue API-Schnittstelle) -----
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise ValueError("Fehlende OPENAI_API_KEY Umgebungsvariable")
client = OpenAI(api_key=OPENAI_KEY)

# ----- Google Service Account (als JSON in env) -----
creds_json = os.environ.get("GOOGLE_CREDS_JSON")
if not creds_json:
    raise ValueError("Fehlende GOOGLE_CREDS_JSON Umgebungsvariable (JSON-Inhalt hier einfügen)")

# creds_json sollte ein JSON-String sein; lade ihn zu dict
creds_dict = json.loads(creds_json)
credentials = Credentials.from_service_account_info(creds_dict)
calendar_service = build("calendar", "v3", credentials=credentials)

# Kalender-ID (z. B. primary oder spezifische calendar id)
calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
if not calendar_id:
    raise ValueError("Fehlende GOOGLE_CALENDAR_ID Umgebungsvariable")

# ----- Hilfsfunktionen -----
def get_openai_response(user_message):
    """
    Fragt OpenAI (Chat) nach einer freundlichen Antwort.
    Wir nutzen das neue OpenAI-Python-Interface.
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Du bist ein hilfreicher Assistent, der freundlich Termine vereinbart."},
            {"role": "user", "content": user_message}
        ],
        max_tokens=400
    )
    # Inhalt der ersten Wahl zurückgeben
    return resp.choices[0].message.content

def detect_datetime_from_text(text):
    """
    Versucht, ein Datum/Uhrzeit aus dem Text zu parsen.
    Wir bevorzugen zukünftige Daten (z.B. 'morgen um 10').
    """
    settings = {'PREFER_DATES_FROM': 'future', 'RETURN_AS_TIMEZONE_AWARE': False}
    dt = dateparser.parse(text, settings=settings)
    return dt

def create_calendar_event(start_dt, summary="Kundentermin", duration_hours=1):
    """
    Legt ein Event im Google-Kalender an.
    start_dt: datetime-Objekt (naiv, wir setzen Europe/Berlin)
    Gibt den Event-Link zurück oder None.
    """
    if start_dt is None:
        return None
    end_dt = start_dt + timedelta(hours=duration_hours)
    event = {
        "summary": summary,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Berlin"},
    }
    created = calendar_service.events().insert(calendarId=calendar_id, body=event).execute()
    return created.get("htmlLink")

# ----- Endpoints -----

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_message = data.get("message", "")
    reply = get_openai_response(user_message)
    # wenn Datum im user_message erkannt wird, Event erstellen
    dt = detect_datetime_from_text(user_message)
    if dt:
        link = create_calendar_event(dt)
        if link:
            reply += f"\n\n✅ Termin wurde angelegt: {link}"
        else:
            reply += "\n\n⚠️ Konnte Termin nicht anlegen."
    return jsonify({"reply": reply})

@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming = request.form.get("Body", "")
    logging.info("SMS eingehend: %s", incoming)
    reply = get_openai_response(incoming)

    # Datum erkennen und ggf. Event eintragen
    dt = detect_datetime_from_text(incoming)
    if dt:
        link = create_calendar_event(dt)
        if link:
            reply += f"\n\nTermin wurde erstellt: {link}"

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

@app.route("/voice", methods=["POST"])
def voice_reply():
    # Twilio setzt SpeechResult, manchmal Body/Text hängt von Setup ab
    incoming_speech = request.form.get("SpeechResult") or request.form.get("Digits") or request.form.get("Body") or ""
    logging.info("Voice eingehend: %s", incoming_speech)
    if not incoming_speech:
        incoming_speech = "Hallo, ich möchte einen Termin vereinbaren."

    reply = get_openai_response(incoming_speech)

    # Datum erkennen und Event anlegen
    dt = detect_datetime_from_text(incoming_speech)
    if dt:
        link = create_calendar_event(dt)
        if link:
            reply += f" Der Termin wurde eingetragen. Link: {link}"

    vr = VoiceResponse()
    vr.say(reply, voice="alice", language="de-DE")
    # noch ein Gather erlauben, damit Anrufer weiter sprechen kann
    vr.gather(action="/voice", input="speech", language="de-DE", method="POST", timeout=5)
    return str(vr)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
