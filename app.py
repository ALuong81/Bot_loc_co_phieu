from flask import Flask
import requests
import yfinance as yf
import pandas as pd
import os
import warnings

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

# ================= MARKET FILTER =================

# def market_trend_ok():
#    try:
#        data = yf.download("^VNINDEX", period="60d", progress=False)
#        data["MA20"] = data["Close"].rolling(20).mean()
#        return data["Close"].iloc[-1] > data["MA20"].iloc[-1]
#   except:
#        return False

# ================= SECTOR ROTATION =================

def sector_strength():
    try:
        vn = yf.download("^VNINDEX", period="40d", progress=False)
        vn_return = (vn["Close"].iloc[-1] / vn["Close"].iloc[-20]) - 1

        sectors = {
            "BANKING": "KBE",
            "TECH": "XLK",
            "OIL": "XLE",
            "REAL": "VNQ",
            "FINANCE": "XLF"
        }

        strong = []

        for name, ticker in sectors.items():
            data = yf.download(ticker, period="40d", progress=False)
            ret = (data["Close"].iloc[-1] / data["Close"].iloc[-20]) - 1
            if ret > vn_return:
                strong.append(name)

        return strong
    except:
        return []

# ================= INDICATORS =================

def calculate_indicators(data):
    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["High20"] = data["High"].rolling(20).max()
    data["VolMA20"] = data["Volume"].rolling(20).mean()

    return data

# ================= SCORING =================

def score_stock(data):
    last = data.iloc[-1]
    score = 0

    if last["Close"] > last["MA20"]:
        score += 20

    if last["Close"] >= last["High20"]:
        score += 25

    if last["Close"] > last["MA50"]:
        score += 15

    if last["Volume"] > 1.5 * last["VolMA20"]:
        score += 20

    if last["MA20"] > data["MA20"].iloc[-5]:
        score += 20

    return score

# ================= SCAN STOCK =================

def scan_stock(ticker):
    try:
        data = yf.download(ticker, period="120d", progress=False)
        if len(data) < 60:
            return None

        data = calculate_indicators(data)
        score = score_stock(data)

        if score < 55:
            return None

        last = data.iloc[-1]
        entry = last["High20"] * 1.01
        stop = data["Low"].iloc[-5:].min()
        risk = entry - stop

        if risk <= 0:
            return None

        target = entry + 2 * risk
        rr = (target - entry) / risk

        if rr < 1.8:
            return None

        return {
            "ticker": ticker,
            "score": score,
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "rr": round(rr, 2),
            "price": round(last["Close"], 2)
        }

    except:
        return None

# ================= ROUTES =================

@app.route("/")
def home():
    return "LEVEL 6 - SECTOR ROTATION RUNNING"

@app.route("/scan")
def run_scan():

    try:

#        if not market_trend_ok():
#            return "OK"

        strong_sectors = sector_strength()

        if not strong_sectors:
            return "OK"

        sector_map = {
            "BANKING": ["VCB.HM","CTG.HM","TCB.HM"],
            "TECH": ["FPT.HM", "CMG.HM", "VGI.HN", "CTR.HM"],
            "OIL": ["PVS.HN","GAS.HM", "BSR.HM", "PVD.HN", "OIL.HN"],
            "REAL": ["DIG.HM","DXG.HM","CII.HM", "CEO.HN"],
            "FINANCE": ["SSI.HM","VND.HM", "EVF.HM", "VDS.HM"]
        }

        results = []

        for sector in strong_sectors:
            for stock in sector_map.get(sector, []):
                res = scan_stock(stock)
                if res:
                    res["sector"] = sector
                    results.append(res)

        if results:

            results.sort(key=lambda x: x["score"], reverse=True)
            top = results[:5]

            message = "🔥 <b>NGÀNH DẪN SÓNG</b>\n\n"

            for item in top:
                message += (
                    f"{item['ticker']} ({item['sector']})\n"
                    f"Giá: {item['price']}\n"
                    f"Entry: {item['entry']}\n"
                    f"Stop: {item['stop']}\n"
                    f"RR: {item['rr']}R\n\n"
                )

            send_telegram(message)

    except:
        pass

    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


