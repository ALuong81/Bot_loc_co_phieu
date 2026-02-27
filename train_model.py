from flask import Flask, request
import requests

BOT_TOKEN = 8542992523:AAGS2aWbjz0O1oDRruqg7ABgRQfRcX5iF6Q
CHAT_ID = -5008303605

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    msg = f"""
📊 {data.get('ticker')}
💰 Giá: {data.get('price')}
⏱ {data.get('timeframe')}
📝 {data.get('note')}
"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg
    })

    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
