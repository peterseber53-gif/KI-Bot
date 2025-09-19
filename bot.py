from flask import Flask, request, jsonify
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
import os
import openai
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime

app = Flask(__name__)

# ===== Environment Variables =====
openai.api_key = os.environ.get("OPENAI_API_KEY")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")
credentials = Credentials.from_service_account_info(eval(GOOGLE_CREDS_JSON))
calendar_service = build('calendar', 'v3', credentials=credentials)

# ===== OpenAI Chat Logic =====
def get_ai_response(user_message):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_message}],
        temperature=0.7
    )
    return response['choices'][0]['message']['content']

# ===== Flask Routes =====
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    reply = get_ai_response(user_message)
    return jsonify({"reply": reply})

@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming_msg = request.form.get('Body')
    response_msg = get_ai_response(incoming_msg)
    resp = VoiceResponse()
    resp.say(response_msg)
    return str(resp)

@app.route("/voice", methods=["POST"])
def voice_reply():
    resp = VoiceResponse()
    resp.say("Hallo! Bitte sag mir, für welchen Zweck du einen Termin möchtest.")
    resp.pause(length=1)
    # Hier könntest du später Speech-to-Text einbauen
    return str(resp)

# ===== Google Calendar Helper =====
def create_calendar_event(summary, start_time, end_time):
    event = {
        'summary': summary,
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Europe/Berlin'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Europe/Berlin'},
    }
    event = calendar_service.events().insert(calendarId='primary', body=event).execute()
    return event.get('htmlLink')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
