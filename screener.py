import io
import os
import re
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf

# ==============================================================================
# 1. 환경변수 로드 (GitHub Secrets 우선 + Fallback 기본값)
# ==============================================================================
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY", 
    "AQ.Ab8RN6KVNJKlJpNgNmoY2m4zsRrcjXbOpd0utS5tFK-u9TmcuQ"
)
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL", 
    "https://discord.com/api/webhooks/1538571023287324843/oF9h8EkOpNvaZHHoFo-Y_CRNymsCca5TzFF1oLKacvVGiwj-e54e-gb7rvfjixYKcujB"
)

MODEL_CANDIDATES = [
    "gemini-3.7-flash",       # 1순위: 3.7 Flash (Extended Thinking)
    "gemini-3.1-pro",         # 2순위: 3.1 Pro (Advanced reasoning)
    "gemini-3.5-flash-lite",   # 3순위: 3.5 Flash-Lite (Fastest)
    "gemini-2.0-flash",       # 4순위: 2.0 Flash (안전망)
    "gemini-1.5-flash"        # 5순위: 1.5 Flash (최종 백업)
]

MAX_RETRIES_PER_MODEL = 3
RETRY_DELAYS = [5, 10, 15]

# ==============================================================================
# 2. AI 시스템 프롬프트 (실제 데이터 100% 그라운딩 및 서식 완벽 고정)
# ==============================================================================
SYSTEM_PROMPT = """# Role & Core Mission
너는 미국 대형주($10B+) 추세추종 · 20EMA 눌림목 스윙 트레이딩(보유 기간 2일~2주) 전문 퀀트 분석가다.

[⚠️ 절대 규칙: 그라운딩 및 환각 방지]
• 프롬프트 예시에 있는 가상 티커를 절대 출력하지 마라.
• 반드시 사용자 입력으로 제공된 [실제 종목 데이터]만을 정량 채점 기준에 따라 계산하여 실시간 최고 득점 종목 10개를 선출하라.

[⭐ STAGE 1 기술 점수(5★ 만점) 핵심 채점 룰]
1. 52W 룸 (상방 여력):
   - 5.0% ~ 10.0% : 1.0점 만점 (1차 목표가 2.0R을 전고점 밑에서 안전하게 익절 가능한 스위트스팟)
   - 3.0% ~ 5.0% 또는 10.0% ~ 15.0% : 0.5점
   - 3.0% 미만 : 0.0점 (전고점 저항 충돌 위험 감점)
2. 거래량 급감 (RelVol < 0.60: 1.0점 / 0.60~0.90: 0.5점)
3. 20EMA 밀착도 (0.0~1.5%: 1.0점 / 1.5~3.0%: 0.5점)
4. 정배열 추세 (EMA20>SMA50>SMA200: 1.0점 / 기타: 0.5점)
5. 캔들 지지력 (강력 반등 캔들: 1.0점 / 기본 지지: 0.5점)

[⚠️ 리스크 등급(A/B/C/D) 절대 판정 및 촉매 점수 보정]
• Grade A (+1★): 2주 내 어닝 없음 + 최근 7일 내 강력한 호재 뉴스 + Strong Buy 컨센서스
• Grade B ( 0★): 2주 내 어닝 없음 + 최근 7일 내 특이 악재 없는 중립 뉴스 + Buy/Hold
• Grade C (-1★): 2주 이내 실적발표(어닝 변동성 위험) 또는 최근 7일 내 단기 악재/노이즈
• Grade D (-2★): 3일 내 실적발표 임박 또는 치명적 규제/조사 악재 (Stage 3 추천 제외)

[서식 및 출력 절대 규칙]
1. 모든 테이블은 1줄당 공백 포함 최대 34자(Characters)를 절대 초과하지 마라.
2. STAGE 1에서는 현재가를 제외하고 작성하라.
3. STAGE 2-A에서는 '순번. 티커 - 정식회사명 (시총)' 표기 후 [최근 7일 뉴스]를 반영하여 작성하라.
4. STAGE 2-B는 최종 점수(6★>5★>4★) 내림차순으로 정렬하라.
5. STAGE 3-A(실전 매매 실행표)와 STAGE 3-B(시초가 매트릭스)는 반드시 34자 테이블 형태로 작성하라.
6. 각 섹션은 반드시 '### [SECTION 1]', '### [SECTION 2]', '### [SECTION 3]', '### [SECTION 4]', '### [SECTION 5]' 로 명확히 분리하여 출력하라.

[출력 양식 템플릿 예시]

### [SECTION 1]
🏆 [STAGE 1: 기술적 1차 셋업 TOP 10]
순위 종목  시총   이격  52W룸 RelV 점수
01  AAA  $2800B +0.8% 9.4% 0.57 5★
02  BBB  $206B +2.1% 6.8% 0.67 5★
...

### [SECTION 2]
🏢 [STAGE 2-A: TOP 10 심층 펀더멘털 & 센티먼트 분석]
01. AAA - Company Name ($2800B)
 • 사업/해자: 핵심 사업 영역 및 해자 요약
 • 7일내 뉴스: 최근 7일 뉴스 기반 모멘텀
 • 리스크: 단기 매크로/산업 리스크
 • 센티먼트: Strong Buy (수혜 지속) | 등급: A (+1★)
...

### [SECTION 3]
⚖️ [STAGE 2-B: 촉매 보정 및 최종 재랭킹 (FINAL TOP 10)]
최종 종목 기존  점수변동 등급 핵심사유
01  AAA (01) 5★->6★   A  클라우드수요폭증
...

### [SECTION 4]
🎯 [STAGE 3-A: 최종 TOP 5 실전 매매 실행표]
(※ 1차: 2.0R 50% 분할익절 / 2차: 52주 고가 라인)
순위 종목  매수가  손절가  1차(2R) 2차(52W)
01  AAA  $262.7 $257.5 $273.1 $287.2
...

### [SECTION 5]
🚦 [STAGE 3-B: 최종 TOP 5 시초가 매트릭스]
(※ 정상:+0.5% | 갭상:+1.5% | 이탈:-1.5%)
순위 종목  정상진입  갭상주의  이탈취소
01  AAA  ~$264.0  ~$266.6  <$258.7
...
"""

# ==============================================================================
# 3. 데이터 수집 및 7일 뉴스 하이브리드 파싱 함수
# ==============================================================================
def extract_recent_news(ticker_obj, max_count=3, max_days=7):
    news_list = []
    current_time = time.time()
    max_seconds = max_days * 24 * 60 * 60
    
    try:
        raw_news = ticker_obj.news
        if not raw_news:
            return "최근 주요 뉴스 없음"
            
        for item in raw_news:
            title = None
            pub_ts = None
            
            if "content" in item and isinstance(item["content"], dict):
                c = item["content"]
                title = c.get("title")
                pub_date_str = c.get("pubDate")
                if pub_date_str:
                    try:
                        dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                        pub_ts = dt.timestamp()
                    except Exception:
                        pass
            
            if not title and "title" in item:
                title = item.get("title")
                pub_ts = item.get("providerPublishTime")
                
            if title:
                if pub_ts is None or (current_time - pub_ts) <= max_seconds:
                    clean_title = title.strip().replace("\n", " ")
                    if clean_title and clean_title not in news_list:
                        news_list.append(clean_title)
                        if len(news_list) >= max_count:
                            break
    except Exception:
        pass
        
    return " | ".join(news_list) if news_list else "최근 7일 내 특이 뉴스 없음 (평이한 주가 흐름)"

run_date_str = datetime.now(ET_TZ).strftime("%Y-%m-%d %H:%M ET")

print(f"🌐 [1/4] S&P 500 종목 리스트 수집 중... ({run_date_str})")
raw_sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
url_match = re.search(r"https?://[^\s\)\]]+", raw_sp500_url)
sp500_url = url_match.group(0) if url_match else "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(sp500_url, headers=headers)
sp500_table = pd.read_html(io.StringIO(response.text))[0]

sp500_table["Clean_Symbol"] = sp500_table["Symbol"].str.replace(".", "-", regex=False)
company_meta = sp500_table.set_index("Clean_Symbol")[["Security", "GICS Sub-Industry"]].to_dict("index")
all_tickers = sp500_table["Clean_Symbol"].tolist()

print(f"⚡ [2/4] 전체 {len(all_tickers)}개 종목 데이터 다운로드 중...")
raw_data = yf.download(all_tickers, period="1y", group_by="ticker", threads=True, progress=False)

try:
    data_date_str = raw_data.index[-1].strftime("%Y-%m-%d") + " (미국 정규장 종가)"
except Exception:
    data_date_str = "최근 영업일 종가"

candidates = []

print(f"🔍 [3/4] 캔들 정량화, 10대 필터($10B+) 및 최근 7일 뉴스 수집 중...")
for ticker in all_tickers:
    try:
        if ticker not in raw_data.columns.levels[0]:
            continue
        df = raw_data[ticker].dropna()
        if len(df) < 200:
            continue
        
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["SMA50"] = df["Close"].rolling(window=50).mean()
        df["SMA200"] = df["Close"].rolling(window=200).mean()
        
        delta = df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df["RSI14"] = 100 - (100 / (1 + rs))
        
        current_price = df["Close"].iloc[-1]
        open_price = df["Open"].iloc[-1]
        high_price = df["High"].iloc[-1]
        low_price = df["Low"].iloc[-1]
        
        ema20 = df["EMA20"].iloc[-1]
        sma50 = df["SMA50"].iloc[-1]
        sma200 = df["SMA200"].iloc[-1]
        rsi14 = df["RSI14"].iloc[-1]
        high_52w = df["High"].tail(252).max()
        
        vol_avg20 = df["Volume"].tail(20).mean()
        vol_avg90 = df["Volume"].tail(90).mean()
        rel_vol = df["Volume"].iloc[-1] / vol_avg20 if vol_avg20 > 0 else 1.0
        
        ema_diff = (current_price - ema20) / ema20 * 100
        room_52w = (high_52w - current_price) / current_price * 100
        
        c_range = high_price - low_price
        lower_shadow_pct = ((min(open_price, current_price) - low_price) / c_range * 100) if c_range > 0 else 0
        close_loc_pct = ((current_price - low_price) / c_range * 100) if c_range > 0 else 0
        candle_support_pass = (lower_shadow_pct >= 35.0) or (close_loc_pct >= 60.0)
        
        cond_trend = (current_price > sma200) and (current_price > sma50) and (current_price > ema20)
        cond_ema = (0.0 <= ema_diff <= 3.0)
        cond_room = (0.0 <= room_52w <= 15.0)
        cond_rsi = (45.0 <= rsi14 <= 65.0)
        cond_rel_vol = (rel_vol < 0.90)
        cond_avg_vol = (vol_avg90 >= 1_000_000)
        
        if cond_trend and cond_ema and cond_room and cond_rsi and cond_rel_vol and cond_avg_vol:
            ticker_obj = yf.Ticker(ticker)
            market_cap = ticker_obj.fast_info.get("marketCap", 0)
            
            if market_cap >= 10_000_000_000:
                is_perfect = (ema20 > sma50 > sma200)
                meta = company_meta.get(ticker, {"Security": ticker, "GICS Sub-Industry": "N/A"})
                news_str = extract_recent_news(ticker_obj, max_count=3, max_days=7)
                
                candidates.append({
                    "Symbol": ticker,
                    "CompanyName": meta["Security"],
                    "Industry": meta["GICS Sub-Industry"],
                    "MktCap($B)": round(market_cap / 1e9, 1),
                    "Price": round(current_price, 2),
                    "EMA20": round(ema20, 2),
                    "EMA_Diff(%)": round(ema_diff, 2),
                    "High52W": round(high_52w, 2),
                    "Room52W(%)": round(room_52w, 2),
                    "RSI14": round(rsi14, 1),
                    "RelVol": round(rel_vol, 2),
                    "Shadow%": round(lower_shadow_pct, 1),
                    "CloseLoc%": round(close_loc_pct, 1),
                    "Candle_Pass": candle_support_pass,
                    "Trend": "EMA20>SMA50>SMA200" if is_perfect else "Mixed",
                    "Recent7DaysNews": news_str
                })
    except Exception:
        continue

candidate_df = pd.DataFrame(candidates)
print(f"✨ [완료] 조건 충족 종목 {len(candidate_df)}개 발견")

# ==============================================================================
# 4. AI 리포트 생성 (헤더 인증 및 모델 폴백 + 상세 에러 추적)
# ==============================================================================
used_model_info = "Unknown Model"
error_logs = []

if candidate_df.empty:
    report_text = "📊 [데일리 20EMA 스윙 리포트]\n현재 10대 엄격 조건($10B+, RSI 45~65, 저항룸 0~15%, RelVol < 0.9)을 충족하는 종목이 없습니다.\n👉 무리한 진입을 지양하고 현금 관망(NO TRADE)을 권장합니다."
else:
    prompt_payload = f"""[분석 기준 정보 (미국 동부시각 ET)]
• 실행 일시: {run_date_str}
• 시장 데이터 기준일: {data_date_str}

아래는 파이썬에서 추출한 실제 {len(candidate_df)}개 정량 분석 종목 데이터입니다:
{candidate_df.to_string(index=False)}

위 {len(candidate_df)}개 데이터 중에서만 52W 룸 배점 기준(5~10%: 1.0점 만점, 3~5%: 0.5점, <3%: 0점) 및 리스크 등급 기준에 따라 채점하여 SECTION 1부터 SECTION 5까지 34자 모바일 최적화 테이블 규격으로 리포트를 작성해 주세요."""

    print(f"🚀 [4/4] AI 퀀트 정밀 리포트 생성 중...")
    clean_api_key = str(GEMINI_API_KEY).strip()
    
    req_headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": clean_api_key
    }
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt_payload}]}]
    }
    
    report_text = None
    for model_name in MODEL_CANDIDATES:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_api_key}"
        current_payload = payload.copy()
        
        for attempt in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                response = requests.post(api_url, headers=req_headers, json=current_payload, timeout=90)
                
                if response.status_code == 200:
                    res_json = response.json()
                    report_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                    used_model_info = model_name
                    break
                else:
                    err_msg = f"[{model_name}] HTTP {response.status_code}: {response.text[:120]}"
                    error_logs.append(err_msg)
                    print(f"  ⚠️ {err_msg}")
                    if response.status_code in [503, 429] and attempt < MAX_RETRIES_PER_MODEL:
                        time.sleep(RETRY_DELAYS[attempt])
                    else:
                        break
            except Exception as e:
                err_msg = f"[{model_name}] Exception: {str(e)[:100]}"
                error_logs.append(err_msg)
                print(f"  ⚠️ {err_msg}")
                if attempt < MAX_RETRIES_PER_MODEL:
                    time.sleep(RETRY_DELAYS[attempt])
                else:
                    break
                    
        if report_text:
            break

    if not report_text:
        latest_err = error_logs[-1] if error_logs else "원인 불명"
        report_text = f"⚠️ 모든 Gemini 모델 호출에 실패했습니다.\n[원인 진단]: {latest_err}"

# ==============================================================================
# 5. 디스코드 안전 분할 발송
# ==============================================================================
def send_discord_clean_report(webhook_url, text, model_info, run_date, data_date):
    raw_clean_text = text.replace("```text", "").replace("```", "").strip()
    sections = raw_clean_text.split("### [SECTION")
    bt = chr(96) * 3
    
    first_section = True
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) >= 2 and sec[0].isdigit() and sec[1] == "]":
            sec = sec[2:].strip()
            
        if first_section:
            header = (
                f"📅 리포트 생성 : {run_date}\n"
                f"📊 데이터 기준 : {data_date}\n"
                f"🤖 AI Engine  : {model_info}\n"
                f"{'=' * 34}\n"
            )
            sec = header + sec
            first_section = False
            
        formatted_msg = f"{bt}\n{sec}\n{bt}"
        
        if len(formatted_msg) <= 1950:
            requests.post(webhook_url, json={"content": formatted_msg})
            time.sleep(0.6)
        else:
            lines = sec.split("\n")
            chunk = f"{bt}\n"
            for line in lines:
                if line.startswith("```"):
                    continue
                if len(chunk) + len(line) + 5 > 1900:
                    chunk += f"\n{bt}"
                    requests.post(webhook_url, json={"content": chunk})
                    time.sleep(0.6)
                    chunk = f"{bt}\n{line}\n"
                else:
                    chunk += line + "\n"
            if len(chunk) > 5:
                chunk += f"{bt}"
                requests.post(webhook_url, json={"content": chunk})
                time.sleep(0.6)

send_discord_clean_report(DISCORD_WEBHOOK_URL, report_text, used_model_info, run_date_str, data_date_str)
print("🎯 디스코드 리포트 전송 성공!")
