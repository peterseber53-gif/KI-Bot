# bot.py
import os
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Flask, request
import openai
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# -------- CONFIG --------
app = Flask(__name__)

# OpenAI Key (aus Env)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Twilio number (nur informativ)
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# Timezone for calendar events
LOCAL_TZ = ZoneInfo("Europe/Berlin")

# -------- GOOGLE CALENDAR SETUP (aus ENV, kein Datei-Upload) --------
# Env: GOOGLE_CREDENTIALS_JSON -> komplettes JSON als String
# Env: GOOGLE_CALENDAR_ID -> z. B. "primary"
google_json_text = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not google_json_text:
    raise RuntimeError("Environment variable GOOGLE_CREDENTIALS_JSON fehlt!")

try:
    google_creds_dict = json.loads(google_json_text)
except Exception as e:
    raise RuntimeError("GOOGLE_CREDENTIALS_JSON ist kein gültiges JSON: " + str(e))

SCOPES = ["https://www.googleapis.com/auth/calendar"]
credentials = Credentials.from_service_account_info(google_creds_dict, scopes=SCOPES)
calendar_service = build("calendar", "v3", credentials=credentials)
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# -------- Hilfsfunktionen --------
def parse_datetime_from_text(text: str):
    """
    Versucht einfache Zeitangaben zu erkennen:
    - "heute um 10", "morgen um 14:30", "um 10", "10 Uhr"
    Rückgabe: start_datetime (aware UTC), end_datetime (aware UTC)
    Wenn nichts erkannt: return (None, None)
    """
    t = text.lower()

    today = datetime.now(LOCAL_TZ).date()
    # check "morgen"
    day = today
    if "morgen" in t:
        day = today + timedelta(days=1)
    elif "heute" in t:
        day = today

    # Suche Muster "um HH:MM" oder "um HH" oder "HH:MM" oder "HH Uhr"
    m = re.search(r"um\s+([0-2]?\d)([:\.]?([0-5]\d))?", t)
    if not m:
        m = re.search(r"([0-2]?\d)[:\.]([0-5]\d)", t) or re.search(r"([0-2]?\d)\s*uhr", t)
    if m:
        try:
            hour = int(m.group(1))
            minute = int(m.group(3)) if m.groups() and len(m.groups()) >= 3 and m.group(3) else 0
            # build local datetime
            start_local = datetime(year=day.year, month=day.month, day=day.day,
                                   hour=hour, minute=minute, tzinfo=LOCAL_TZ)
            end_local = start_local + timedelta(minutes=30)
            # convert to UTC isoformat with Z
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
            return start_utc, end_utc
        except Exception:
            return None, None
    return None, None

def create_calendar_event(summary: str, start_dt_utc: datetime, end_dt_utc: datetime, description: str = ""):
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt_utc.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": end_dt_utc.isoformat().replace("+00:00", "Z")},
    }
    created = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return created.get("htmlLink", None)

def ask_openai_text(prompt: str):
    # Einfacher Chat-Call; benutze dein bevorzugtes Modell
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400
    )
    return resp.choices[0].message.content.strip()

# -------- Routes --------
@app.route("/", methods=["GET"])
def home():
    return "KI-Rezeptionist läuft 🚀", 200

# --- SMS / WhatsApp Webhook ---
@app.route("/sms", methods=["POST"])
def sms_webhook():
    incoming = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    resp = MessagingResponse()

    # 1) Wenn Nutzer deutlich Terminwunsch schreibt -> parse & create
    start_utc, end_utc = parse_datetime_from_text(incoming)
    if "termin" in incoming.lower():
        if start_utc is None:
            # fallback: 1 Stunde ab jetzt
            start_local = datetime.now(LOCAL_TZ) + timedelta(hours=1)
            end_local = start_local + timedelta(minutes=30)
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
            schedule_text = "in einer Stunde"
        else:
            schedule_text = start_utc.astimezone(LOCAL_TZ).strftime("%d.%m.%Y %H:%M")
        link = create_calendar_event("Termin (über Bot)", start_utc, end_utc, description=incoming)
        reply = f"✅ Termin eingetragen für {schedule_text}.\nKalender-Link: {link}"
        resp.message(reply)
        return str(resp)

    # 2) Sonst: OpenAI antwortet frei
    ai = ask_openai_text(incoming)
    resp.message(ai)
    return str(resp)

# --- Voice webhook: entry point when Anruf eingeht ---
@app.route("/voice", methods=["POST", "GET"])
def voice_entry():
    """Willkomen, fragt den Anrufer nach seinem Anliegen und sammelt Sprache."""
    vr = VoiceResponse()
    vr.say("Hallo, willkommen beim Terminservice. Bitte sagen Sie kurz, wofür Sie einen Termin möchten und wann.", voice="Polly.Hans", language="de-DE")
    gather = Gather(input="speech", action="/voice/handle", method="POST", timeout=5, speech_timeout="auto")
    gather.say("Sprechen Sie jetzt bitte.", voice="Polly.Hans", language="de-DE")
    vr.append(gather)
    # Falls keine Eingabe:
    vr.say("Ich habe leider nichts gehört. Auf Wiedersehen.", voice="Polly.Hans", language="de-DE")
    vr.hangup()
    return str(vr)

# --- Voice handle: verarbeitet erkannte Sprache (ein Turn) ---
@app.route("/voice/handle", methods=["POST"])
def voice_handle():
    # Twilio liefert 'SpeechResult' (falls speech input erkannt wurde)
    speech = request.values.get("SpeechResult", "").strip()
    vr = VoiceResponse()

    if not speech:
        vr.say("Ich habe leider nichts verstanden. Bitte versuchen Sie es erneut.", voice="Polly.Hans", language="de-DE")
        vr.redirect("/voice")
        return str(vr)

    # 1) Nutze OpenAI zum Verstehen / Antwort generieren
    ai_prompt = f"Du bist eine freundliche Rezeptionshilfe. Der Kunde sagte: {speech}\nAntworte kurz und natürlich auf Deutsch. Wenn der Kunde einen Termin wünscht, schreibe am Ende 'SCHEDULE_EVENT' gefolgt von einer kurzen Zeitangabe falls vorhanden."
    ai_answer = ask_openai_text(ai_prompt)

    # 2) Prüfe, ob OpenAI "SCHEDULE_EVENT" zurückgab (wir instruieren es oben)
    if "SCHEDULE_EVENT" in ai_answer:
        # entferne marker, extrahiere evtl. Datum/Uhrzeit (Text nach Marker)
        parts = ai_answer.split("SCHEDULE_EVENT", 1)
        user_msg = speech  # ursprüngliche Sprache
        # Versuche zu parsen
        start_utc, end_utc = parse_datetime_from_text(user_msg)
        if start_utc is None:
            # fallback 1 Stunde
            start_local = datetime.now(LOCAL_TZ) + timedelta(hours=1)
            end_local = start_local + timedelta(minutes=30)
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
            schedule_text = "in einer Stunde"
        else:
            schedule_text = start_utc.astimezone(LOCAL_TZ).strftime("%d.%m.%Y %H:%M")
        link = create_calendar_event("Telefon-Termin", start_utc, end_utc, description=user_msg)
        vr.say(f"Alles klar. Ich habe den Termin für {schedule_text} eingetragen. Den Link sende ich Ihnen per SMS.", voice="Polly.Hans", language="de-DE")
        # optional: schicke SMS mit Link falls From vorhanden
        from_num = request.values.get("From", "")
        if from_num:
            try:
                # Twilio REST senden (falls Account SID/TOKEN gesetzt) - best effort
                from twilio.rest import Client
                client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
                client.messages.create(body=f"Ihr Termin: {link}", from_=TWILIO_NUMBER, to=from_num)
            except Exception:
                pass
        vr.hangup()
        return str(vr)

    # 3) Sonst: normale AI-Antwort sprechen und Anrufer fragen ob noch etwas
    # Ai_answer könnte contain newline; nur ersten Satz vorlesen
    to_say = ai_answer
    vr.say(to_say, voice="Polly.Hans", language="de-DE")
    # Frage ob weiter Bedarf: gather again
    gather = Gather(input="speech", action="/voice/handle", method="POST", timeout=5, speech_timeout="auto")
    gather.say("Möchten Sie sonst noch etwas? Sagen Sie ja oder nein, oder Ihr Anliegen.", voice="Polly.Hans", language="de-DE")
    vr.append(gather)
    # falls nichts, Auf Wiedersehen
    vr.say("Danke, auf Wiedersehen.", voice="Polly.Hans", language="de-DE")
    vr.hangup()
    return str(vr)

# -------- START --------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
