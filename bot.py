import os
import json
from flask import Flask, request, jsonify
from twilio.twiml.voice_response import VoiceResponse, Say
from twilio.twiml.messaging_response import MessagingResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
import openai

app = Flask(__name__)

# ------------------------
# OpenAI Setup
# ------------------------
openai.api_key = os.getenv("OPENAI_API_KEY")

# ------------------------
# Google Calendar Setup
# ------------------------
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")  # komplettes JSON als String
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")  # z.B. primary oder eigene ID

creds_dict = json.loads(GOOGLE_CREDS_JSON)
credentials = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=credentials)

# ------------------------
# Helper Funktionen
# ------------------------
def create_event(summary, start_time, end_time):
    event = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "Europe/Berlin"},
        "end": {"dateTime": end_time, "timeZone": "Europe/Berlin"},
    }
    calendar_service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    return f"Termin '{summary}' wurde erstellt."

def get_openai_response(message):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": message}]
    )
    return response.choices[0].message.content

# ------------------------
# REST Endpoint: Chat
# ------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    reply = get_openai_response(message)
    return jsonify({"reply": reply})

# ------------------------
# Twilio SMS Webhook
# ------------------------
@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming_msg = request.values.get("Body", "")
    reply_text = get_openai_response(incoming_msg)
    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp)

# ------------------------
# Twilio Voice Webhook
# ------------------------
@app.route("/voice", methods=["POST"])
def voice_reply():
    resp = VoiceResponse()
    resp.say("Hallo! Ich bin dein Termin-Bot. Sag mir, wann du einen Termin möchtest.", voice="alice", language="de-DE")
    return str(resp)

# ------------------------
# Main
# ------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
