import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

STATE_FILE = "state.json"
DASHBOARD_FILE = "dashboard_data.json"
TODAY_DATE = datetime.now()
TODAY_STR = TODAY_DATE.strftime("%Y-%m-%d")

def get_combined_tickers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        sp_df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", storage_options=headers)[0]
        sp_tickers = sp_df["Symbol"].str.replace(".", "-", regex=False).tolist()
    except Exception as e:
        print(f"⚠️ S&P 500 리스트 로드 실패: {e}")
        sp_tickers = []

    try:
        ndx_tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies", storage_options=headers)
        ndx_df = next(df for df in ndx_tables if "Ticker" in df.columns or "Symbol" in df.columns)
        col_name = "Ticker" if "Ticker" in ndx_df.columns else "Symbol"
        ndx_tickers = ndx_df[col_name].str.replace(".", "-", regex=False).tolist()
    except Exception as e:
        print(f"⚠️ NASDAQ-100 리스트 로드 실패: {e}")
        ndx_tickers = []

    return list(set(sp_tickers + ndx_tickers))

def calc_rs_rating(df_close):
    n = len(df_close)
    if n < 200: return None
    r3m = df_close.iloc[-1] / df_close.iloc[-min(63, n - 1)] - 1
    r12m = df_close.iloc[-1] / df_close.iloc[-min(n - 1, 240)] - 1
    return (r3m * 2 + r12m) / 3

def linear_score(value, best, worst, max_points):
    """연속적 점수화를 위한 선형 보간법 함수"""
    if value <= best: return max_points
    if value >= worst: return 0
    ratio = (value - best) / (worst - best)
    return max_points * (1 - ratio)

def calculate_continuous_score(rvol3, rs_change_20d, setup_type, **kwargs):
    score = 0
    
    # 1. Volume Contraction Score (Max 25)
    vol_score = linear_score(rvol3, best=0.3, worst=1.0, max_points=25)
    score += vol_score
    
    # 2. RS Line Improvement Score (Max 15)
    rs_score_val = linear_score(rs_change_20d, best=0.08, worst=0.0, max_points=15)
    score += rs_score_val
    
    # 3. Structure & Precision Score (Max 60)
    if setup_type == "20EMA":
        close_loc = kwargs.get('close_loc', 0.5)
        ema_dist = kwargs.get('ema_dist', 0.01)
        score += linear_score(close_loc, best=0.8, worst=0.2, max_points=30)
        score += linear_score(abs(ema_dist), best=0.0, worst=0.02, max_points=30)
        
    elif setup_type == "VCP":
        range_5d = kwargs.get('range_5d', 0.05)
        pivot_dist = kwargs.get('pivot_dist', 0.05)
        score += linear_score(range_5d, best=0.02, worst=0.06, max_points=35)
        score += linear_score(pivot_dist, best=0.0, worst=0.05, max_points=25)
        
    elif setup_type == "B&R":
        retest_dist = kwargs.get('retest_dist', 0.02)
        score += linear_score(retest_dist, best=0.0, worst=0.03, max_points=60)
        
    elif setup_type == "MTF":
        flag_range = kwargs.get('flag_range', 0.08)
        score += linear_score(flag_range, best=0.03, worst=0.12, max_points=60)
        
    return min(100, int(score))

def run_lifecycle_screener():
    tickers = get_combined_tickers()
    print(f"📥 총 {len(tickers)}개 종목 및 SPY 데이터 다운로드 중...")
    
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

    print("🔍 3-Stage 퀀트 엔진 스크리닝 시작...")
    for ticker in tickers:
        try:
            if ticker not in raw_data.columns.levels[0]: continue
            df = raw_data[ticker].dropna().copy()
            if len(df) < 230: continue

            # [P0 해결] 지표 먼저 계산 후 현재 candle(c) 생성
            df["Vol50Avg"] = df["Volume"].rolling(50).mean()
            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["SMA50"] = df["Close"].rolling(window=50).mean()
            df["SMA200"] = df["Close"].rolling(window=200).mean()

            c = df.iloc[-1]
            price = float(c["Close"])
            
            # [Gate 1] Hard Eligibility (Price, Dollar Volume, RS >= 70)
            avg_dollar_vol_50 = (df["Close"] * df["Volume"]).rolling(50).mean().iloc[-1]
            rs_score = round(rs_percentile.get(ticker, 0), 1)

            if price < 10 or avg_dollar_vol_50 < 50_000_000 or rs_score < 70:
                continue

            # 3일 평균 RVOL 계산
            vol_3_avg = df["Volume"].tail(3).mean()
            rvol3 = vol_3_avg / df["Vol50Avg"].iloc[-1] if df["Vol50Avg"].iloc[-1] > 0 else 1.0

            # RS Line 상대 개선율 계산
            rs_change_20d = 0.0
            rs_slope_positive = False
            if spy_close is not None:
                aligned_spy = spy_close.reindex(df.index).ffill()
                rs_line = df["Close"] / aligned_spy
                if len(rs_line) > 21:
                    rs_change_20d = (rs_line.iloc[-1] / rs_line.iloc[-21]) - 1.0
                    rs_slope_positive = rs_change_20d > 0

            setups = {}

            # =================================================================
            # [Gate 2-1] 20EMA Pullback (Ceiling RVOL <= 0.80)
            # =================================================================
            ema20_rising = c["EMA20"] > df["EMA20"].shift(5).iloc[-1]
            ema_dist_low = (c["Low"] / c["EMA20"]) - 1
            
            is_touching = -0.02 <= ema_dist_low <= 0.015
            is_holding = c["Close"] >= c["EMA20"]
            range_today = max(c["High"] - c["Low"], 0.01)
            close_loc = (c["Close"] - c["Low"]) / range_today
            
            if (price > c["SMA50"]) and ema20_rising and is_touching and is_holding and (rvol3 <= 0.80):
                score = calculate_continuous_score(rvol3, rs_change_20d, "20EMA", close_loc=close_loc, ema_dist=ema_dist_low)
                setups["20EMA"] = score

            # =================================================================
            # [Gate 2-2] VCP (True Range Contraction + Ceiling RVOL <= 0.65)
            # =================================================================
            prev_close = df["Close"].shift(1)
            tr = pd.concat([
                df["High"] - df["Low"],
                (df["High"] - prev_close).abs(),
                (df["Low"] - prev_close).abs()
            ], axis=1).max(axis=1)
            tr_pct = tr / prev_close

            vol_old = tr_pct.iloc[-20:-10].mean()
            vol_mid = tr_pct.iloc[-10:-5].mean()
            vol_new = tr_pct.iloc[-5:].mean()
            is_contracting = (vol_mid <= vol_old * 0.85) and (vol_new <= vol_mid * 0.85)

            range_5d = (df["High"].tail(5).max() - df["Low"].tail(5).min()) / df["Low"].tail(5).min()
            vcp_pivot = df["High"].shift(1).tail(20).max()
            
            # [VCP 버그 수정] 음수 피벗 거리 원천 차단 및 허용 대역 (하방 8%, 돌파 2%)
            pivot_dist = abs(price / vcp_pivot - 1)
            near_pivot = (price >= vcp_pivot * 0.92) and (price <= vcp_pivot * 1.02)

            if (price > c["SMA50"] > c["SMA200"]) and is_contracting and (range_5d <= 0.06) and near_pivot and (rvol3 <= 0.65):
                score = calculate_continuous_score(rvol3, rs_change_20d, "VCP", range_5d=range_5d, pivot_dist=pivot_dist)
                setups["VCP"] = score

            # =================================================================
            # [Gate 2-3] Breakout & Retest (SMA200 복원 + Low Touch + Ceiling RVOL <= 0.65)
            # =================================================================
            prior_200d_high = df["High"].shift(1).rolling(200).max()
            prior_vol50 = df["Volume"].shift(1).rolling(50).mean()
            
            br_candidates = []
            for i in range(3, 31):
                idx = -i
                pivot = prior_200d_high.iloc[idx]
                if pd.isna(pivot): continue
                
                prev_c = df["Close"].iloc[idx-1]
                day_c = df["Close"].iloc[idx]
                
                if (prev_c <= pivot * 1.01) and (day_c > pivot * 1.015):
                    if df["Volume"].iloc[idx] >= prior_vol50.iloc[idx] * 1.5:
                        peak_since = df["High"].iloc[idx+1:].max()
                        if peak_since >= pivot * 1.04:
                            pullback_from_peak = (peak_since - price) / peak_since
                            if pullback_from_peak >= 0.03:
                                
                                low_retest_dist = abs(c["Low"] / pivot - 1)
                                touching_pivot = (c["Low"] >= pivot * 0.97) and (c["Low"] <= pivot * 1.02)
                                holding_pivot = c["Close"] >= pivot * 0.99
                                
                                if (price > c["SMA200"]) and touching_pivot and holding_pivot and (rvol3 <= 0.65):
                                    score = calculate_continuous_score(rvol3, rs_change_20d, "B&R", retest_dist=low_retest_dist)
                                    br_candidates.append({"score": score, "pivot": pivot, "days_ago": i})
                                    break
            if br_candidates:
                best_br = max(br_candidates, key=lambda x: x["score"])
                setups["B&R"] = best_br["score"]

            # =================================================================
            # [Gate 2-4] Momentum Tight Flag (MTF) (고점 근접도 + Ceiling RVOL <= 0.80)
            # =================================================================
            if rs_score >= 90:
                w = df["Close"].tail(40)
                max_runup = (w / w.cummin() - 1).max()
                
                high_40 = df["High"].tail(40).max()
                drawdown_from_high = (high_40 - price) / high_40
                
                high_10 = df["High"].tail(10).max()
                low_10 = df["Low"].tail(10).min()
                flag_range = (high_10 - low_10) / high_10
                
                if (max_runup >= 0.25) and (price > c["EMA20"] > c["SMA50"]) and (flag_range <= 0.12) and (drawdown_from_high <= 0.10) and (rvol3 <= 0.80):
                    score = calculate_continuous_score(rvol3, rs_change_20d, "MTF", flag_range=flag_range)
                    setups["MTF"] = score

            # =================================================================
            # [Gate 3] Lifecycle & TTL State Management
            # =================================================================
            prev_info = old_state.get(ticker, {})
            prev_status = prev_info.get("state", "none")
            item_data = {}
            
            if prev_status == "failed":
                if (TODAY_DATE - datetime.strptime(prev_info["failed_date"], "%Y-%m-%d")).days <= 3: 
                    item_data = prev_info
            elif prev_status in ["action", "working"]:
                item_data = prev_info 

            elif not setups and prev_status == "setup":
                # [TTL 적용] 셋업이 사라졌을 때 2일 동안은 보존, 이후 말소
                prev_date = datetime.strptime(prev_info.get("last_seen", TODAY_STR), "%Y-%m-%d")
                age = (TODAY_DATE - prev_date).days
                if age <= 2:
                    item_data = prev_info
                else:
                    continue
                
            elif setups:
                primary_strategy = max(setups, key=setups.get)
                primary_score = setups[primary_strategy]
                
                if primary_score >= 85: grade = 'S'
                elif primary_score >= 70: grade = 'A'
                else: grade = 'B'
                
                if grade in ['S', 'A']:
                    item_data = {
                        "state": "setup", 
                        "strategy": primary_strategy, 
                        "score": primary_score,
                        "grade": grade,
                        "setups": setups,
                        "msg": f"[{primary_strategy}] 고순도 구조 형성완료",
                        "last_seen": TODAY_STR
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
                
        except Exception as e:
            print(f"❌ {ticker} 처리 중 에러 발생: {type(e).__name__}: {e}")
            continue

    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_state, f, indent=4, ensure_ascii=False)
    with open(DASHBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(dashboard_output, f, indent=4, ensure_ascii=False)
    print(f"✅ 최종 3단 퀀트 스크리닝 완료.")

if __name__ == "__main__":
    run_lifecycle_screener()
