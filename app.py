import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask, jsonify
from datetime import datetime
import os
import requests
import time

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ==============================
# LOAD WATCHLIST
# ==============================
def load_watchlist():
    df = pd.read_csv("tickers.csv")
    return df["ticker"].tolist(), dict(zip(df["ticker"], df["sector"]))

# ==============================
# TELEGRAM
# ==============================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ==============================
# SAFE DOWNLOAD
# ==============================
def safe_download(ticker):
    try:
        data = yf.download(ticker, period="6mo", progress=False)
        if data is None or len(data) == 0:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data
    except:
        return None

# ==============================
# INDICATORS
# ==============================
def compute_indicators(df):

    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
#   df["High20"] = df["High"].rolling(20).max()
    df["High20"] = df["High"].rolling(20).max().shift(1)
    df["VolMA20"] = df["Volume"].rolling(20).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # CMF
    mf = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (
        df["High"] - df["Low"]
    )
    mf = mf.replace([np.inf, -np.inf], 0).fillna(0)
    df["CMF"] = (mf * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()

    return df

# ==============================
# SCAN ROUTE
# ==============================
@app.route("/scan")
def scan():

    start_time = time.time()

    tickers, sector_map = load_watchlist()

    signals = []
    scanned_valid = 0

    for ticker in tickers:

        data = safe_download(ticker)
        if data is None or len(data) < 60:
            continue

        scanned_valid += 1

        data = compute_indicators(data)
        row = data.iloc[-1]

        # Trend
        if row["MA20"] <= row["MA50"]:
            continue

        # Breakout
        if row["Close"] < row["High20"]:
            continue

        # Volume
        if row["Volume"] <= row["VolMA20"] * 1.3:
            continue

        # Liquidity filter 2 tỷ
        avg_value = row["Close"] * row["VolMA20"]
        if avg_value < 2000000000:
            continue

        signals.append({
            "ticker": ticker,
            "sector": sector_map.get(ticker, "UNKNOWN"),
            "price": round(row["Close"],2)
        })

    # Telegram top signals
    if signals:
        text = "🔥 BREAKOUT LEADER\n\n"
        for s in signals[:5]:
            text += f"{s['ticker']} | {s['price']}\n"
        send_telegram(text)

    return jsonify({
        "tickers_total": len(tickers),
        "scanned_valid": scanned_valid,
        "signals": len(signals),
        "time_seconds": round(time.time() - start_time,2)
    })

# ==============================
# BACKTEST BREAKOUT LEADER
# ==============================
@app.route("/backtest")
def backtest():

    tickers, _ = load_watchlist()

    wins = 0
    losses = 0
    total = 0
    total_rr = 0

    for ticker in tickers:

        data = safe_download(ticker)
        if data is None or len(data) < 150:
            continue

        data = compute_indicators(data)

        for i in range(60, len(data)-30):

            row = data.iloc[i]

            if row["MA20"] <= row["MA50"]:
                continue

            if row["Close"] < row["High20"]:
                continue

            if row["Volume"] <= row["VolMA20"] * 1.3:
                continue

            entry = row["Close"]
            stop = entry * 0.94  # 6% stop

            future = data.iloc[i+1:i+30]

            exit_price = None

            for _, f in future.iterrows():

                # stop loss
                if f["Low"] <= stop:
                    exit_price = stop
                    break

                # trailing MA20
                if f["Close"] < f["MA20"]:
                    exit_price = f["Close"]
                    break

            if exit_price is None:
                exit_price = future.iloc[-1]["Close"]

            rr = (exit_price - entry) / (entry - stop)

            total_rr += rr
            total += 1

            if rr > 0:
                wins += 1
            else:
                losses += 1

    winrate = round((wins/total)*100,2) if total > 0 else 0
    avg_rr = round(total_rr/total,2) if total > 0 else 0

    return jsonify({
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "winrate_percent": winrate,
        "average_rr": avg_rr
    })

# ==============================
# HEALTH CHECK
# ==============================
@app.route("/health")
def health():
    return "OK"

@app.route("/")
def home():
    return "VN Breakout Leader Pro running."

# ==============================
# START
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


