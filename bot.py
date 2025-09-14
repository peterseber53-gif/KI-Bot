from flask import Flask, request, jsonify
import os
import openai

app = Flask(__name__)

# OpenAI-Key aus Render-Umgebungsvariablen laden
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/")
def home():
    return "KI-Bot läuft 🚀"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"error": "Keine Nachricht erhalten"}), 400

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",  # falls kein Zugriff, nimm "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher KI-Assistent."},
                {"role": "user", "content": user_message},
            ],
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Render Startpunkt
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
