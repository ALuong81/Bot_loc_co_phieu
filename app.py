import yfinance as yf
import pandas as pd
import numpy as np
import sqlite3
from flask import Flask, jsonify
from datetime import datetime
import os
import requests
import logging

app = Flask(__name__)

# ==============================
# CONFIG
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
DB_FILE = "database.db"

logging.basicConfig(level=logging.INFO)

# ==============================
# DATABASE INIT
# ==============================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS ranking (
        date TEXT,
        ticker TEXT,
        sector TEXT,
        price REAL,
        score INTEGER,
        rank INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        date TEXT,
        ticker TEXT,
        sector TEXT,
        price REAL,
        score INTEGER,
        tier TEXT
    )
    """)

    conn.commit()
    conn.close()

# ==============================
# LOAD TICKERS
# tickers.csv phải có:
# ticker,sector
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
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except:
        pass

# ==============================
# INDICATORS
# ==============================
def compute_indicators(df):

    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["High20"] = df["High"].rolling(20).max()
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
    mf = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (df["High"] - df["Low"])
    mf = mf.replace([np.inf, -np.inf], 0).fillna(0)
    df["CMF"] = (mf * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()

    return df

# ==============================
# SCORE
# ==============================
def score_stock(df):

    last = df.iloc[-1]
    score = 0

    if last["MA20"] > last["MA50"]:
        score += 20

    if last["Close"] >= last["High20"]:
        score += 25

    if last["Close"] > last["MA20"] and last["Close"] < last["High20"]:
        score += 10

    vol_ratio = last["Volume"] / last["VolMA20"] if last["VolMA20"] > 0 else 0
    if vol_ratio > 1.5:
        score += 15

    if last["CMF"] > 0:
        score += 15

    if 50 < last["RSI"] < 70:
        score += 10

    return score

def classify(score):
    if score >= 80:
        return "ELITE"
    elif score >= 70:
        return "STRONG"
    elif score >= 60:
        return "BASIC"
    else:
        return "NONE"

# ==============================
# CHUNK BATCH
# ==============================
def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

# ==============================
# SAVE TO DB
# ==============================
def save_ranking(rows):
    conn = sqlite3.connect(DB_FILE)
    df = pd.DataFrame(rows)
    df.to_sql("ranking", conn, if_exists="append", index=False)
    conn.close()

def save_signals(rows):
    conn = sqlite3.connect(DB_FILE)
    df = pd.DataFrame(rows)
    df.to_sql("signals", conn, if_exists="append", index=False)
    conn.close()

# ==============================
# SCAN ROUTE (Cron gọi)
# ==============================
@app.route("/scan")
def scan():

    start_time = datetime.now()
    tickers, sector_map = load_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")

    ranking_rows = []
    signal_rows = []

    for batch in chunk_list(tickers, 30):

        logging.info(f"Downloading batch: {batch}")

        data = yf.download(
            batch,
            period="4mo",
            group_by='ticker',
            progress=False,
            threads=True
        )

        for ticker in batch:
            try:
                df = data[ticker].dropna()

                if len(df) < 60:
                    continue

                df = compute_indicators(df)
                score = score_stock(df)

                last = df.iloc[-1]
                sector = sector_map.get(ticker, "UNKNOWN")
                tier = classify(score)

                ranking_rows.append({
                    "date": today,
                    "ticker": ticker,
                    "sector": sector,
                    "price": round(last["Close"],2),
                    "score": score,
                    "rank": 0
                })

                if score >= 60:
                    signal_rows.append({
                        "date": today,
                        "ticker": ticker,
                        "sector": sector,
                        "price": round(last["Close"],2),
                        "score": score,
                        "tier": tier
                    })

            except:
                continue

    # Sort ranking
    if ranking_rows:
        df_rank = pd.DataFrame(ranking_rows)
        df_rank = df_rank.sort_values("score", ascending=False)
        df_rank["rank"] = range(1, len(df_rank)+1)
        save_ranking(df_rank.to_dict("records"))

    if signal_rows:
        save_signals(signal_rows)

        top5 = sorted(signal_rows, key=lambda x: x["score"], reverse=True)[:5]
        text = "🔥 TOP SIGNAL HÔM NAY\n\n"
        for s in top5:
            text += f"{s['ticker']} | {s['score']} | {s['price']}\n"

        send_telegram(text)

    duration = (datetime.now() - start_time).seconds

    return jsonify({
        "scanned": len(tickers),
        "signals": len(signal_rows),
        "time_seconds": duration
    })

# ==============================
# DASHBOARD
# ==============================
@app.route("/dashboard")
def dashboard():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM ranking ORDER BY score DESC LIMIT 20", conn)
    conn.close()
    return df.to_html()

# ==============================
# HEALTH
# ==============================
@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/")
def home():
    init_db()
    return "VN Stock System Stable Running"

# ==============================
# START
# ==============================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
