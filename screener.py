import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

STATE_FILE = "state.json"
DASHBOARD_FILE = "dashboard_data.json"
TODAY_STR = datetime.now().strftime("%Y-%m-%d")
TODAY_DATE = datetime.strptime(TODAY_STR, "%Y-%m-%d")

def get_combined_tickers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    sp_df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", storage_options=headers)[0]
    sp_tickers = sp_df["Symbol"].str.replace(".", "-", regex=False).tolist()
    ndx_tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies", storage_options=headers)
    ndx_df = next(df for df in ndx_tables if "Ticker" in df.columns or "Symbol" in df.columns)
    col_name = "Ticker" if "Ticker" in ndx_df.columns else "Symbol"
    ndx_tickers = ndx_df[col_name].str.replace(".", "-", regex=False).tolist()
    return list(set(sp_tickers + ndx_tickers))

def calc_rs_rating(df_close):
    n = len(df_close)
    if n < 200: return None
    r3m = df_close.iloc[-1] / df_close.iloc[-min(63, n - 1)] - 1
    r12m = df_close.iloc[-1] / df_close.iloc[-min(n - 1, 240)] - 1
    return (r3m * 2 + r12m) / 3

def run_lifecycle_screener():
    tickers = get_combined_tickers()
    print(f"📥 총 {len(tickers)}개 종목 다운로드 중...")
    
    raw_data = yf.download(tickers, period="1y", interval="1d", group_by="ticker", auto_adjust=True, threads=True)
    
    rs_raw = {}
    for t in tickers:
        try:
            if t in raw_data.columns.levels[0] and len(raw_data[t].dropna()) >= 200:
                rs_raw[t] = calc_rs_rating(raw_data[t]["Close"].dropna())
        except: continue
    rs_series = pd.Series(rs_raw).dropna()
    rs_percentile = rs_series.rank(pct=True) * 99

    old_state = json.load(open(STATE_FILE, 'r', encoding='utf-8')) if os.path.exists(STATE_FILE) else {}
    new_state = {}
    dashboard_output = []

    print("🔍 4-Core 전략 탐색 중 (모바일/필터 최적화)...")
    for ticker in tickers:
        try:
            if ticker not in raw_data.columns.levels[0]: continue
            df = raw_data[ticker].dropna()
            if len(df) < 200: continue

            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["SMA50"] = df["Close"].rolling(window=50).mean()
            df["SMA200"] = df["Close"].rolling(window=200).mean()
            df["Max10"] = df["High"].rolling(10).max()
            df["Min5"] = df["Low"].rolling(5).min()
            df["Vol50Avg"] = df["Volume"].rolling(50).mean()
            
            # 🌟 B&R 업데이트: 52주(200일) 메이저 신고가 돌파-지지 확인
            df["Max200"] = df["High"].rolling(200).max()
            df["PastMajorResist"] = df["Max200"].shift(15) 

            c, p = df.iloc[-1], df.iloc[-2]
            price = round(c["Close"], 2)
            rel_vol = c["Volume"] / c["Vol50Avg"] if c["Vol50Avg"] > 0 else 1.0
            rs_score = round(rs_percentile.get(ticker, 0), 1)

            # 🌟 S/A급 허들 상향 (S=95이상, A=80이상)
            if rs_score >= 95: grade = 'S'
            elif rs_score >= 80: grade = 'A'
            elif rs_score >= 50: grade = 'B'
            else: grade = 'C'

            trend_ok = (price > c["SMA50"]) and (c["SMA50"] > c["SMA200"])
            prev_info = old_state.get(ticker, {})
            prev_status = prev_info.get("state", "none")
            item_data, target_sl = {}, prev_info.get("sl", 0)

            # 상태 머신 처리 (내부 데이터 관리용 - 화면엔 안 보임)
            if prev_status == "failed":
                if (TODAY_DATE - datetime.strptime(prev_info["failed_date"], "%Y-%m-%d")).days <= 3: item_data = prev_info
            elif prev_status in ["action", "working"]:
                entry_price = prev_info.get("entry_price", price)
                if price < target_sl:
                    item_data = prev_info
                    item_data.update({"state": "failed", "failed_date": TODAY_STR})
                else:
                    days_held = (TODAY_DATE - datetime.strptime(prev_info.get("trigger_date", TODAY_STR), "%Y-%m-%d")).days
                    if days_held > 0:
                        ret = round(((price - entry_price) / entry_price) * 100, 2)
                        item_data = prev_info
                        item_data.update({"state": "working", "current_return": ret})
                    else: item_data = prev_info

            # 4-Core 전략 탐색
            elif prev_status in ["setup", "none"]:
                # 1. 20EMA
                ema20_dist = (price - c["EMA20"]) / c["EMA20"]
                is_20ema_setup = trend_ok and (-0.02 <= ema20_dist <= 0.03) and (rel_vol < 0.8)
                is_20ema_trigger = trend_ok and (-0.02 <= ema20_dist <= 0.04) and (price > c["Open"]) and (price > p["Close"]) and (rel_vol >= 1.2)
                
                # 2. VCP
                price_consolidation = (df["High"].tail(5).max() - df["Low"].tail(5).min()) / df["Low"].tail(5).min()
                is_vcp_setup = trend_ok and (price_consolidation < 0.05) and (rel_vol < 0.6)
                is_vcp_trigger = trend_ok and (price > p["Max10"]) and (rel_vol > 1.5)
                
                # 3. B&R (52주 신고가 기준)
                retest_dist = abs(price - c["PastMajorResist"]) / c["PastMajorResist"]
                is_br_setup = trend_ok and (retest_dist < 0.03) and (rel_vol < 0.6)
                is_br_trigger = trend_ok and (retest_dist < 0.04) and (price > c["Open"]) and (price > p["Close"]) and (rel_vol >= 1.0)
                
                # 4. MOMO
                is_strong = rs_score >= 90 and (price / df["Close"].shift(40).iloc[-1] > 1.25)
                is_momo_setup = is_strong and (price > df["Max200"].iloc[-1] * 0.90) and (rel_vol < 0.8)
                is_momo_trigger = is_strong and (price > p["Max10"]) and (rel_vol > 1.5)

                if is_momo_trigger: item_data = {"state": "action", "strategy": "MOMO", "sl": round(c["Min5"], 2), "msg": "플래그 상단 돌파!"}
                elif is_vcp_trigger: item_data = {"state": "action", "strategy": "VCP", "sl": round(c["Min5"], 2), "msg": "VCP 피벗 돌파!"}
                elif is_br_trigger: item_data = {"state": "action", "strategy": "B&R", "sl": round(c["PastMajorResist"] * 0.97, 2), "msg": "52주 신고가 Retest 반등!"}
                elif is_20ema_trigger: item_data = {"state": "action", "strategy": "20EMA", "sl": round(min(c["Low"], p["Low"]) * 0.99, 2), "msg": "20 EMA 지지 양봉 Reclaim!"}
                elif not item_data:
                    if is_momo_setup: item_data = {"state": "setup", "strategy": "MOMO", "msg": "High Tight Flag 돌파 대기"}
                    elif is_vcp_setup: item_data = {"state": "setup", "strategy": "VCP", "msg": "VCP 극비수축 대기"}
                    elif is_br_setup: item_data = {"state": "setup", "strategy": "B&R", "msg": "52주 메이저 저항선 지지력 테스트"}
                    elif is_20ema_setup: item_data = {"state": "setup", "strategy": "20EMA", "msg": "20 EMA 눌림목 대기"}
                    elif prev_status == "setup": item_data = prev_info

            if item_data:
                try:
                    mcap_raw = yf.Ticker(ticker).fast_info.get("marketCap", 0)
                    mcap_b = round(mcap_raw / 1_000_000_000, 2)
                except: mcap_b = 0

                if "entry_price" not in item_data and item_data.get("state") == "action":
                    item_data["entry_price"] = price
                    item_data["trigger_date"] = TODAY_STR
                
                item_data.update({
                    "symbol": ticker, "price": price, "rvol": round(rel_vol, 2),
                    "rs_rating": rs_score, "grade": grade, "mcap": mcap_b
                })
                new_state[ticker] = item_data
                dashboard_output.append(item_data)
                
        except Exception as e: continue

    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_state, f, indent=4, ensure_ascii=False)
    with open(DASHBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(dashboard_output, f, indent=4, ensure_ascii=False)
    print(f"✅ 스크리닝 완료.")

if __name__ == "__main__":
    run_lifecycle_screener()
