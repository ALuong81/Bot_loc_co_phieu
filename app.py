from flask import Flask
import requests
import yfinance as yf
import pandas as pd
import os
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

app = Flask(__name__)

BOT_TOKEN = "8542992523:AAELdFNjsGb-3Gl8KEOhd17ZH7OPLQTyD8o"
CHAT_ID = "-5008303605"

# ================= TELEGRAM =================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ================= INDICATORS =================

def calculate_indicators(data):
    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["High20"] = data["High"].rolling(20).max()
    data["VolMA20"] = data["Volume"].rolling(20).mean()

    delta = data["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    data["RSI"] = 100 - (100 / (1 + rs))

    ema12 = data["Close"].ewm(span=12, adjust=False).mean()
    ema26 = data["Close"].ewm(span=26, adjust=False).mean()
    data["MACD"] = ema12 - ema26
    data["Signal"] = data["MACD"].ewm(span=9, adjust=False).mean()

    return data

# ================= SCORING =================

def score_stock(data):
    last = data.iloc[-1]
    prev = data.iloc[-2]

    score = 0

    if last["Close"] > last["MA20"]:
        score += 15

    if last["Close"] >= last["High20"]:
        score += 20

    if 55 <= last["RSI"] <= 70:
        score += 15

    if prev["MACD"] < prev["Signal"] and last["MACD"] > last["Signal"]:
        score += 15

    if last["Volume"] > 1.5 * last["VolMA20"]:
        score += 15

    if last["MA20"] > data["MA20"].iloc[-5]:
        score += 10

    if last["Close"] > last["MA50"]:
        score += 10

    return score

# ================= MARKET FILTER =================

def market_trend_ok():
    try:
        data = yf.download("^VNINDEX", period="60d", interval="1d", progress=False)
        if len(data) < 30:
            return False

        data["MA20"] = data["Close"].rolling(20).mean()
        return data["Close"].iloc[-1] > data["MA20"].iloc[-1]
    except:
        return False

# ================= STOCK SCAN =================

def scan_stock(ticker):
    try:
        data = yf.download(ticker, period="120d", interval="1d", progress=False)

        if len(data) < 60:
            return None

        data = calculate_indicators(data)
        score = score_stock(data)

        if score >= 50:
            return (ticker, score)

        return None
    except:
        return None

# ================= ROUTES =================

@app.route("/")
def home():
    return "LEVEL 4 SCANNER RUNNING"

@app.route("/scan")
def run_scan():

    try:

        if not market_trend_ok():
            return "OK"

        watchlist = [
            "HPG.HM","VCB.HM","FPT.HM","MWG.HM",
            "SSI.HM","VND.HM","DIG.HM","DXG.HM",
            "SHS.HN","PVS.HN","DGC.HM","CTG.HM"
        ]

        results = []

        for stock in watchlist:
            res = scan_stock(stock)
            if res:
                results.append(res)

        if results:
            results.sort(key=lambda x: x[1], reverse=True)
            top = results[:5]

            message = "🏆 <b>TOP CỔ PHIẾU MẠNH NHẤT HÔM NAY</b>\n\n"

            for ticker, score in top:
                rank = "B"
                if score >= 65:
                    rank = "A"
                if score >= 80:
                    rank = "A+"

                message += f"{ticker} | {rank} | {score}/100\n"

            send_telegram(message)

    except:
        pass

    return "OK"

# ================= RUN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
