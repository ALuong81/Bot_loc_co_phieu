#        sector_map = {
#            "BANKING": ["VCB.VN","CTG.VN","TCB.VN", "MBB.VN", "VPB.VN", "LPB.VN"],
#            "TECH": ["FPT.VN", "CMG.VN", "VGI.VN", "CTR.VN", "ELC.VN"],
#            "OIL": ["PVS.VN","GAS.VN", "BSR.VN", "PVD.VN", "OIL.VN", "CNG.VN", "PVB.VN", "PVC.VN"],
#            "REAL": ["DIG.VN","DXG.VN","CII.VN", "CEO.VN", "HDC.VN", "CSC.VN", "PDR.VN"],
#            "FINANCE": ["SSI.VN","VND.VN", "EVF.VN", "VDS.VN", "VCI.VN", "VIX.VN", "FTS.VN"]
#        }

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

SIGNAL_FILE = "signals.csv"

# ================= FILE SAFETY =================

def ensure_signal_file():
    columns = ["date","ticker","sector","price","entry","stop","rr","score"]

    if not os.path.exists(SIGNAL_FILE):
        df = pd.DataFrame(columns=columns)
        df.to_csv(SIGNAL_FILE, index=False, encoding="utf-8")

    elif os.path.getsize(SIGNAL_FILE) == 0:
        df = pd.DataFrame(columns=columns)
        df.to_csv(SIGNAL_FILE, index=False, encoding="utf-8")

# ================= TELEGRAM =================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message
        }
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ================= SAVE SIGNAL =================

def save_signal(data):
    ensure_signal_file()
    df = pd.DataFrame([data])
    df.to_csv(
        SIGNAL_FILE,
        mode='a',
        header=False,
        index=False,
        encoding="utf-8"
    )

# ================= DATA DOWNLOAD =================

def safe_download(ticker):
    try:
        data = yf.download(
            ticker,
            period="3mo",
            progress=False,
            auto_adjust=True
        )

        if data is None or len(data) == 0:
            return None

        # 🔥 BẮT BUỘC FLATTEN COLUMN
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

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
        if last["Volume"] > last["VolMA20"]:
            score += 10
        if last["MA20"] > data["MA20"].iloc[-5]:
            score += 20

        return score
    except:
        return 0

# ================= SCAN =================

def scan_stock(ticker):

    data = safe_download(ticker)

    if data is None or len(data) < 60:
        return None

    data = calculate_indicators(data)
    score = score_stock(data)

    # giảm điều kiện để test dễ có tín hiệu
    if score < 40:
        return None

    last = data.iloc[-1]

    entry = last["High20"] * 1.01
    stop = data["Low"].iloc[-5:].min()
    risk = entry - stop

    if risk <= 0:
        return None

    rr = round(2,2)

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": ticker,
        "sector": "VN",
        "price": round(last["Close"],2),
        "entry": round(entry,2),
        "stop": round(stop,2),
        "rr": rr,
        "score": score
    }

# ================= ROUTES =================

@app.route("/")
def home():
    return "BOT SYSTEM RUNNING"

@app.route("/scan")
def run_scan():

    try:

        watchlist = ["VCB.VN","CTG.VN","TCB.VN", "MBB.VN", "VPB.VN", "LPB.VN", "FPT.VN", "CMG.VN", "VGI.VN", "CTR.VN", "ELC.VN", "PVS.VN","GAS.VN", "BSR.VN", "PVD.VN", "OIL.VN", "CNG.VN", "PVB.VN", "PVC.VN" ,"DIG.VN","DXG.VN","CII.VN", "CEO.VN", "HDC.VN", "CSC.VN", "PDR.VN", "SSI.VN","VND.VN", "EVF.VN", "VDS.VN", "VCI.VN", "VIX.VN", "FTS.VN"]

        results = []

        for stock in watchlist:
            res = scan_stock(stock)
            if res:
                results.append(res)
                save_signal(res)

        if results:
            message = "SETUP HÔM NAY\n\n"
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

        df = pd.read_csv(SIGNAL_FILE, encoding="utf-8")

        if df.empty:
            return "Chưa có tín hiệu nào"

        return df.to_html(index=False)

    except Exception as e:
        return f"Lỗi dashboard: {e}"

@app.route("/reset")
def reset():
    if os.path.exists(SIGNAL_FILE):
        os.remove(SIGNAL_FILE)
    ensure_signal_file()
    return "Đã reset file tín hiệu"

@app.route("/debug")
def debug():
    data = safe_download("VCB.VN")

    if data is None:
        return "No data"

    return f"Số dòng: {len(data)} | Giá cuối: {data['Close'].iloc[-1]}"

