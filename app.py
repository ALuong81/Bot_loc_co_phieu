import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask, jsonify
from datetime import datetime
import os
import requests

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SIGNAL_FILE = "signals.csv"

# ======================================
# LOAD WATCHLIST
# ======================================
def load_watchlist():
    try:
        df = pd.read_csv("tickers.csv")
        return df["ticker"].tolist(), dict(zip(df["ticker"], df["sector"]))
    except:
        return [], {}

# ======================================
# TELEGRAM
# ======================================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": msg}
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ======================================
# SAFE DOWNLOAD
# ======================================
def safe_download(ticker):
    try:
        data = yf.download(
            ticker,
            period="1y",
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if data is None or len(data) == 0:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data

    except:
        return None

# ======================================
# INDICATORS
# ======================================
def compute_indicators(df):

    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["High20"] = df["High"].rolling(20).max()
    df["VolMA20"] = df["Volume"].rolling(20).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    mf = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (df["High"] - df["Low"])
    mf = mf.replace([np.inf, -np.inf], 0).fillna(0)
    df["CMF"] = (mf * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()

    return df

# ======================================
# SCORE ENGINE
# ======================================
def score_stock(df):

    last = df.iloc[-1]

    score = 0
    breakout = False
    pullback = False

    if last["MA20"] > last["MA50"]:
        score += 20

    if last["Close"] >= last["High20"]:
        score += 25
        breakout = True

    if last["Close"] > last["MA20"] and last["Close"] < last["High20"]:
        score += 10
        pullback = True

    vol_ratio = last["Volume"] / last["VolMA20"] if last["VolMA20"] > 0 else 0
    if vol_ratio > 1.5:
        score += 15

    if last["CMF"] > 0:
        score += 15

    if 50 < last["RSI"] < 70:
        score += 10

    return score, breakout, pullback, vol_ratio

# ======================================
# SCAN ROUTE (LEVEL PRO)
# ======================================
@app.route("/scan")
def scan():

    tickers, sector_map = load_watchlist()

    if not tickers:
        return jsonify({"error":"tickers.csv missing"})

    today = datetime.now().strftime("%Y-%m-%d")

    ranking = []
    signals = []

    # ======================
    # STEP 1: Ranking all
    # ======================
    for ticker in tickers:

        data = safe_download(ticker)
        if data is None or len(data) < 60:
            continue

        data = compute_indicators(data)
        score, breakout, pullback, vol_ratio = score_stock(data)
        last = data.iloc[-1]

        sector = sector_map.get(ticker, "UNKNOWN")

        avg_value = last["Close"] * last["VolMA20"]

        ranking.append({
            "ticker": ticker,
            "sector": sector,
            "score": score,
            "avg_value": avg_value
        })

    if not ranking:
        return jsonify({"message":"No data from Yahoo"})

    df_rank = pd.DataFrame(ranking)

    # ======================
    # STEP 2: Sector strength
    # ======================
    sector_strength = (
        df_rank.groupby("sector")["score"]
        .mean()
        .reset_index()
        .sort_values("score", ascending=False)
    )

    top_sectors = sector_strength.head(3)["sector"].tolist()

    # ======================
    # STEP 3: Generate signals
    # ======================
    for row in ranking:

        if row["sector"] not in top_sectors:
            continue

        if row["avg_value"] < 3_000_000_000:
            continue

        if row["score"] < 75:
            continue

        ticker = row["ticker"]

        data = safe_download(ticker)
        if data is None:
            continue

        data = compute_indicators(data)
        last = data.iloc[-1]

        entry = last["Close"]
        target = round(entry * 1.12,2)
        stop = round(entry * 0.95,2)

        rr = (target - entry) / (entry - stop)

        if rr < 2:
            continue

        signals.append({
            "date": today,
            "ticker": ticker,
            "sector": row["sector"],
            "price": round(entry,2),
            "score": row["score"],
            "target": target,
            "stop": stop,
            "rr": round(rr,2)
        })

    if signals:
        df = pd.DataFrame(signals)
        df.to_csv(SIGNAL_FILE, index=False)

        msg = "🔥 SWING LEADER PRO\n\n"
        for _, r in df.iterrows():
            msg += f"{r['ticker']} | {r['price']} | Score {r['score']}\n"

        send_telegram(msg)

    return jsonify({
        "tickers_total": len(tickers),
        "top_sectors": top_sectors,
        "signals": len(signals)
    })

# ======================================
# BACKTEST 6 MONTHS
# ======================================
@app.route("/backtest")
def backtest():

    tickers, _ = load_watchlist()

    wins = 0
    total = 0

    for ticker in tickers:

        data = safe_download(ticker)
        if data is None or len(data) < 120:
            continue

        data = compute_indicators(data)

        for i in range(60, len(data)-10):

            sub = data.iloc[:i]
            score, _, _, _ = score_stock(sub)

            if score >= 75:
                entry = data.iloc[i]["Close"]
                future = data.iloc[i:i+10]

                if future["High"].max() >= entry * 1.12:
                    wins += 1
                total += 1

    winrate = round((wins/total)*100,2) if total > 0 else 0

    return jsonify({
        "total_trades": total,
        "wins": wins,
        "winrate_percent": winrate
    })

# ======================================
# BASIC ROUTES
# ======================================
@app.route("/health")
def health():
    return "OK"

@app.route("/")
def home():
    return "Swing Leader PRO Running"

# ======================================
# START
# ======================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
