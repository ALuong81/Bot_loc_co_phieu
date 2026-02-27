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

SIGNAL_FILE = "signals.csv"
RANKING_FILE = "ranking.csv"
SECTOR_FILE = "sector.csv"

# ==============================
# LOAD TICKERS
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
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except:
        pass

# ==============================
# INDICATORS
# ==============================
def compute_indicators(df):

    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    # BREAKOUT FIX
    df["High20"] = df["High"].rolling(20).max().shift(1)
    df["VolMA20"] = df["Volume"].rolling(20).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    mf = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (
        df["High"] - df["Low"]
    )
    mf = mf.replace([np.inf, -np.inf], 0).fillna(0)

    df["CMF"] = (
        (mf * df["Volume"]).rolling(20).sum()
        / df["Volume"].rolling(20).sum()
    )

    return df

# ==============================
# SCORE
# ==============================
def score_stock(df):

    last = df.iloc[-1]

    score = 0
    breakout = False
    pullback = False

    ma20 = float(last["MA20"]) if not pd.isna(last["MA20"]) else 0
    ma50 = float(last["MA50"]) if not pd.isna(last["MA50"]) else 0
    high20 = float(last["High20"]) if not pd.isna(last["High20"]) else 0
    volma = float(last["VolMA20"]) if not pd.isna(last["VolMA20"]) else 0
    close = float(last["Close"])
    volume = float(last["Volume"])
    cmf = float(last["CMF"]) if not pd.isna(last["CMF"]) else 0
    rsi = float(last["RSI"]) if not pd.isna(last["RSI"]) else 0

    if ma20 > ma50:
        score += 20

    if close >= high20:
        score += 25
        breakout = True

    if close > ma20 and close < high20:
        score += 10
        pullback = True

    vol_ratio = volume / volma if volma > 0 else 0
    if vol_ratio > 1.5:
        score += 15

    if cmf > 0:
        score += 15

    if 50 < rsi < 70:
        score += 10

    return score, breakout, pullback, vol_ratio

# ==============================
# SAVE CSV
# ==============================
def save_append(file, df_new):

    if os.path.exists(file):
        df_old = pd.read_csv(file)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    df.to_csv(file, index=False)

# ==============================
# HEALTH
# ==============================
@app.route("/health")
def health():
    return "OK"

# ==============================
# SCAN
# ==============================
@app.route("/scan")
def scan():

    start_time = time.time()

    tickers, sector_map = load_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")

    # 🔥 Batch download (QUAN TRỌNG)
    try:
        data_all = yf.download(
            tickers,
            period="6mo",
            group_by="ticker",
            threads=True,
            progress=False
        )
    except:
        return jsonify({"message": "Download failed"})

    ranking_rows = []
    signal_rows = []

    scanned_valid = 0

    for ticker in tickers:

        if ticker not in data_all:
            continue

        data = data_all[ticker].dropna()

        if len(data) < 60:
            continue

        scanned_valid += 1

        data = compute_indicators(data)

        score, breakout, pullback, vol_ratio = score_stock(data)

        last = data.iloc[-1]
        sector = sector_map.get(ticker, "UNKNOWN")

        ranking_rows.append({
            "date": today,
            "ticker": ticker,
            "sector": sector,
            "price": round(float(last["Close"]), 2),
            "score": score
        })

        if score >= 60:
            signal_rows.append({
                "date": today,
                "ticker": ticker,
                "sector": sector,
                "price": round(float(last["Close"]), 2),
                "score": score,
                "breakout": breakout,
                "pullback": pullback,
                "volume_ratio": round(vol_ratio,2),
                "cmf": round(float(last["CMF"]),2),
                "rsi": round(float(last["RSI"]),2),
                "hold_plan": "7-14 days"
            })

    # SAVE RANKING
    if ranking_rows:
        df_rank = pd.DataFrame(ranking_rows)
        df_rank = df_rank.sort_values("score", ascending=False)
        df_rank["rank"] = range(1, len(df_rank)+1)
        save_append(RANKING_FILE, df_rank)

    # SAVE SIGNAL
    if signal_rows:
        df_sig = pd.DataFrame(signal_rows)
        save_append(SIGNAL_FILE, df_sig)

        top = df_sig.sort_values("score", ascending=False).head(5)
        msg = "🔥 TOP SIGNAL HÔM NAY\n\n"
        for _, row in top.iterrows():
            msg += f"{row['ticker']} | Score {row['score']} | {row['price']}\n"
        send_telegram(msg)

    elapsed = round(time.time() - start_time, 2)

    return jsonify({
        "tickers_total": len(tickers),
        "scanned_valid": scanned_valid,
        "signals": len(signal_rows),
        "time_seconds": elapsed
    })

# ==============================
# ROOT
# ==============================
@app.route("/")
def home():
    return "VN Stock Scanner Pro Running"

# ==============================
# START
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

