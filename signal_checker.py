"""
Bollinger + Supertrend + EMA200 - Buy/Sell Signal Checker
Reimplements the TradingView Pine Script indicator logic in Python,
pulls candles from Binance's free public API, and pushes Buy/Sell
alerts to Telegram. Designed to run on a schedule (e.g. GitHub Actions)
once per closed candle.

Matches the Pine Script settings 1:1:
  - Bollinger: length=20, mult=2.0
  - Supertrend: factor=3.0, atrPeriod=10
  - EMA: length=200 (display only, not used in conditions)
  - onlyOncePerTouch = true
  - minBarsSinceFlip = 3
  - showCounterTrend = true
"""

import os
import sys
import requests
import pandas as pd
import numpy as np

# ================= CONFIG (từ biến môi trường / GitHub Secrets) =================
SYMBOLS = [s.strip().upper() for s in os.environ.get("SYMBOLS", "BTCUSDT").split(",") if s.strip()]
INTERVAL = os.environ.get("INTERVAL", "4h")  # phải khớp timeframe bạn dùng trên TradingView
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ================= THAM SỐ INDICATOR (giống hệt Pine Script) =================
BB_LENGTH = 20
BB_MULT = 2.0
ST_FACTOR = 3.0
ST_PERIOD = 10
EMA_LEN = 200
MIN_BARS_SINCE_FLIP = 3
SHOW_COUNTER_TREND = True

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def fetch_klines(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """Lấy nến từ Binance (public endpoint, không cần API key)."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    # Bỏ nến cuối cùng nếu nó chưa đóng (còn đang chạy)
    if df["close_time"].iloc[-1] > pd.Timestamp.utcnow().tz_localize(None):
        df = df.iloc[:-1].reset_index(drop=True)
    return df


def wilder_rma(series: pd.Series, period: int) -> pd.Series:
    """RMA (Wilder smoothing) - giống ta.rma() trong Pine Script, dùng cho ATR."""
    return series.ewm(alpha=1 / period, adjust=False).mean()


def compute_supertrend(df: pd.DataFrame, factor: float, period: int):
    high, low, close = df["high"], df["low"], df["close"]
    hl2 = (high + low) / 2

    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = wilder_rma(tr, period)

    upper_basic = hl2 + factor * atr
    lower_basic = hl2 - factor * atr

    final_upper = upper_basic.copy()
    final_lower = lower_basic.copy()
    direction = pd.Series(index=df.index, dtype=float)
    st_line = pd.Series(index=df.index, dtype=float)

    for i in range(len(df)):
        if i == 0:
            direction.iloc[i] = 1  # mặc định downtrend ở nến đầu
            final_upper.iloc[i] = upper_basic.iloc[i]
            final_lower.iloc[i] = lower_basic.iloc[i]
            st_line.iloc[i] = final_upper.iloc[i]
            continue

        # Điều chỉnh final band theo band trước đó
        if upper_basic.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = upper_basic.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if lower_basic.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = lower_basic.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        prev_dir = direction.iloc[i - 1]
        if prev_dir == 1:  # đang downtrend
            direction.iloc[i] = -1 if close.iloc[i] > final_upper.iloc[i] else 1
        else:  # đang uptrend
            direction.iloc[i] = 1 if close.iloc[i] < final_lower.iloc[i] else -1

        st_line.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == -1 else final_upper.iloc[i]

    # Quy ước giống Pine: dir < 0 = uptrend, dir > 0 = downtrend
    return st_line, direction


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    basis = df["close"].rolling(BB_LENGTH).mean()
    dev = BB_MULT * df["close"].rolling(BB_LENGTH).std(ddof=0)
    df["upper"] = basis + dev
    df["lower"] = basis - dev

    df["ema200"] = df["close"].ewm(span=EMA_LEN, adjust=False).mean()

    st_line, st_dir = compute_supertrend(df, ST_FACTOR, ST_PERIOD)
    df["st_line"] = st_line
    df["st_dir"] = st_dir

    df["is_uptrend"] = df["st_dir"] < 0
    df["is_downtrend"] = df["st_dir"] > 0

    flip = df["st_dir"] != df["st_dir"].shift(1)
    bars_since_flip = pd.Series(np.nan, index=df.index)
    count = 0
    for i in range(len(df)):
        if i == 0 or flip.iloc[i]:
            count = 0
        else:
            count += 1
        bars_since_flip.iloc[i] = count
    df["bars_since_flip"] = bars_since_flip
    df["trend_stable"] = df["bars_since_flip"] >= MIN_BARS_SINCE_FLIP

    df["touch_lower"] = (df["low"] <= df["lower"]) & (df["close"] > df["lower"])
    df["touch_upper"] = (df["high"] >= df["upper"]) & (df["close"] < df["upper"])

    buy_cond = df["is_uptrend"] & df["trend_stable"] & df["touch_lower"]
    sell_cond = df["is_downtrend"] & df["trend_stable"] & df["touch_upper"]
    df["buy_signal"] = buy_cond & ~buy_cond.shift(1, fill_value=False)
    df["sell_signal"] = sell_cond & ~sell_cond.shift(1, fill_value=False)

    counter_buy_cond = df["is_downtrend"] & df["trend_stable"] & df["touch_lower"]
    counter_sell_cond = df["is_uptrend"] & df["trend_stable"] & df["touch_upper"]
    df["counter_buy_signal"] = counter_buy_cond & ~counter_buy_cond.shift(1, fill_value=False)
    df["counter_sell_signal"] = counter_sell_cond & ~counter_sell_cond.shift(1, fill_value=False)

    return df


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }, timeout=15)
    if not resp.ok:
        print(f"Loi gui Telegram: {resp.status_code} {resp.text}", file=sys.stderr)


def check_symbol(symbol: str):
    df = fetch_klines(symbol, INTERVAL)
    if len(df) < max(BB_LENGTH, ST_PERIOD, EMA_LEN) + MIN_BARS_SINCE_FLIP + 2:
        print(f"[{symbol}] Chua du du lieu de tinh, bo qua.")
        return

    df = compute_signals(df)
    last = df.iloc[-1]
    price = last["close"]
    ts = last["open_time"]

    if last["buy_signal"]:
        send_telegram(
            f"🟢 <b>BUY</b> {symbol} ({INTERVAL})\n"
            f"Uptrend (Supertrend) + rút râu band dưới\n"
            f"Giá: {price:g} | Nến: {ts} UTC"
        )
        print(f"[{symbol}] BUY signal sent.")

    if last["sell_signal"]:
        send_telegram(
            f"🔴 <b>SELL</b> {symbol} ({INTERVAL})\n"
            f"Downtrend (Supertrend) + rút râu band trên\n"
            f"Giá: {price:g} | Nến: {ts} UTC"
        )
        print(f"[{symbol}] SELL signal sent.")

    if SHOW_COUNTER_TREND and last["counter_buy_signal"]:
        send_telegram(
            f"🟩 <b>BUY*</b> (ngược xu hướng) {symbol} ({INTERVAL})\n"
            f"Downtrend nhưng chạm band dưới - khả năng hồi kỹ thuật\n"
            f"Giá: {price:g} | Nến: {ts} UTC"
        )
        print(f"[{symbol}] Counter-BUY signal sent.")

    if SHOW_COUNTER_TREND and last["counter_sell_signal"]:
        send_telegram(
            f"🟥 <b>SELL*</b> (ngược xu hướng) {symbol} ({INTERVAL})\n"
            f"Uptrend nhưng chạm band trên - khả năng điều chỉnh\n"
            f"Giá: {price:g} | Nến: {ts} UTC"
        )
        print(f"[{symbol}] Counter-SELL signal sent.")

    if not any([last["buy_signal"], last["sell_signal"],
                last["counter_buy_signal"], last["counter_sell_signal"]]):
        print(f"[{symbol}] Khong co tin hieu moi o nen gan nhat ({ts} UTC).")


def main():
    for symbol in SYMBOLS:
        try:
            check_symbol(symbol)
        except Exception as e:
            print(f"[{symbol}] Loi: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
