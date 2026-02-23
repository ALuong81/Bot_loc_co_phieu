from flask import Flask
import requests
import yfinance as yf
import pandas as pd
import os

app = Flask(__name__)

BOT_TOKEN = "8542992523:AAELdFNjsGb-3Gl8KEOhd17ZH7OPLQTyD8o"
CHAT_ID = "-5008303605"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, json=payload)

def scan_stock(ticker):
    data = yf.download(ticker, period="120d", interval="1d", progress=False)
    if len(data) < 50:
        return

    data["MA20"] = data["Close"].rolling(20).mean()

    last_close = data["Close"].iloc[-1]
    last_ma20 = data["MA20"].iloc[-1]
    prev_close = data["Close"].iloc[-2]
    prev_ma20 = data["MA20"].iloc[-2]

    if prev_close < prev_ma20 and last_close > last_ma20:
        message = f"🚀 {ticker}\nGiá: {round(last_close,2)}\nTín hiệu: Cắt lên MA20"
        send_telegram(message)

@app.route("/")
def home():
    return "Bot is running"

@app.route("/scan")
def run_scan():

    watchlist = [
        "HPG.HM","VCB.HM","FPT.HM","MWG.HM",
        "SSI.HM","VND.HM","DIG.HM","DXG.HM",
        "SHS.HN","PVS.HN","DGC.HM","CTG.HM"
    ]

    count = 0

    for stock in watchlist:
        res = scan_stock(stock)
        if res:
            count += 1

    return f"OK - {count} signals"
   
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


