#        sector_map = {
#            "BANKING": ["VCB.HM","CTG.HM","TCB.HM", "MBB.HM", "VPB.HM", "LPB.HM"],
#            "TECH": ["FPT.HM", "CMG.HM", "VGI.HN", "CTR.HM", "ELC.HM"],
#            "OIL": ["PVS.HN","GAS.HM", "BSR.HM", "PVD.HN", "OIL.HN", "CNG.HM", "PVB.HN", "PVC.HN"],
#            "REAL": ["DIG.HM","DXG.HM","CII.HM", "CEO.HN", "HDC.HM", "CSC.HN", "PDR.HM"],
#            "FINANCE": ["SSI.HM","VND.HM", "EVF.HM", "VDS.HM", "VCI.HM", "VIX.HM", "FTS.HM"]
#        }

from flask import Flask, render_template_string
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

SIGNAL_FILE = "signals.xlsx"

def ensure_signal_file():

    columns = ["date","ticker","sector","price","entry","stop","rr","score"]

    if not os.path.exists(SIGNAL_FILE) or os.path.getsize(SIGNAL_FILE) == 0:
        df = pd.DataFrame(columns=columns)
        df.to_csv(SIGNAL_FILE, index=False)

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
    except Exception as e:
        print("Telegram error:", e)

# ================= SAVE SIGNAL =================

def save_signal(data):

    ensure_signal_file()

    df = pd.DataFrame([data])
    df.to_csv(SIGNAL_FILE, mode='a', header=False, index=False)

# ================= SAFE DOWNLOAD =================

def safe_download(ticker, period="120d"):
    try:
        data = yf.download(ticker, period=period, progress=False)
        if data is None or len(data) == 0:
            return None
        return data
    except:
        return None

# ================= INDICATORS =================

def calculate_indicators(data):
    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["High20"] = data["High"].rolling(20).max()
    data["VolMA20"] = data["Volume"].rolling(20).mean()
    return data

def score_stock(data):
    try:
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
    except:
        return 0

def scan_stock(ticker):
    data = safe_download(ticker)

    if data is None or len(data) < 60:
        return None

    data = calculate_indicators(data)
    score = score_stock(data)

    if score < 30:
        return None

    last = data.iloc[-1]

    entry = last["High20"] * 1.01
    stop = data["Low"].iloc[-5:].min()
    risk = entry - stop

    if risk <= 0:
        return None

    rr = 2

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": ticker,
        "sector": "N/A",
        "price": round(last["Close"], 2),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "rr": rr,
        "score": score
    }

# ================= ROUTES =================

@app.route("/")
def home():
    return "SYSTEM RUNNING"

@app.route("/scan")
def run_scan():

    try:
        watchlist = ["VCB.HM","CTG.HM","TCB.HM", "MBB.HM", "VPB.HM", "LPB.HM", "FPT.HM", "CMG.HM", "VGI.HN", "CTR.HM", "ELC.HM", "PVS.HN","GAS.HM", "BSR.HM", "PVD.HN", "OIL.HN", "CNG.HM", "PVB.HN", "PVC.HN" ,"DIG.HM","DXG.HM","CII.HM", "CEO.HN", "HDC.HM", "CSC.HN", "PDR.HM", "SSI.HM","VND.HM", "EVF.HM", "VDS.HM", "VCI.HM", "VIX.HM", "FTS.HM"]

        results = []

        for stock in watchlist:
            res = scan_stock(stock)
            if res:
                results.append(res)
                save_signal(res)

        if results:
            message = "🔥 SETUP HÔM NAY\n\n"
            for item in results:
                message += f"{item['ticker']} | Score: {item['score']}\n"
            send_telegram(message)

    except Exception as e:
        print("Scan error:", e)

    return "OK"

@app.route("/dashboard")
def dashboard():

    try:

        ensure_signal_file()

        df = pd.read_csv(SIGNAL_FILE)

        if df.empty:
            return "Chưa có tín hiệu nào"

        return df.to_html(index=False)

    except Exception as e:
        return f"Lỗi dashboard: {e}"



