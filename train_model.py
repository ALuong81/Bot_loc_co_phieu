import pandas as pd
import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

SIGNAL_FILE = "signals.csv"
MODEL_FILE = "model.pkl"

def prepare_data():

    df = pd.read_csv(SIGNAL_FILE)

    if len(df) < 50:
        print("Not enough data to train")
        return None, None

    # Tạo return %
    df["future_return"] = (
        df["future_price"] - df["price"]
    ) / df["price"] * 100

    # Label: win nếu >= 5%
    df["label"] = (df["future_return"] >= 5).astype(int)

    # Feature selection
    features = [
        "rsi",
        "cmf",
        "volume_ratio",
        "breakout",
        "pullback"
    ]

    X = df[features]
    y = df["label"]

    return X, y


def train():

    X, y = prepare_data()

    if X is None:
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)

    print("Accuracy:", round(acc * 100, 2), "%")

    joblib.dump(model, MODEL_FILE)
    print("Model saved as model.pkl")


if __name__ == "__main__":
    train()
