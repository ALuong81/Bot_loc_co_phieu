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
TRADES_FILE = "trades.csv"
STATE_FILE = "bot_state.csv"

# ===============================
# LOAD WATCHLIST
# ===============================
def load_watchlist():
    df = pd.read_csv("tickers.csv")
    return df["ticker"].tolist(), dict(zip(df["ticker"], df["sector"]))

# ===============================
# TELEGRAM
# ===============================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ===============================
# INDICATORS
# ===============================
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

# ===============================
# SCORE
# ===============================
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

    slope_percent = (df["MA20"].iloc[-1] - df["MA20"].iloc[-5]) / df["MA20"].iloc[-5]
    if slope_percent > 0.015:
        score += 10

    return score, breakout, pullback, vol_ratio

# ===============================
# MARKET REGIME
# ===============================
def detect_market_regime(df_rank):

    market_score = df_rank["score"].mean()

    if market_score > 75:
        return "STRONG_BULL", market_score
    elif 65 < market_score <= 75:
        return "BULL", market_score
    elif 55 < market_score <= 65:
        return "SIDEWAY", market_score
    else:
        return "WEAK", market_score

# ===============================
# ROUTES
# ===============================
@app.route("/scan")
def scan():

    tickers, sector_map = load_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")

    ranking = []
    signals = []

    for ticker in tickers:
        try:
            data = yf.download(ticker, period="6mo", progress=False)
            if len(data) < 60:
                continue

            data = compute_indicators(data)
            score, breakout, pullback, vol_ratio = score_stock(data)

            last = data.iloc[-1]

            ranking.append({
                "ticker": ticker,
                "sector": sector_map.get(ticker,"UNKNOWN"),
                "score": score
            })

        except:
            continue

    if not ranking:
        return jsonify({"message":"No data"})

    df_rank = pd.DataFrame(ranking)
    regime, market_score = detect_market_regime(df_rank)

    if regime == "WEAK":
        return jsonify({"regime":regime})

    for ticker in tickers:

        try:
            data = yf.download(ticker, period="6mo", progress=False)
            if len(data) < 60:
                continue

            data = compute_indicators(data)
            score, breakout, pullback, vol_ratio = score_stock(data)

            if score < 75:
                continue

            last = data.iloc[-1]
            entry = last["Close"]
            target = round(entry * 1.12,2)
            stop = round(entry * 0.95,2)

            rr = (target - entry) / (entry - stop)

            if rr < 2:
                continue

            signals.append({
                "date":today,
                "ticker":ticker,
                "price":round(entry,2),
                "score":score,
                "target":target,
                "stop":stop,
                "rr":round(rr,2),
                "regime":regime
            })

        except:
            continue

    if signals:
        df_sig = pd.DataFrame(signals)
        df_sig.to_csv(SIGNAL_FILE, index=False)

        msg = "🔥 SWING LEADER\n\n"
        for _, row in df_sig.iterrows():
            msg += f"{row['ticker']} | {row['price']} | Score {row['score']}\n"
        send_telegram(msg)

    return jsonify({
        "scanned":len(tickers),
        "signals":len(signals),
        "regime":regime
    })

@app.route("/health")
def health():
    return "OK"

@app.route("/")
def home():
    return "Swing Leader Bot Running"

# ===============================
# START
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
