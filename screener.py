import json
import os
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

STATE_FILE = "state.json"
DASHBOARD_FILE = "dashboard_data.json"
ENGINE_VERSION = "2.4"
TODAY_DATE = datetime.now(timezone.utc)
TODAY_STR = TODAY_DATE.strftime("%Y-%m-%d")
SCAN_TS_UTC = TODAY_DATE.isoformat(timespec="seconds")

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

    return sorted(set(sp_tickers + ndx_tickers))

def calc_rs_rating(df_close):
    n = len(df_close)
    if n < 200: return None
    r3m = df_close.iloc[-1] / df_close.iloc[-min(63, n - 1)] - 1
    r12m = df_close.iloc[-1] / df_close.iloc[-min(n - 1, 240)] - 1
    return (r3m * 2 + r12m) / 3

def score_low(value, best, worst, max_points):
    """Return more points when a value is lower."""
    if pd.isna(value) or value >= worst:
        return 0.0
    if value <= best:
        return float(max_points)
    return float(max_points) * (worst - value) / (worst - best)


def score_high(value, worst, best, max_points):
    """Return more points when a value is higher."""
    if pd.isna(value) or value <= worst:
        return 0.0
    if value >= best:
        return float(max_points)
    return float(max_points) * (value - worst) / (best - worst)

def calculate_continuous_score(rvol3, rs_change_20d, setup_type, **kwargs):
    """Calculate a 0-100 setup-quality score.

    RS Rating is deliberately excluded. It is an eligibility gate, not a
    grading input. Score ranges are calibrated to each strategy's gate so a
    strong, realistic candidate can reach S grade without requiring every
    component to be mathematically perfect.
    """
    score = 0

    # 1. Volume Contraction Score (Max 25)
    rvol_ceiling = {
        "20EMA": 1.00,
        "VCP": 0.80,
        "B&R": 0.65,
        "MTF": 1.10,
    }[setup_type]
    score += score_low(rvol3, best=0.55, worst=rvol_ceiling, max_points=25)

    # 2. RS Line Improvement Score (Max 15)
    score += score_high(rs_change_20d, worst=-0.03, best=0.04, max_points=15)

    # 3. Structure & Precision Score (Max 60)
    if setup_type == "20EMA":
        close_loc = kwargs.get('close_loc', 0.5)
        ema_dist = kwargs.get('ema_dist', 0.01)
        score += score_high(close_loc, worst=0.30, best=0.75, max_points=30)
        score += score_low(abs(ema_dist), best=0.005, worst=0.03, max_points=30)
        
    elif setup_type == "VCP":
        range_5d = kwargs.get('range_5d', 0.05)
        pivot_dist = kwargs.get('pivot_dist', 0.05)
        score += score_low(range_5d, best=0.035, worst=0.075, max_points=35)
        score += score_low(pivot_dist, best=0.02, worst=0.10, max_points=25)
        
    elif setup_type == "B&R":
        retest_dist = kwargs.get('retest_dist', 0.02)
        score += score_low(retest_dist, best=0.008, worst=0.04, max_points=60)
        
    elif setup_type == "MTF":
        flag_range = kwargs.get('flag_range', 0.08)
        drawdown = kwargs.get('drawdown_from_high', 0.15)
        max_runup = kwargs.get('max_runup', 0.18)
        ema20_gap = kwargs.get('ema20_gap', 0.0)
        ema50_gap = kwargs.get('ema50_gap', 0.0)

        # MTF structure is multi-dimensional: tightness alone must not decide
        # the entire 60-point structure score.
        score += score_low(flag_range, best=0.06, worst=0.18, max_points=25)
        score += score_low(drawdown, best=0.04, worst=0.15, max_points=15)
        score += score_high(max_runup, worst=0.18, best=0.35, max_points=10)
        score += score_high(ema20_gap, worst=0.00, best=0.04, max_points=5)
        score += score_high(ema50_gap, worst=0.00, best=0.06, max_points=5)
        
    return min(100, int(round(score)))


def grade_from_score(score):
    """Assign grade from composite setup quality, never from RS Rating."""
    if score >= 85:
        return "S"
    if score >= 70:
        return "A"
    if score >= 60:
        return "B"
    return None

def run_lifecycle_screener():
    tickers = get_combined_tickers()
    print(f"📥 총 {len(tickers)}개 종목 및 SPY 데이터 다운로드 중...")
    
    fetch_list = tickers + ["SPY"]
    raw_data = yf.download(
        fetch_list, period="1y", interval="1d", group_by="ticker",
        auto_adjust=True, threads=True, progress=False
    )
    
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

    old_state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as file:
                saved_state = json.load(file)
            old_state = {
                ticker: item for ticker, item in saved_state.items()
                if isinstance(item, dict)
                and item.get("engine_version") == ENGINE_VERSION
            }
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            print(f"⚠️ state.json 로드 실패: {exc}")
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
            rs_rating = round(float(rs_percentile.get(ticker, 0)), 1)

            if pd.isna(avg_dollar_vol_50) or price < 10 or avg_dollar_vol_50 < 50_000_000 or rs_rating < 70:
                continue

            # 3일 평균 RVOL 계산
            vol_3_avg = df["Volume"].tail(3).mean()
            rvol3 = vol_3_avg / df["Vol50Avg"].iloc[-1] if df["Vol50Avg"].iloc[-1] > 0 else 1.0
            prior_vol50_now = float(df["Volume"].shift(1).rolling(50).mean().iloc[-1])
            daily_rvol = float(c["Volume"]) / prior_vol50_now if prior_vol50_now > 0 else 1.0

            # RS Line 상대 개선율 계산
            rs_change_20d = 0.0
            if spy_close is not None:
                aligned_spy = spy_close.reindex(df.index).ffill()
                rs_line = df["Close"] / aligned_spy
                if len(rs_line) > 21:
                    rs_change_20d = (rs_line.iloc[-1] / rs_line.iloc[-21]) - 1.0

            setups = {}
            setup_meta = {}
            trade_levels = {}

            # =================================================================
            # [Gate 2-1] 20EMA Pullback (Ceiling RVOL <= 0.80)
            # =================================================================
            ema20_rising = c["EMA20"] > df["EMA20"].shift(5).iloc[-1]
            ema_dist_low = (c["Low"] / c["EMA20"]) - 1
            
            is_touching = -0.03 <= ema_dist_low <= 0.02
            is_holding = c["Close"] >= c["EMA20"]
            range_today = max(c["High"] - c["Low"], 0.01)
            close_loc = (c["Close"] - c["Low"]) / range_today
            
            if (price > c["SMA50"]) and ema20_rising and is_touching and is_holding and (rvol3 <= 1.00):
                score = calculate_continuous_score(rvol3, rs_change_20d, "20EMA", close_loc=close_loc, ema_dist=ema_dist_low)
                setups["20EMA"] = score
                setup_meta["20EMA"] = {
                    "ema20": round(float(c["EMA20"]), 2),
                    "ema_low_distance_pct": round(float(ema_dist_low) * 100, 2),
                    "close_location_pct": round(float(close_loc) * 100, 1),
                }
                trade_levels["20EMA"] = {
                    "entry_trigger": float(c["High"]) * 1.002,
                    "stop_loss": min(float(c["Low"]), float(c["EMA20"]) * 0.97) * 0.995,
                    "action_rvol_min": 0.90,
                }

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
            is_contracting = (vol_mid <= vol_old * 0.92) and (vol_new <= vol_mid * 0.92)

            range_5d = (df["High"].tail(5).max() - df["Low"].tail(5).min()) / df["Low"].tail(5).min()
            vcp_pivot = df["High"].shift(1).tail(20).max()
            
            # [VCP 버그 수정] 음수 피벗 거리 원천 차단 및 허용 대역 (하방 8%, 돌파 2%)
            pivot_dist = abs(price / vcp_pivot - 1)
            near_pivot = (price >= vcp_pivot * 0.90) and (price <= vcp_pivot * 1.025)

            if (price > c["SMA50"] > c["SMA200"]) and is_contracting and (range_5d <= 0.075) and near_pivot and (rvol3 <= 0.80):
                score = calculate_continuous_score(rvol3, rs_change_20d, "VCP", range_5d=range_5d, pivot_dist=pivot_dist)
                setups["VCP"] = score
                setup_meta["VCP"] = {
                    "range_5d_pct": round(float(range_5d) * 100, 2),
                    "pivot": round(float(vcp_pivot), 2),
                    "pivot_distance_pct": round(float(pivot_dist) * 100, 2),
                }
                trade_levels["VCP"] = {
                    "entry_trigger": float(vcp_pivot) * 1.005,
                    "stop_loss": float(df["Low"].tail(5).min()) * 0.995,
                    "action_rvol_min": 1.20,
                }

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
                setup_meta["B&R"] = {
                    "pivot": round(float(best_br["pivot"]), 2),
                    "breakout_days_ago": int(best_br["days_ago"]),
                }
                trade_levels["B&R"] = {
                    "entry_trigger": float(c["High"]) * 1.002,
                    "stop_loss": float(best_br["pivot"]) * 0.965,
                    "action_rvol_min": 0.90,
                }

            # =================================================================
            # [Gate 2-4] Momentum Tight Flag (MTF)
            # =================================================================
            if rs_rating > 80:
                w = df["Close"].tail(40)
                max_runup = float((w / w.cummin() - 1.0).max())
                
                high_40 = float(df["High"].tail(40).max())
                drawdown_from_high = (high_40 - price) / high_40 if high_40 > 0 else 1.0
                
                high_10 = float(df["High"].tail(10).max())
                low_10 = float(df["Low"].tail(10).min())
                flag_range = (high_10 - low_10) / high_10 if high_10 > 0 else 1.0
                momentum_trend = price > float(c["EMA20"]) > float(c["SMA50"])
                ema20_gap = price / float(c["EMA20"]) - 1.0
                ema50_gap = float(c["EMA20"]) / float(c["SMA50"]) - 1.0
                
                is_mtf_eligible = (
                    rs_rating > 80
                    and max_runup >= 0.18
                    and momentum_trend
                    and flag_range <= 0.18
                    and drawdown_from_high <= 0.15
                    and rvol3 <= 1.10
                )

                if is_mtf_eligible:
                    score = calculate_continuous_score(
                        rvol3,
                        rs_change_20d,
                        "MTF",
                        flag_range=flag_range,
                        drawdown_from_high=drawdown_from_high,
                        max_runup=max_runup,
                        ema20_gap=ema20_gap,
                        ema50_gap=ema50_gap,
                    )
                    setups["MTF"] = score
                    setup_meta["MTF"] = {
                        "max_runup_40d_pct": round(max_runup * 100, 1),
                        "flag_range_10d_pct": round(flag_range * 100, 2),
                        "drawdown_from_40d_high_pct": round(drawdown_from_high * 100, 2),
                        "mtf_rs_threshold": 80,
                    }
                    mtf_pivot = float(df["High"].shift(1).tail(10).max())
                    trade_levels["MTF"] = {
                        "entry_trigger": mtf_pivot * 1.005,
                        "stop_loss": max(low_10 * 0.995, float(c["EMA20"]) * 0.97),
                        "action_rvol_min": 1.20,
                    }

            # =================================================================
            # [Gate 3] Lifecycle & TTL State Management
            # =================================================================
            prev_info = old_state.get(ticker, {})
            prev_status = prev_info.get("state", "none")
            item_data = {}
            current_setup = {}

            if setups:
                primary_strategy = max(setups, key=setups.get)
                primary_score = setups[primary_strategy]
                grade = grade_from_score(primary_score)

                if grade is not None:
                    levels = trade_levels[primary_strategy]
                    current_setup = {
                        "state": "setup",
                        "strategy": primary_strategy,
                        "score": primary_score,
                        "grade": grade,
                        "setups": setups,
                        "setup_meta": setup_meta,
                        "msg": f"[{primary_strategy}] 셋업 구조 형성",
                        "last_seen": TODAY_STR,
                        "signal_date": pd.Timestamp(df.index[-1]).strftime("%Y-%m-%d"),
                        "entry_trigger": round(levels["entry_trigger"], 2),
                        "stop_loss": round(levels["stop_loss"], 2),
                        "sl": round(levels["stop_loss"], 2),
                        "action_rvol_min": levels["action_rvol_min"],
                        "engine_version": ENGINE_VERSION,
                    }

            def state_age(date_key, default=999):
                try:
                    saved_date = datetime.strptime(
                        prev_info.get(date_key, ""), "%Y-%m-%d"
                    ).date()
                    return (TODAY_DATE.date() - saved_date).days
                except (TypeError, ValueError):
                    return default

            def failed_item(source, reason):
                failed = dict(source)
                failed.update({
                    "state": "failed",
                    "failed_date": TODAY_STR,
                    "msg": reason,
                })
                return failed

            # Existing Action/Working positions are monitored before looking
            # for a fresh setup. An intraday stop breach invalidates the state.
            if prev_status in ("action", "working"):
                prev_stop = float(prev_info.get("stop_loss", prev_info.get("sl", 0)) or 0)
                if prev_stop > 0 and float(c["Low"]) <= prev_stop:
                    item_data = failed_item(prev_info, "구조 손절가 이탈")
                elif prev_status == "action":
                    trigger = float(prev_info.get("entry_trigger", price) or price)
                    if state_age("action_date") > 2 or price > trigger * 1.05:
                        item_data = dict(prev_info)
                        item_data.update({
                            "state": "working",
                            "msg": f"[{prev_info.get('strategy', '')}] 진입 구간 통과 · 추세 진행",
                        })
                    else:
                        item_data = dict(prev_info)
                else:
                    item_data = dict(prev_info)

            elif prev_status == "failed":
                if state_age("failed_date") <= 3:
                    item_data = dict(prev_info)

            else:
                # A saved S/A setup becomes Action when price closes above its
                # trigger with strategy-specific daily volume confirmation.
                source_setup = prev_info if prev_status == "setup" else current_setup
                source_grade = source_setup.get("grade")
                trigger = float(source_setup.get("entry_trigger", 0) or 0)
                stop = float(source_setup.get("stop_loss", source_setup.get("sl", 0)) or 0)
                min_rvol = float(source_setup.get("action_rvol_min", 99) or 99)

                if stop > 0 and float(c["Low"]) <= stop and prev_status == "setup":
                    item_data = failed_item(source_setup, "셋업 구조 손절가 이탈")
                elif (
                    source_grade in ("S", "A")
                    and trigger > 0
                    and price >= trigger
                    and daily_rvol >= min_rvol
                ):
                    item_data = dict(source_setup)
                    item_data.update({
                        "state": "action",
                        "action_date": TODAY_STR,
                        "triggered_price": round(price, 2),
                        "daily_rvol": round(daily_rvol, 2),
                        "sl": round(stop, 2),
                        "msg": (
                            f"[{source_setup.get('strategy', '')}] 진입 트리거 돌파 "
                            f"· 일간 RVOL {daily_rvol:.2f}"
                        ),
                    })
                elif current_setup:
                    item_data = current_setup
                elif prev_status == "setup" and state_age("last_seen") <= 2:
                    item_data = dict(prev_info)

            if item_data:
                try:
                    mcap_raw = yf.Ticker(ticker).fast_info.get("marketCap", 0)
                    mcap_b = round(mcap_raw / 1_000_000_000, 2)
                except: mcap_b = 0
                
                item_data.update({
                    "symbol": ticker, "price": price, "rvol": round(rvol3, 2),
                    "rs_rating": rs_rating, "mcap": mcap_b,
                    "scan_ts_utc": SCAN_TS_UTC,
                    "engine_version": ENGINE_VERSION,
                })
                new_state[ticker] = item_data
                dashboard_output.append(item_data)
                
        except Exception as e:
            print(f"❌ {ticker} 처리 중 에러 발생: {type(e).__name__}: {e}")
            continue

    grade_counts = {
        grade: sum(item.get("grade") == grade for item in dashboard_output)
        for grade in ("S", "A", "B")
    }
    strategy_counts = {
        strategy: sum(item.get("strategy") == strategy for item in dashboard_output)
        for strategy in ("20EMA", "VCP", "B&R", "MTF")
    }

    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_state, f, indent=4, ensure_ascii=False)
    with open(DASHBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(dashboard_output, f, indent=4, ensure_ascii=False)
    print(f"📊 등급 분포: {grade_counts}")
    print(f"📊 대표 전략 분포: {strategy_counts}")
    print("✅ 최종 3단 퀀트 스크리닝 완료.")

if __name__ == "__main__":
    run_lifecycle_screener()
