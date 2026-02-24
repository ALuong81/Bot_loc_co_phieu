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

SIGNAL_FILE = "signals.xlsx"
RANKING_FILE = "ranking.xlsx"
SECTOR_FILE = "sector.xlsx"

# ==============================
# LOAD TICKERS + SECTOR MAP
# ==============================
def load_watchlist():
    df = pd.read_csv("tickers.xlsx")
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

    # CMF (20)
    mf = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (df["High"] - df["Low"])
    mf = mf.replace([np.inf, -np.inf], 0).fillna(0)
    df["CMF"] = (mf * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()

    return df

# ==============================
# SCORE ENGINE
# ==============================
def score_stock(df):

    last = df.iloc[-1]

    score = 0
    breakout = False
    pullback = False

    # Trend
    if last["MA20"] > last["MA50"]:
        score += 20

    # Breakout
    if last["Close"] >= last["High20"]:
        score += 25
        breakout = True

    # Pullback strong trend
    if last["Close"] > last["MA20"] and last["Close"] < last["High20"]:
        score += 10
        pullback = True

    # Volume
    vol_ratio = last["Volume"] / last["VolMA20"] if last["VolMA20"] > 0 else 0
    if vol_ratio > 1.5:
        score += 15

    # Money flow
    if last["CMF"] > 0:
        score += 15

    # RSI
    if 50 < last["RSI"] < 70:
        score += 10

    return score, breakout, pullback, vol_ratio

# ==============================
# SAVE FUNCTIONS
# ==============================
def save_append(file, df_new):
    if os.path.exists(file):
        df_old = pd.read_csv(file)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_csv(file, index=False)

# ==============================
# SCAN ROUTE
# ==============================
@app.route("/scan")
def scan():

    tickers, sector_map = load_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")

    ranking_rows = []
    signal_rows = []

    for ticker in tickers:

        try:
            data = yf.download(ticker, period="6mo", progress=False)
            if len(data) < 60:
                continue

            data = compute_indicators(data)
            score, breakout, pullback, vol_ratio = score_stock(data)

            last = data.iloc[-1]
            sector = sector_map.get(ticker, "UNKNOWN")

            ranking_rows.append({
                "date": today,
                "ticker": ticker,
                "sector": sector,
                "price": round(last["Close"],2),
                "score": score,
                "liquidity": int(last["VolMA20"])
            })

            if score >= 60:
                signal_rows.append({
                    "date": today,
                    "ticker": ticker,
                    "sector": sector,
                    "price": round(last["Close"],2),
                    "score": score,
                    "breakout": breakout,
                    "pullback": pullback,
                    "volume_ratio": round(vol_ratio,2),
                    "cmf": round(last["CMF"],2),
                    "rsi": round(last["RSI"],2),
                    "hold_plan": "7-14 days"
                })

        except:
            continue

    # ==================
    # SAVE RANKING
    # ==================
    if ranking_rows:
        df_rank = pd.DataFrame(ranking_rows)
        df_rank = df_rank.sort_values("score", ascending=False)
        df_rank["rank"] = range(1, len(df_rank)+1)
        save_append(RANKING_FILE, df_rank)

    # ==================
    # SAVE SIGNALS
    # ==================
    if signal_rows:
        df_sig = pd.DataFrame(signal_rows)
        save_append(SIGNAL_FILE, df_sig)

        top_msg = df_sig.sort_values("score", ascending=False).head(5)
        text = "🔥 TOP SIGNAL HÔM NAY\n\n"
        for _, row in top_msg.iterrows():
            text += f"{row['ticker']} | Score {row['score']} | {row['price']}\n"

        send_telegram(text)

    # ==================
    # SECTOR ANALYSIS
    # ==================
    if ranking_rows:
        df_sector = pd.DataFrame(ranking_rows)
        sector_summary = df_sector.groupby("sector").agg({
            "score":"mean",
            "ticker":"count"
        }).reset_index()

        sector_summary["date"] = today
        sector_summary.rename(columns={
            "score":"avg_score",
            "ticker":"stocks_count"
        }, inplace=True)

        save_append(SECTOR_FILE, sector_summary)

    return jsonify({
        "scanned": len(tickers),
        "signals": len(signal_rows)
    })

# ==============================
# DASHBOARD
# ==============================
@app.route("/dashboard")
def dashboard():
    if not os.path.exists(RANKING_FILE):
        return "Chưa có dữ liệu"
    df = pd.read_csv(RANKING_FILE)
    return df.sort_values("score", ascending=False).head(20).to_html()

@app.route("/")
def home():
    return "Bot VN Stock Level Pro đang chạy."

# ==============================
# START
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


