#        sector_map = {
#            "BANKING": ["VCB.VN","CTG.VN","TCB.VN", "MBB.VN", "VPB.VN", "LPB.VN"],
#            "TECH": ["FPT.VN", "CMG.VN", "VGI.VN", "CTR.VN", "ELC.VN"],
#            "OIL": ["PVS.VN","GAS.VN", "BSR.VN", "PVD.VN", "OIL.VN", "CNG.VN", "PVB.VN", "PVC.VN"],
#            "REAL": ["DIG.VN","DXG.VN","CII.VN", "CEO.VN", "HDC.VN", "CSC.VN", "PDR.VN"],
#            "FINANCE": ["SSI.VN","VND.VN", "EVF.VN", "VDS.VN", "VCI.VN", "VIX.VN", "FTS.VN"]
#        }

# BOT_TOKEN = "8542992523:AAELdFNjsGb-3Gl8KEOhd17ZH7OPLQTyD8o"
# CHAT_ID = "-5008303605"
import yfinance as yf
import pandas as pd
from flask import Flask, jsonify
from datetime import datetime
import os
import requests

app = Flask(__name__)

SIGNAL_FILE = "signals.xlsx"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# WATCHLIST
# =========================
watchlist = [
    "VCB.VN",
    "FPT.VN",
    "SSI.VN",
    "DIG.VN",
    "CTG.VN"
]

# =========================
# TELEGRAM SEND
# =========================
def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram chưa cấu hình.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)


# =========================
# SAFE DOWNLOAD
# =========================
def safe_download(ticker):
    try:
        data = yf.download(
            ticker,
            period="3mo",
            progress=False,
            auto_adjust=True,
            timeout=10
        )

        if data is None or len(data) == 0:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data

    except:
        return None


# =========================
# SCAN LOGIC
# =========================
def scan_stock(ticker):

    data = safe_download(ticker)

    if data is None or len(data) < 25:
        return None

    data["MA20"] = data["Close"].rolling(20).mean()
    data["High20"] = data["High"].rolling(20).max()
    data["VolMA20"] = data["Volume"].rolling(20).mean()

    last = data.iloc[-1]

    score = 0

    if last["Close"] >= last["High20"]:
        score += 40

    if last["Volume"] > last["VolMA20"]:
        score += 20

    if last["Close"] > last["MA20"]:
        score += 20

    if score < 40:
        return None

    return {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticker": ticker,
        "price": round(last["Close"], 2),
        "score": score
    }


# =========================
# SAVE SIGNAL
# =========================
def save_signals(results):

    if len(results) == 0:
        return

    df_new = pd.DataFrame(results)

    if os.path.exists(SIGNAL_FILE):
        try:
            df_old = pd.read_csv(SIGNAL_FILE, encoding="utf-8")
            df = pd.concat([df_old, df_new], ignore_index=True)
        except:
            df = df_new
    else:
        df = df_new

    df.to_csv(SIGNAL_FILE, index=False, encoding="utf-8")


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "Bot đang chạy + Telegram sẵn sàng."

@app.route("/scan")
def scan():

    results = []

    for ticker in watchlist:
        print("Scanning:", ticker)
        signal = scan_stock(ticker)
        if signal:
            results.append(signal)

            message = f"""
🚀 TÍN HIỆU MỚI

Mã: {signal['ticker']}
Giá: {signal['price']}
Score: {signal['score']}
Thời gian: {signal['date']}
"""
            send_telegram(message)

    save_signals(results)

    return jsonify({
        "scanned": len(watchlist),
        "signals_found": len(results)
    })


@app.route("/dashboard")
def dashboard():

    if not os.path.exists(SIGNAL_FILE):
        return "Chưa có tín hiệu nào"

    try:
        df = pd.read_csv(SIGNAL_FILE, encoding="utf-8")
    except:
        return "Lỗi đọc file"

    if len(df) == 0:
        return "Chưa có tín hiệu nào"

    return df.tail(20).to_html()

@app.route("/test")
def test():
    send_telegram("Bot đã kết nối thành công.")
    return "Đã gửi"
    
# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

