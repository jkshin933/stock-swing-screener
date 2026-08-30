import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

STATE_FILE = "state.json"
DASHBOARD_FILE = "dashboard_data.json"
TODAY_STR = datetime.now().strftime("%Y-%m-%d")

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

def calculate_continuous_score(rvol3, rs_slope_pos, setup_type, **kwargs):
    """0~100점 연속 스코어링 엔진"""
    score = 0
    
    # 1. Volume Contraction (Max 25)
    if rvol3 <= 0.4: score += 25
    elif rvol3 <= 0.6: score += 18
    elif rvol3 <= 0.8: score += 10
    elif rvol3 <= 1.0: score += 5
    
    # 2. RS Trend (Max 15)
    if rs_slope_pos: score += 15
    
    # 3. Structure & Precision (Max 60)
    if setup_type == "20EMA":
        close_loc = kwargs.get('close_loc', 0)
        ema_dist = kwargs.get('ema_dist', 0.05)
        
        # 캔들 마감 위치 (Max 30)
        if close_loc >= 0.7: score += 30
        elif close_loc >= 0.5: score += 20
        
        # EMA 근접도 (Max 30)
        score += max(0, 30 - (abs(ema_dist) * 100 * 10)) # 0%오차=30점, 1.5%오차=15점
        
    elif setup_type == "VCP":
        range_5d = kwargs.get('range_5d', 0.1)
        pivot_prox = kwargs.get('pivot_prox', 0.1)
        
        # 5일 압축 강도 (Max 35)
        score += max(0, 35 - (range_5d * 100 * 5)) # 2%=25점, 5%=10점
        
        # 피벗 근접도 (Max 25)
        score += max(0, 25 - (pivot_prox * 100 * 3)) # 1%=22점, 5%=10점
        
    elif setup_type == "B&R":
        retest_dist = kwargs.get('retest_dist', 0.1)
        # 피벗 정확도 (Max 60): 0%=60점, 1%=40점, 2%=20점
        score += max(0, 60 - (retest_dist * 100 * 20))
        
    elif setup_type == "MTF":
        flag_range = kwargs.get('flag_range', 0.2)
        # 플래그 압축 강도 (Max 60): 3%=60점, 8%=35점, 12%=15점
        score += max(0, 60 - (flag_range * 100 * 5))
        
    return min(100, int(score))

def run_lifecycle_screener():
    tickers = get_combined_tickers()
    print(f"📥 다운로드 중... (SPY 포함)")
    
    # SPY를 포함하여 다운로드 (RS Line 계산용)
    fetch_list = tickers + ["SPY"]
    raw_data = yf.download(fetch_list, period="1y", interval="1d", group_by="ticker", auto_adjust=True, threads=True)
    
    try:
        spy_close = raw_data["SPY"]["Close"].dropna()
    except:
        spy_close = None

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

    print("🔍 3-Stage Engine 탐색 중...")
    for ticker in tickers:
        try:
            if ticker not in raw_data.columns.levels[0]: continue
            df = raw_data[ticker].dropna()
            if len(df) < 200: continue

            c = df.iloc[-1]
            price = round(c["Close"], 2)
            
            # [Gate 1] Foundation: Price & Dollar Volume
            df["Vol50Avg"] = df["Volume"].rolling(50).mean()
            avg_dollar_vol_50 = (df["Close"] * df["Volume"]).rolling(50).mean().iloc[-1]
            rs_score = round(rs_percentile.get(ticker, 0), 1)

            if price < 10 or avg_dollar_vol_50 < 50_000_000 or rs_score < 70:
                continue

            # 지표 계산
            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["SMA50"] = df["Close"].rolling(window=50).mean()
            df["SMA200"] = df["Close"].rolling(window=200).mean()
            
            # RVOL (3일 평균)
            vol_3_avg = df["Volume"].tail(3).mean()
            rvol3 = vol_3_avg / df["Vol50Avg"].iloc[-1] if df["Vol50Avg"].iloc[-1] > 0 else 1.0
            
            # RS Line Trend (20일 전 대비 향상 여부)
            rs_slope_positive = False
            if spy_close is not None:
                aligned_spy = spy_close.reindex(df.index).ffill()
                rs_line = df["Close"] / aligned_spy
                if len(rs_line) > 21:
                    rs_slope_positive = rs_line.iloc[-1] > rs_line.iloc[-21]

            setups = {}

            # =================================================================
            # [Gate 2] 20EMA Pullback (Touch & Hold)
            # =================================================================
            ema20_rising = c["EMA20"] > df["EMA20"].shift(5).iloc[-1]
            ema_dist_low = (c["Low"] / c["EMA20"]) - 1
            
            is_touching = -0.02 <= ema_dist_low <= 0.015
            is_holding = c["Close"] >= c["EMA20"]
            
            range_today = max(c["High"] - c["Low"], 0.01)
            close_loc = (c["Close"] - c["Low"]) / range_today
            
            if (price > c["SMA50"]) and ema20_rising and is_touching and is_holding:
                setups["20EMA"] = calculate_continuous_score(rvol3, rs_slope_positive, "20EMA", close_loc=close_loc, ema_dist=ema_dist_low)

            # =================================================================
            # [Gate 2] VCP (Disjoint Volatility Contraction)
            # =================================================================
            atr_pct = (df["High"] - df["Low"]) / df["Close"].shift(1)
            vol_old = atr_pct.iloc[-20:-10].mean()
            vol_mid = atr_pct.iloc[-10:-5].mean()
            vol_new = atr_pct.iloc[-5:].mean()
            
            is_contracting = (vol_old > vol_mid) and (vol_mid > vol_new)
            range_5d = (df["High"].tail(5).max() - df["Low"].tail(5).min()) / df["Low"].tail(5).min()
            
            # 피벗 (오늘 제외 과거 20일)
            vcp_pivot = df["High"].shift(1).tail(20).max()
            pivot_prox = (vcp_pivot - price) / price
            
            if (price > c["SMA50"] > c["SMA200"]) and is_contracting and (range_5d <= 0.06) and (pivot_prox <= 0.08):
                setups["VCP"] = calculate_continuous_score(rvol3, rs_slope_positive, "VCP", range_5d=range_5d, pivot_prox=pivot_prox)

            # =================================================================
            # [Gate 2] Breakout & Retest (Frozen Pivot + Pullback Sequence)
            # =================================================================
            prior_200d_high = df["High"].shift(1).rolling(200).max()
            prior_vol50 = df["Volume"].shift(1).rolling(50).mean()
            
            for i in range(3, 31):
                idx = -i
                pivot = prior_200d_high.iloc[idx]
                if pd.isna(pivot): continue
                
                prev_close = df["Close"].iloc[idx-1]
                day_close = df["Close"].iloc[idx]
                
                # Fresh Breakout Cross
                if (prev_close <= pivot * 1.01) and (day_close > pivot * 1.015):
                    day_vol = df["Volume"].iloc[idx]
                    if day_vol >= prior_vol50.iloc[idx] * 1.5:
                        
                        # Peak Formation & Pullback Check
                        peak_since = df["High"].iloc[idx+1:].max()
                        if peak_since >= pivot * 1.04:
                            pullback_from_peak = (peak_since - price) / peak_since
                            if pullback_from_peak >= 0.03:
                                
                                # Retest Evaluation (Today)
                                retest_dist = abs(price / pivot - 1)
                                if retest_dist <= 0.035 and c["Close"] >= pivot * 0.985:
                                    setups["B&R"] = calculate_continuous_score(rvol3, rs_slope_positive, "B&R", retest_dist=retest_dist)
                                break

            # =================================================================
            # [Gate 2] Momentum Tight Flag (MTF)
            # =================================================================
            if rs_score >= 90:
                w = df["Close"].tail(40)
                max_runup = (w / w.cummin() - 1).max()
                
                high_10 = df["High"].tail(10).max()
                low_10 = df["Low"].tail(10).min()
                flag_range = (high_10 - low_10) / high_10
                
                if (max_runup >= 0.25) and (price > c["EMA20"] > c["SMA50"]) and (flag_range <= 0.12):
                    setups["MTF"] = calculate_continuous_score(rvol3, rs_slope_positive, "MTF", flag_range=flag_range)

            # =================================================================
            # [Gate 3] State Assignment & JSON Formatting
            # =================================================================
            prev_info = old_state.get(ticker, {})
            prev_status = prev_info.get("state", "none")
            item_data = {}
            
            if prev_status == "failed":
                if (TODAY_DATE - datetime.strptime(prev_info["failed_date"], "%Y-%m-%d")).days <= 3: item_data = prev_info
            elif prev_status in ["action", "working"]:
                item_data = prev_info # 단순화: Action 이후 로직은 유지 관리 모드

            elif not setups and prev_status == "setup":
                item_data = prev_info # 기존 대기 종목 유지
                
            elif setups:
                # 가장 점수가 높은 전략을 Primary로 선정
                primary_strategy = max(setups, key=setups.get)
                primary_score = setups[primary_strategy]
                
                if primary_score >= 85: grade = 'S'
                elif primary_score >= 70: grade = 'A'
                else: grade = 'B'
                
                # B급 미만은 신규 진입 배제
                if grade in ['S', 'A']:
                    msg = f"[{primary_strategy}] 핵심 타점 도달"
                    item_data = {
                        "state": "setup", 
                        "strategy": primary_strategy, 
                        "score": primary_score,
                        "grade": grade,
                        "setups": setups,
                        "msg": msg
                    }

            if item_data:
                try:
                    mcap_raw = yf.Ticker(ticker).fast_info.get("marketCap", 0)
                    mcap_b = round(mcap_raw / 1_000_000_000, 2)
                except: mcap_b = 0
                
                item_data.update({
                    "symbol": ticker, "price": price, "rvol": round(rvol3, 2),
                    "rs_rating": rs_score, "mcap": mcap_b
                })
                new_state[ticker] = item_data
                dashboard_output.append(item_data)
                
        except Exception as e: continue

    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_state, f, indent=4, ensure_ascii=False)
    with open(DASHBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(dashboard_output, f, indent=4, ensure_ascii=False)
    print(f"✅ 엔진 구동 완료.")

if __name__ == "__main__":
    run_lifecycle_screener()
