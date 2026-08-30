import os
import json
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


STATE_FILE = "state.json"
DASHBOARD_FILE = "dashboard_data.json"

ENGINE_VERSION = "2.3"

SCAN_TS_UTC = datetime.now(
    timezone.utc
).isoformat(timespec="seconds")


# ============================================================
# UNIVERSE
# ============================================================

def get_combined_tickers():

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    sp_tickers = []
    ndx_tickers = []

    try:

        sp_df = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            storage_options=headers
        )[0]

        sp_tickers = (
            sp_df["Symbol"]
            .astype(str)
            .str.replace(
                ".",
                "-",
                regex=False
            )
            .tolist()
        )

    except Exception as e:

        print(
            f"⚠️ S&P 500 리스트 로드 실패: {e}"
        )


    try:

        ndx_tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
            storage_options=headers
        )

        ndx_df = next(
            df
            for df in ndx_tables
            if "Ticker" in df.columns
            or "Symbol" in df.columns
        )

        col_name = (
            "Ticker"
            if "Ticker" in ndx_df.columns
            else "Symbol"
        )

        ndx_tickers = (
            ndx_df[col_name]
            .astype(str)
            .str.replace(
                ".",
                "-",
                regex=False
            )
            .tolist()
        )

    except Exception as e:

        print(
            f"⚠️ NASDAQ-100 리스트 로드 실패: {e}"
        )


    return sorted(
        set(
            sp_tickers
            + ndx_tickers
        )
    )


# ============================================================
# RS RATING
# ============================================================

def calc_rs_rating(df_close):

    close = (
        df_close
        .dropna()
    )

    n = len(close)

    if n < 200:
        return None


    idx_3m = max(
        0,
        n - 64
    )

    idx_12m = max(
        0,
        n - 241
    )


    r3m = (
        close.iloc[-1]
        / close.iloc[idx_3m]
        - 1
    )

    r12m = (
        close.iloc[-1]
        / close.iloc[idx_12m]
        - 1
    )


    return (
        r3m * 2
        + r12m
    ) / 3


# ============================================================
# CONTINUOUS SCORING
# ============================================================

def score_low(
    value,
    best,
    worst,
    max_points
):
    """
    값이 낮을수록 좋은 지표.
    """

    if pd.isna(value):
        return 0.0

    if value <= best:
        return float(max_points)

    if value >= worst:
        return 0.0


    return (
        float(max_points)
        * (worst - value)
        / (worst - best)
    )


def score_high(
    value,
    worst,
    best,
    max_points
):
    """
    값이 높을수록 좋은 지표.
    """

    if pd.isna(value):
        return 0.0

    if value <= worst:
        return 0.0

    if value >= best:
        return float(max_points)


    return (
        float(max_points)
        * (value - worst)
        / (best - worst)
    )


def calculate_continuous_score(
    rvol3,
    rs_change_20d,
    setup_type,
    **kwargs
):

    score = 0.0


    # ========================================================
    # 1. Volume Dry-Up
    # Max 25
    # ========================================================

    score += score_low(
        rvol3,
        best=0.30,
        worst=1.00,
        max_points=25
    )


    # ========================================================
    # 2. RS Line Improvement
    # Max 15
    # ========================================================

    score += score_high(
        rs_change_20d,
        worst=0.00,
        best=0.08,
        max_points=15
    )


    # ========================================================
    # 3. Strategy Structure
    # Max 60
    # ========================================================

    if setup_type == "20EMA":

        close_loc = kwargs.get(
            "close_loc",
            0.5
        )

        ema_dist = abs(
            kwargs.get(
                "ema_dist",
                0.03
            )
        )


        # Candle recovery quality
        score += score_high(
            close_loc,
            worst=0.20,
            best=0.80,
            max_points=30
        )


        # EMA touch precision
        score += score_low(
            ema_dist,
            best=0.00,
            worst=0.03,
            max_points=30
        )


    elif setup_type == "VCP":

        range_5d = kwargs.get(
            "range_5d",
            0.075
        )

        pivot_dist = kwargs.get(
            "pivot_dist",
            0.07
        )


        score += score_low(
            range_5d,
            best=0.02,
            worst=0.075,
            max_points=35
        )


        score += score_low(
            pivot_dist,
            best=0.00,
            worst=0.07,
            max_points=25
        )


    elif setup_type == "B&R":

        retest_dist = kwargs.get(
            "retest_dist",
            0.04
        )


        score += score_low(
            retest_dist,
            best=0.00,
            worst=0.04,
            max_points=60
        )


    elif setup_type == "MTF":

        flag_range = kwargs.get(
            "flag_range",
            0.15
        )


        score += score_low(
            flag_range,
            best=0.03,
            worst=0.15,
            max_points=60
        )


    return min(
        100,
        int(
            round(score)
        )
    )


# ============================================================
# GRADE
#
# IMPORTANT:
# Grade is NOT based on RS Rating.
#
# RS >= 70 = Universe Gate only.
#
# Grade = Setup Quality Score.
# ============================================================

def grade_from_score(score):

    if score >= 85:
        return "S"

    if score >= 70:
        return "A"

    if score >= 60:
        return "B"

    return None


# ============================================================
# STATE
# ============================================================

def load_compatible_state():

    if not os.path.exists(
        STATE_FILE
    ):
        return {}


    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            raw_state = json.load(f)

    except Exception as e:

        print(
            f"⚠️ state.json 오류: {e}"
        )

        return {}


    if not isinstance(
        raw_state,
        dict
    ):
        return {}


    compatible = {

        ticker: item

        for ticker, item
        in raw_state.items()

        if (
            isinstance(
                item,
                dict
            )
            and
            item.get(
                "engine_version"
            )
            == ENGINE_VERSION
        )
    }


    dropped = (
        len(raw_state)
        - len(compatible)
    )


    if dropped > 0:

        print(
            f"🧹 이전 버전 state "
            f"{dropped}개 제거"
        )


    return compatible


# ============================================================
# MARKET CAP
# ============================================================

def safe_market_cap_billions(
    ticker
):

    try:

        fast_info = (
            yf.Ticker(
                ticker
            )
            .fast_info
        )


        mcap = fast_info.get(
            "marketCap",
            None
        )


        if mcap is None:
            return None


        return round(
            float(mcap)
            / 1_000_000_000,
            2
        )


    except Exception:

        return None


# ============================================================
# MAIN
# ============================================================

def run_lifecycle_screener():

    tickers = (
        get_combined_tickers()
    )


    print(
        f"📥 {len(tickers)}개 종목 "
        f"+ SPY 다운로드 중..."
    )


    fetch_list = sorted(
        set(
            tickers
            + ["SPY"]
        )
    )


    raw_data = yf.download(

        fetch_list,

        period="1y",

        interval="1d",

        group_by="ticker",

        auto_adjust=True,

        threads=True,

        progress=False
    )


    # ========================================================
    # SPY
    # ========================================================

    try:

        spy_close = (
            raw_data["SPY"]["Close"]
            .dropna()
        )

    except Exception:

        spy_close = None

        print(
            "⚠️ SPY 데이터 없음"
        )


    # ========================================================
    # RS UNIVERSE PERCENTILE
    # ========================================================

    rs_raw = {}


    for ticker in tickers:

        try:

            if (
                ticker
                not in raw_data.columns.levels[0]
            ):
                continue


            close = (
                raw_data[ticker]["Close"]
                .dropna()
            )


            if len(close) < 200:
                continue


            raw_rs = (
                calc_rs_rating(
                    close
                )
            )


            if raw_rs is not None:

                rs_raw[
                    ticker
                ] = raw_rs


        except Exception:

            continue


    rs_series = pd.Series(
        rs_raw,
        dtype="float64"
    ).dropna()


    rs_percentile = (
        rs_series.rank(
            pct=True
        )
        * 99
    )


    old_state = (
        load_compatible_state()
    )


    new_state = {}

    dashboard_output = []


    print(
        "🔍 4-Core v2.3 "
        "스크리닝 시작..."
    )


    # ========================================================
    # INDIVIDUAL STOCK
    # ========================================================

    for ticker in tickers:

        try:

            if (
                ticker
                not in raw_data.columns.levels[0]
            ):
                continue


            df = (
                raw_data[ticker]
                .dropna()
                .copy()
            )


            if len(df) < 230:
                continue


            # =================================================
            # INDICATORS FIRST
            # =================================================

            df["Vol50Avg"] = (
                df["Volume"]
                .rolling(50)
                .mean()
            )


            df["EMA20"] = (
                df["Close"]
                .ewm(
                    span=20,
                    adjust=False
                )
                .mean()
            )


            df["SMA50"] = (
                df["Close"]
                .rolling(50)
                .mean()
            )


            df["SMA200"] = (
                df["Close"]
                .rolling(200)
                .mean()
            )


            c = df.iloc[-1]


            price = float(
                c["Close"]
            )


            signal_date = (
                pd.Timestamp(
                    df.index[-1]
                )
                .strftime(
                    "%Y-%m-%d"
                )
            )


            # =================================================
            # GATE 1
            #
            # RS >= 70 is ONLY a universe filter.
            # =================================================

            avg_dollar_vol_50 = (

                (
                    df["Close"]
                    * df["Volume"]
                )

                .rolling(50)

                .mean()

                .iloc[-1]
            )


            rs_rating = round(

                float(

                    rs_percentile.get(
                        ticker,
                        0
                    )
                ),

                1
            )


            if (
                price < 10
                or
                pd.isna(
                    avg_dollar_vol_50
                )
                or
                avg_dollar_vol_50
                < 50_000_000
                or
                rs_rating < 70
            ):

                continue


            # =================================================
            # RVOL3
            # =================================================

            vol50 = float(
                df["Vol50Avg"]
                .iloc[-1]
            )


            vol_3_avg = float(
                df["Volume"]
                .tail(3)
                .mean()
            )


            if vol50 > 0:

                rvol3 = (
                    vol_3_avg
                    / vol50
                )

            else:

                rvol3 = 1.0


            # =================================================
            # RS LINE CHANGE VS SPY
            # =================================================

            rs_change_20d = 0.0


            if spy_close is not None:

                aligned_spy = (

                    spy_close

                    .reindex(
                        df.index
                    )

                    .ffill()
                )


                rs_line = (
                    df["Close"]
                    / aligned_spy
                )


                rs_line = (
                    rs_line
                    .replace(
                        [
                            float("inf"),
                            -float("inf")
                        ],
                        pd.NA
                    )
                    .dropna()
                )


                if (
                    len(rs_line) > 21
                    and
                    rs_line.iloc[-21] != 0
                ):

                    rs_change_20d = float(

                        rs_line.iloc[-1]

                        / rs_line.iloc[-21]

                        - 1.0
                    )


            setups = {}

            setup_meta = {}


            # =================================================
            # 1. 20EMA PULLBACK
            #
            # Relaxed Gate:
            # RVOL <= 1.00
            # Low between -3% and +2%
            # =================================================

            ema20_5d_ago = float(
                df["EMA20"]
                .iloc[-6]
            )


            ema20_rising = (
                float(
                    c["EMA20"]
                )
                > ema20_5d_ago
            )


            ema_dist_low = float(

                c["Low"]

                / c["EMA20"]

                - 1.0
            )


            is_touching = (

                -0.03

                <= ema_dist_low

                <= 0.02
            )


            is_holding = (

                float(
                    c["Close"]
                )

                >=

                float(
                    c["EMA20"]
                )
            )


            range_today = max(

                float(
                    c["High"]
                    - c["Low"]
                ),

                0.01
            )


            close_loc = float(

                (
                    c["Close"]
                    - c["Low"]
                )

                / range_today
            )


            if (

                price
                > float(
                    c["SMA50"]
                )

                and ema20_rising

                and is_touching

                and is_holding

                and rvol3 <= 1.00
            ):


                score = (
                    calculate_continuous_score(

                        rvol3,

                        rs_change_20d,

                        "20EMA",

                        close_loc=
                            close_loc,

                        ema_dist=
                            ema_dist_low
                    )
                )


                setups[
                    "20EMA"
                ] = score


                setup_meta[
                    "20EMA"
                ] = {

                    "ema20":
                        round(
                            float(
                                c["EMA20"]
                            ),
                            2
                        ),

                    "ema_low_distance_pct":
                        round(
                            ema_dist_low
                            * 100,
                            2
                        ),

                    "close_location_pct":
                        round(
                            close_loc
                            * 100,
                            1
                        )
                }


            # =================================================
            # 2. VCP
            # =================================================

            prev_close = (
                df["Close"]
                .shift(1)
            )


            tr = pd.concat(

                [

                    df["High"]
                    - df["Low"],


                    (
                        df["High"]
                        - prev_close
                    ).abs(),


                    (
                        df["Low"]
                        - prev_close
                    ).abs()
                ],

                axis=1

            ).max(
                axis=1
            )


            tr_pct = (
                tr
                / prev_close
            )


            vol_old = float(
                tr_pct
                .iloc[-20:-10]
                .mean()
            )


            vol_mid = float(
                tr_pct
                .iloc[-10:-5]
                .mean()
            )


            vol_new = float(
                tr_pct
                .iloc[-5:]
                .mean()
            )


            # Relaxed contraction:
            # at least 8% improvement
            is_contracting = (

                vol_mid
                <= vol_old * 0.92

                and

                vol_new
                <= vol_mid * 0.92
            )


            high_5 = float(
                df["High"]
                .tail(5)
                .max()
            )


            low_5 = float(
                df["Low"]
                .tail(5)
                .min()
            )


            range_5d = (

                (
                    high_5
                    - low_5
                )

                / low_5

                if low_5 > 0

                else 1.0
            )


            vcp_pivot = float(

                df["High"]

                .shift(1)

                .tail(20)

                .max()
            )


            pivot_dist = abs(

                price

                / vcp_pivot

                - 1.0
            )


            near_pivot = (

                vcp_pivot * 0.90

                <= price

                <= vcp_pivot * 1.025
            )


            if (

                price
                > float(
                    c["SMA50"]
                )

                > float(
                    c["SMA200"]
                )

                and is_contracting

                and range_5d
                <= 0.075

                and near_pivot

                and rvol3
                <= 0.85
            ):


                score = (
                    calculate_continuous_score(

                        rvol3,

                        rs_change_20d,

                        "VCP",

                        range_5d=
                            range_5d,

                        pivot_dist=
                            pivot_dist
                    )
                )


                setups[
                    "VCP"
                ] = score


                setup_meta[
                    "VCP"
                ] = {

                    "pivot":
                        round(
                            vcp_pivot,
                            2
                        ),

                    "pivot_distance_pct":
                        round(
                            pivot_dist
                            * 100,
                            2
                        ),

                    "range_5d_pct":
                        round(
                            range_5d
                            * 100,
                            2
                        ),

                    "tr_old_pct":
                        round(
                            vol_old
                            * 100,
                            2
                        ),

                    "tr_mid_pct":
                        round(
                            vol_mid
                            * 100,
                            2
                        ),

                    "tr_new_pct":
                        round(
                            vol_new
                            * 100,
                            2
                        )
                }


            # =================================================
            # 3. BREAKOUT & RETEST
            # =================================================

            prior_200d_high = (

                df["High"]

                .shift(1)

                .rolling(200)

                .max()
            )


            prior_vol50 = (

                df["Volume"]

                .shift(1)

                .rolling(50)

                .mean()
            )


            br_candidates = []


            for days_ago in range(
                3,
                31
            ):


                idx = (
                    -days_ago
                )


                pivot = (
                    prior_200d_high
                    .iloc[idx]
                )


                benchmark_vol = (
                    prior_vol50
                    .iloc[idx]
                )


                if (
                    pd.isna(
                        pivot
                    )
                    or
                    pd.isna(
                        benchmark_vol
                    )
                    or
                    benchmark_vol <= 0
                ):

                    continue


                pivot = float(
                    pivot
                )


                prev_c = float(
                    df["Close"]
                    .iloc[idx - 1]
                )


                day_c = float(
                    df["Close"]
                    .iloc[idx]
                )


                breakout_vol = float(
                    df["Volume"]
                    .iloc[idx]
                )


                breakout_rvol = (

                    breakout_vol

                    / float(
                        benchmark_vol
                    )
                )


                fresh_breakout = (

                    prev_c
                    <= pivot * 1.01

                    and

                    day_c
                    > pivot * 1.01
                )


                if (
                    not fresh_breakout
                    or
                    breakout_rvol < 1.20
                ):

                    continue


                post_breakout_highs = (
                    df["High"]
                    .iloc[idx + 1:]
                )


                if (
                    post_breakout_highs.empty
                ):

                    continue


                peak_since = float(
                    post_breakout_highs
                    .max()
                )


                # Must separate from pivot
                if (
                    peak_since
                    < pivot * 1.03
                ):

                    continue


                pullback_from_peak = (

                    peak_since
                    - price

                ) / peak_since


                if (
                    pullback_from_peak
                    < 0.02
                ):

                    continue


                low_retest_dist = abs(

                    float(
                        c["Low"]
                    )

                    / pivot

                    - 1.0
                )


                touching_pivot = (

                    pivot * 0.96

                    <= float(
                        c["Low"]
                    )

                    <= pivot * 1.025
                )


                holding_pivot = (

                    float(
                        c["Close"]
                    )

                    >= pivot * 0.98
                )


                if (

                    price
                    > float(
                        c["SMA200"]
                    )

                    and touching_pivot

                    and holding_pivot

                    and rvol3
                    <= 0.85
                ):


                    score = (
                        calculate_continuous_score(

                            rvol3,

                            rs_change_20d,

                            "B&R",

                            retest_dist=
                                low_retest_dist
                        )
                    )


                    br_candidates.append({

                        "score":
                            score,

                        "pivot":
                            pivot,

                        "days_ago":
                            days_ago,

                        "breakout_rvol":
                            breakout_rvol,

                        "retest_dist":
                            low_retest_dist,

                        "pullback_from_peak":
                            pullback_from_peak
                    })


            if br_candidates:

                best_br = max(

                    br_candidates,

                    key=lambda x:
                        x["score"]
                )


                setups[
                    "B&R"
                ] = best_br[
                    "score"
                ]


                setup_meta[
                    "B&R"
                ] = {

                    "pivot":
                        round(
                            best_br[
                                "pivot"
                            ],
                            2
                        ),

                    "breakout_days_ago":
                        int(
                            best_br[
                                "days_ago"
                            ]
                        ),

                    "breakout_rvol":
                        round(
                            best_br[
                                "breakout_rvol"
                            ],
                            2
                        ),

                    "retest_distance_pct":
                        round(
                            best_br[
                                "retest_dist"
                            ]
                            * 100,
                            2
                        ),

                    "pullback_from_peak_pct":
                        round(
                            best_br[
                                "pullback_from_peak"
                            ]
                            * 100,
                            2
                        )
                }


            # =================================================
            # 4. MOMENTUM TIGHT FLAG
            # =================================================

            if rs_rating >= 90:


                w = (
                    df["Close"]
                    .tail(40)
                )


                max_runup = float(

                    (
                        w
                        / w.cummin()
                        - 1.0
                    )

                    .max()
                )


                high_40 = float(
                    df["High"]
                    .tail(40)
                    .max()
                )


                drawdown_from_high = (

                    (
                        high_40
                        - price
                    )

                    / high_40

                    if high_40 > 0

                    else 1.0
                )


                high_10 = float(
                    df["High"]
                    .tail(10)
                    .max()
                )


                low_10 = float(
                    df["Low"]
                    .tail(10)
                    .min()
                )


                flag_range = (

                    (
                        high_10
                        - low_10
                    )

                    / high_10

                    if high_10 > 0

                    else 1.0
                )


                if (

                    max_runup
                    >= 0.22

                    and

                    price
                    > float(
                        c["EMA20"]
                    )

                    > float(
                        c["SMA50"]
                    )

                    and

                    flag_range
                    <= 0.15

                    and

                    drawdown_from_high
                    <= 0.12

                    and

                    rvol3
                    <= 1.00
                ):


                    score = (
                        calculate_continuous_score(

                            rvol3,

                            rs_change_20d,

                            "MTF",

                            flag_range=
                                flag_range
                        )
                    )


                    setups[
                        "MTF"
                    ] = score


                    setup_meta[
                        "MTF"
                    ] = {

                        "max_runup_40d_pct":
                            round(
                                max_runup
                                * 100,
                                1
                            ),

                        "flag_range_10d_pct":
                            round(
                                flag_range
                                * 100,
                                2
                            ),

                        "drawdown_from_40d_high_pct":
                            round(
                                drawdown_from_high
                                * 100,
                                2
                            )
                }


            # =================================================
            # RESULT
            #
            # Keep all setups scoring >= 60
            # =================================================

            qualifying_setups = {

                strategy: score

                for strategy, score
                in setups.items()

                if score >= 60
            }


            if qualifying_setups:


                primary_strategy = max(

                    qualifying_setups,

                    key=
                        qualifying_setups.get
                )


                primary_score = (

                    qualifying_setups[
                        primary_strategy
                    ]
                )


                grade = (
                    grade_from_score(
                        primary_score
                    )
                )


                item_data = {

                    "engine_version":
                        ENGINE_VERSION,

                    "state":
                        "setup",

                    "strategy":
                        primary_strategy,

                    "score":
                        primary_score,

                    "grade":
                        grade,

                    "setups":
                        qualifying_setups,

                    "setup_meta": {

                        k: v

                        for k, v
                        in setup_meta.items()

                        if k
                        in qualifying_setups
                    },

                    "msg":
                        (
                            f"[{primary_strategy}] "
                            f"Setup Quality {primary_score}"
                        ),

                    "last_seen":
                        signal_date,

                    "signal_date":
                        signal_date,

                    "scan_ts_utc":
                        SCAN_TS_UTC,

                    "symbol":
                        ticker,

                    "price":
                        round(
                            price,
                            2
                        ),

                    "rvol":
                        round(
                            rvol3,
                            2
                        ),

                    "rs_rating":
                        rs_rating,

                    "rs_change_20d_pct":
                        round(
                            rs_change_20d
                            * 100,
                            2
                        ),

                    "mcap":
                        safe_market_cap_billions(
                            ticker
                        )
                }


                new_state[
                    ticker
                ] = item_data


                dashboard_output.append(
                    item_data
                )


            # =================================================
            # STALE STATE
            #
            # Keep in state only.
            # Do NOT show on dashboard.
            # =================================================

            else:


                prev = old_state.get(
                    ticker,
                    {}
                )


                if (

                    prev.get(
                        "state"
                    )
                    in {
                        "setup",
                        "stale"
                    }

                    and

                    prev.get(
                        "last_seen"
                    )
                ):


                    try:


                        last_seen_ts = (

                            pd.Timestamp(
                                prev[
                                    "last_seen"
                                ]
                            )

                            .normalize()
                        )


                        session_index = (

                            pd.DatetimeIndex(
                                df.index
                            )

                            .tz_localize(
                                None
                            )

                            .normalize()
                        )


                        sessions_since = int(

                            (
                                session_index
                                > last_seen_ts
                            )

                            .sum()
                        )


                        if (
                            sessions_since
                            <= 2
                        ):


                            stale_item = dict(
                                prev
                            )


                            stale_item[
                                "state"
                            ] = "stale"


                            stale_item[
                                "stale_as_of"
                            ] = signal_date


                            stale_item[
                                "stale_sessions"
                            ] = sessions_since


                            stale_item[
                                "scan_ts_utc"
                            ] = SCAN_TS_UTC


                            new_state[
                                ticker
                            ] = stale_item


                    except Exception:

                        pass


        except Exception as e:


            print(

                f"❌ {ticker}: "

                f"{type(e).__name__}: "

                f"{e}"
            )


            continue


    # ========================================================
    # SORT
    # ========================================================

    dashboard_output.sort(

        key=lambda x: (

            x.get(
                "score",
                0
            ),

            x.get(
                "rs_rating",
                0
            )
        ),

        reverse=True
    )


    # ========================================================
    # WRITE JSON
    # ========================================================

    with open(

        STATE_FILE,

        "w",

        encoding="utf-8"

    ) as f:


        json.dump(

            new_state,

            f,

            indent=2,

            ensure_ascii=False,

            allow_nan=False
        )


    with open(

        DASHBOARD_FILE,

        "w",

        encoding="utf-8"

    ) as f:


        json.dump(

            dashboard_output,

            f,

            indent=2,

            ensure_ascii=False,

            allow_nan=False
        )


    s_count = sum(
        1
        for x in dashboard_output
        if x["grade"] == "S"
    )


    a_count = sum(
        1
        for x in dashboard_output
        if x["grade"] == "A"
    )


    b_count = sum(
        1
        for x in dashboard_output
        if x["grade"] == "B"
    )


    print(
        f"✅ v{ENGINE_VERSION} 완료 | "
        f"S {s_count} | "
        f"A {a_count} | "
        f"B {b_count}"
    )


if __name__ == "__main__":

    run_lifecycle_screener()
