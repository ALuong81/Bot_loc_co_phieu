import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask, jsonify
from datetime import datetime
import os
import requests
import sqlite3
import time

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.db")

# =========================
# INIT DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        date TEXT,
        ticker TEXT,
        sector TEXT,
        price REAL,
        score INTEGER,
        breakout INTEGER,
        pullback INTEGER,
        volume_ratio REAL,
        cmf REAL,
        rsi REAL,
        hold_plan TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ranking (
        date TEXT,
        ticker TEXT,
        sector TEXT,
        price REAL,
        score INTEGER,
        liquidity INTEGER,
        rank INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sector_summary (
        date TEXT,
        sector TEXT,
        avg_score REAL,
        stocks_count INTEGER
    )
    """)

    conn.commit()
    conn.close()

init_db()

# =========================
# LOAD WATCHLIST
# =========================
def load_watchlist():
    df = pd.read_csv("tickers.csv")
    return df["ticker"].tolist(), dict(zip(df["ticker"], df["sector"]))

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except:
        pass

# =========================
# INDICATORS
# =========================
def compute_indicators(df):
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
 
    # BREAKOUT FIX
    df["High20"] = df["High"].rolling(20).max().shift(1)

    df["VolMA20"] = df["Volume"].rolling(20).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + rs))

    mf = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (df["High"] - df["Low"])
    mf = mf.replace([np.inf, -np.inf], 0).fillna(0)
    df["CMF"] = (mf * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()

    return df

# =========================
# SCORE
# =========================
def score_stock(df):
    last = df.iloc[-1]
    score = 0
    breakout = 0
    pullback = 0

    if last["MA20"] > last["MA50"]:
        score += 20

    if last["Close"] >= last["High20"]:
        score += 25
        breakout = 1

    if last["Close"] > last["MA20"] and last["Close"] < last["High20"]:
        score += 10
        pullback = 1

    vol_ratio = last["Volume"] / last["VolMA20"] if last["VolMA20"] > 0 else 0
    if vol_ratio > 1.5:
        score += 15

    if last["CMF"] > 0:
        score += 15

    if 50 < last["RSI"] < 70:
        score += 10

    return score, breakout, pullback, vol_ratio

# =========================
# SCAN
# =========================
@app.route("/scan")
def scan():
    start_time = time.time()
    tickers, sector_map = load_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    valid = 0
    signals_count = 0

    for ticker in tickers:
        try:
            data = yf.download(ticker, period="6mo", progress=False, threads=False)
            if len(data) < 60:
                continue

            valid += 1
            data = compute_indicators(data)
            score, breakout, pullback, vol_ratio = score_stock(data)
            last = data.iloc[-1]
            sector = sector_map.get(ticker, "UNKNOWN")

            # Save ranking
            c.execute("""
            INSERT INTO ranking VALUES (?,?,?,?,?,?,?)
            """, (
                today, ticker, sector,
                float(last["Close"]),
                int(score),
                int(last["VolMA20"]),
                0
            ))

            # Save signal
            if score >= 60:
                signals_count += 1
                c.execute("""
                INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    today, ticker, sector,
                    float(last["Close"]),
                    int(score),
                    breakout,
                    pullback,
                    float(vol_ratio),
                    float(last["CMF"]),
                    float(last["RSI"]),
                    "7-14 days"
                ))

        except Exception as e:
            print("ERROR:", e)
            continue

    conn.commit()
    conn.close()

    return jsonify({
        "tickers_total": len(tickers),
        "scanned_valid": valid,
        "signals": signals_count,
        "time_seconds": round(time.time() - start_time, 2)
    })

# =========================
# BACKTEST
# =========================
@app.route("/backtest")
def backtest():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM signals", conn)
    conn.close()

    if df.empty:
        return jsonify({"message": "No data"})

    wins = 0
    losses = 0

    for _, row in df.iterrows():
        try:
            data = yf.download(row["ticker"], start=row["date"], period="15d", progress=False)
            entry = row["price"]
            max_price = data["High"].max()
            min_price = data["Low"].min()

            if max_price >= entry * 1.05:
                wins += 1
            elif min_price <= entry * 0.97:
                losses += 1

        except:
            continue

    total = wins + losses
    winrate = round(wins / total * 100, 2) if total > 0 else 0

    return jsonify({
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "winrate_percent": winrate
    })

# =========================
# HEALTH
# =========================
@app.route("/health")
def health():
    return "OK"

@app.route("/debug_signals")
def debug_signals():
    import sqlite3
    conn = sqlite3.connect("database.db")
    df = pd.read_sql("SELECT * FROM signals", conn)
    conn.close()
    return jsonify({"rows": len(df)})
@app.route("/")

def home():
    return "Stock Bot SQLite Running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


