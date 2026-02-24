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
    "VCB.VN","CTG.VN","TCB.VN","MBB.VN","VPB.VN","LPB.VN",
    "FPT.VN","CMG.VN","VGI.VN","CTR.VN","ELC.VN",
    "SSI.VN","VND.VN","EVF.VN","VDS.VN","VCI.VN","VIX.VN","FTS.VN",
    "DIG.VN","DXG.VN","CII.VN","CEO.VN","HDC.VN","CSC.VN","PDR.VN",
    "PVS.VN","GAS.VN","BSR.VN","PVD.VN","OIL.VN","CNG.VN","PVB.VN","PVC.VN"
]
# =========================
# TELEGRAM
# =========================
def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram chưa cấu hình")
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

        if data is None or len(data) < 30:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data

    except:
        return None

def universe_filter(ticker):

    data = safe_download(ticker)
    if data is None or len(data) < 30:
        return False

    last = data.iloc[-1]
    vol_ma20 = data["Volume"].rolling(20).mean().iloc[-1]

    # Điều kiện lọc sơ cấp
    if last["Close"] < 5:
        return False

    if vol_ma20 < 500000:
        return False

    return True
# =========================
# CHECK DUPLICATE
# =========================
def is_duplicate(ticker):

    if not os.path.exists(SIGNAL_FILE):
        return False

    try:
        df = pd.read_csv(SIGNAL_FILE)
    except:
        return False

    if len(df) == 0:
        return False

    today = datetime.now().strftime("%Y-%m-%d")

    df_today = df[df["date"].str.contains(today)]

    return ticker in df_today["ticker"].values


# =========================
# SCAN LOGIC
# =========================
def scan_stock(ticker):

    data = safe_download(ticker)
    if data is None:
        return None

    if not universe_filter(ticker):
        return None

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

    last = data.iloc[-1]

    score = 0

    if last["Close"] >= last["High20"]:
        score += 30

    if last["Volume"] > 1.5 * last["VolMA20"]:
        score += 20

    if last["Close"] > last["MA20"]:
        score += 15

    if last["MA20"] > last["MA50"]:
        score += 15

    if last["RSI"] > 55:
        score += 10

    if score < 60:
        return None

    if is_duplicate(ticker):
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
            df_old = pd.read_csv(SIGNAL_FILE)
            df = pd.concat([df_old, df_new], ignore_index=True)
        except:
            df = df_new
    else:
        df = df_new

    df.to_csv(SIGNAL_FILE, index=False)


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "Bot đang chạy ổn định."

@app.route("/scan")
def scan():

    results = []

    # Giới hạn mỗi lần scan 80 mã
    limited_list = watchlist[:80]

    for ticker in limited_list:
        signal = scan_stock(ticker)

        if signal:
            results.append(signal)

            message = f"""
🔥 TÍN HIỆU MẠNH

Mã: {signal['ticker']}
Giá: {signal['price']}
Score: {signal['score']}
"""
            send_telegram(message)

    save_signals(results)

    return jsonify({
        "scanned": len(limited_list),
        "signals_found": len(results)
    })
    
@app.route("/dashboard")
def dashboard():

    if not os.path.exists(SIGNAL_FILE):
        return "Chưa có tín hiệu nào"

    try:
        df = pd.read_csv(SIGNAL_FILE)
    except:
        return "Lỗi đọc file"

    if len(df) == 0:
        return "Chưa có tín hiệu nào"

    # Thống kê
    total = len(df)
    best = df.sort_values("score", ascending=False).head(5)

    html = f"""
    <h2>Tổng số tín hiệu: {total}</h2>
    <h3>Top 5 Score cao nhất</h3>
    {best.to_html(index=False)}
    <h3>20 tín hiệu gần nhất</h3>
    {df.tail(20).to_html(index=False)}
    """

    return html


@app.route("/test")
def test():
    send_telegram("Bot đã kết nối thành công.")
    return "Đã gửi test Telegram"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)





