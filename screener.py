import io
import os
import re
import sys
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf
import google.generativeai as genai

# ==============================================================================
# 1. 헬퍼 함수 (URL 자동 세니타이징)
# ==============================================================================
def sanitize_url(raw_url_str):
    """마크다운 링크 문법 및 특수문자로 인한 InvalidSchema 에러를 원천 차단합니다."""
    match = re.search(r"https?://[^\s\)\]\"']+", str(raw_url_str))
    if match:
        return match.group(0)
    return str(raw_url_str).replace("[", "").replace("]", "").replace("(", "").replace(")", "").strip()

# ==============================================================================
# 2. 환경변수 및 전역 설정
# ==============================================================================
ET_TZ = ZoneInfo("America/New_York")
run_date_str = datetime.now(ET_TZ).strftime("%Y-%m-%d %H:%M ET")

# GitHub Secrets 우선 로드 (Fallback 기본값 포함)
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY", 
    "AQ.Ab8RN6KVNJKlJpNgNmoY2m4zsRrcjXbOpd0utS5tFK-u9TmcuQ"
)
DISCORD_WEBHOOK_URL = sanitize_url(os.environ.get(
    "DISCORD_WEBHOOK_URL", 
    "https://discord.com/api/webhooks/1538571023287324843/oF9h8EkOpNvaZHHoFo-Y_CRNymsCca5TzFF1oLKacvVGiwj-e54e-gb7rvfjixYKcujB"
))

# 최신 5종 모델 정예 우선순위 큐
TARGET_MODELS = [
    "gemini-3.7-flash",           # 1순위: 메인 추론 엔진
    "gemini-3.6-flash",           # 2순위: 고속 Flash
    "gemini-3.5-flash",           # 3순위: 안정화 Flash
    "gemini-3.1-pro-preview",     # 4순위: 심층 퀀트 추론
    "gemini-2.5-flash"            # 5순위: 표준 안전망
]

# ==============================================================================
# 3. Gemini API 연결 사전 검증 (Pre-flight Check)
# ==============================================================================
def verify_gemini_connection(api_key, target_models):
    print("🔑 [0/4] Gemini API 접속 사전 검증 중...")
    clean_api_key = str(api_key).strip()
    try:
        genai.configure(api_key=clean_api_key)
        available_models = [
            m.name.replace("models/", "") 
            for m in genai.list_models() 
            if "generateContent" in m.supported_generation_methods
        ]
        model_queue = [m for m in target_models if m in available_models] + [m for m in available_models if "gemini" in m]
        model_queue = list(dict.fromkeys(model_queue))
        
        for m_name in model_queue:
            try:
                test_model = genai.GenerativeModel(model_name=m_name)
                test_res = test_model.generate_content("Ping")
                if test_res and test_res.text:
                    print(f"  ✅ Gemini API 정상 연결 확인! [사용 모델: {m_name}]")
                    return True, m_name, model_queue
            except Exception:
                continue
                
        return False, None, model_queue
    except Exception as e:
        print(f"  ❌ Gemini 접속 실패: {str(e)}")
        return False, None, []

# ==============================================================================
# 4. 뉴스 추출 및 디스코드 분할 발송 보조 함수
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

def send_discord_clean_report(webhook_url, text, model_info, run_date, data_date):
    url_clean = sanitize_url(webhook_url)
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
            requests.post(url_clean, json={"content": formatted_msg})
            time.sleep(0.6)
        else:
            lines = sec.split("\n")
            chunk = f"{bt}\n"
            for line in lines:
                if line.startswith("```"):
                    continue
                if len(chunk) + len(line) + 5 > 1900:
                    chunk += f"\n{bt}"
                    requests.post(url_clean, json={"content": chunk})
                    time.sleep(0.6)
                    chunk = f"{bt}\n{line}\n"
                else:
                    chunk += line + "\n"
            if len(chunk) > 5:
                chunk += f"{bt}"
                requests.post(url_clean, json={"content": chunk})
                time.sleep(0.6)

# ==============================================================================
# 5. [STAGE 1: 파이썬 100% 정량 채점] S&P 500 수집 및 TOP 20 확정
# ==============================================================================
is_connected, confirmed_model, validated_queue = verify_gemini_connection(GEMINI_API_KEY, TARGET_MODELS)
if not is_connected:
    print("⛔ [실행 중단] Gemini API 접속 실패로 프로세스를 종료합니다.")
    sys.exit(1)

print(f"\n🌐 [1/4] S&P 500 종목 데이터 수집 중... ({run_date_str})")
sp500_url = sanitize_url("[https://en.wikipedia.org/wiki/List_of_S%26P_500_companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)")
headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(sp500_url, headers=headers)
sp500_table = pd.read_html(io.StringIO(response.text))[0]

sp500_table["Clean_Symbol"] = sp500_table["Symbol"].str.replace(".", "-", regex=False)
company_meta = sp500_table.set_index("Clean_Symbol")[["Security", "GICS Sub-Industry"]].to_dict("index")
all_tickers = sp500_table["Clean_Symbol"].tolist()

print(f"⚡ [2/4] 전체 {len(all_tickers)}개 종목 주가 다운로드 중...")
raw_data = yf.download(all_tickers, period="1y", group_by="ticker", threads=True, progress=False)

try:
    data_date_str = raw_data.index[-1].strftime("%Y-%m-%d") + " (미국 정규장 종가)"
except Exception:
    data_date_str = "최근 영업일 종가"

candidates = []
print(f"🔍 [3/4] 파이썬 정량 채점(5.0★ 만점) 및 최근 7일 뉴스 수집 중...")

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
        
        # 1차 하드필터 ($10B+, 정배열, RelVol < 0.90, 52W룸 0~15%)
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
                
                # 🎯 [파이썬 수학적 5.0★ 채점]
                s_room = 1.0 if (5.0 <= room_52w <= 10.0) else (0.5 if (3.0 <= room_52w < 5.0 or 10.0 < room_52w <= 15.0) else 0.0)
                s_vol = 1.0 if rel_vol < 0.60 else 0.5
                s_ema = 1.0 if ema_diff <= 1.5 else 0.5
                s_trend = 1.0 if is_perfect else 0.5
                s_candle = 1.0 if candle_support_pass else 0.5
                
                total_score = s_room + s_vol + s_ema + s_trend + s_candle
                
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
                    "Total_Score": total_score,
                    "Stars": f"{int(round(total_score))}★",
                    "Recent7DaysNews": news_str
                })
    except Exception:
        continue

df_result = pd.DataFrame(candidates)

if df_result.empty:
    print("❌ 조건을 충족하는 종목이 없습니다. 관망 리포트를 발송합니다.")
    no_trade_msg = "📊 [데일리 20EMA 스윙 리포트]\n현재 10대 엄격 조건($10B+, RSI 45~65, 저항룸 0~15%, RelVol < 0.9)을 충족하는 종목이 없습니다.\n👉 무리한 진입을 지양하고 현금 관망(NO TRADE)을 권장합니다."
    send_discord_clean_report(DISCORD_WEBHOOK_URL, no_trade_msg, confirmed_model, run_date_str, data_date_str)
    sys.exit(0)

# 🎯 파이썬 완벽 고정 다중 정렬 (총점 -> 52W룸 최적거리 7.5% -> RelVol -> 시총)
df_result["Room_Dist"] = abs(df_result["Room52W(%)"] - 7.5)
df_sorted = df_result.sort_values(
    by=["Total_Score", "Room_Dist", "RelVol", "MktCap($B)"],
    ascending=[False, True, True, False]
).reset_index(drop=True)

# 20개 종목 확정
top20_df = df_sorted.head(20).copy()
top20_df.index = top20_df.index + 1

# ==============================================================================
# 6. STAGE 1 파이썬 직접 생성 (34자 포맷 완벽 고정)
# ==============================================================================
stage1_lines = [
    "### [SECTION 1]",
    "🏆 [STAGE 1: 기술적 1차 셋업 TOP 20]",
    "순위 종목  시총   이격  52W룸 RelV 점수"
]

for rank, row in top20_df.iterrows():
    r_str = f"{rank:02d}"
    s_str = f"{row['Symbol']:<5}"
    m_val = row['MktCap($B)']
    m_str = f"${int(m_val)}B" if m_val >= 100 else f"${m_val:.1f}B"
    m_str = f"{m_str:<6}"
    e_str = f"+{row['EMA_Diff(%)']:.1f}%" if row['EMA_Diff(%)'] >= 0 else f"{row['EMA_Diff(%)']:.1f}%"
    e_str = f"{e_str:<6}"
    room_str = f"{row['Room52W(%)']:.1f}%"
    room_str = f"{room_str:<5}"
    vol_str = f"{row['RelVol']:.2f}"
    vol_str = f"{vol_str:<5}"
    star_str = row['Stars']
    stage1_lines.append(f"{r_str} {s_str} {m_str} {e_str} {room_str} {vol_str} {star_str}"[:34])

stage1_text = "\n".join(stage1_lines)
print(f"✨ [STAGE 1 완료] 총 {len(df_result)}개 중 상위 20개 종목 확정")

# ==============================================================================
# 7. [AI 전담: STAGE 2 TOP 10 & STAGE 3 TOP 10] 리포트 생성
# ==============================================================================
AI_PROMPT = """# Role & Core Mission
너는 미국 대형주 20EMA 눌림목 스윙 트레이딩 전문 퀀트 분석가다.
입력된 STAGE 1 20개 종목의 정량 데이터와 [최근 7일 뉴스]를 종합 분석하여 SECTION 2부터 SECTION 5까지 작성하라.

[⚠️ 리스크 등급(A/B/C/D) 절대 판정 및 촉매 점수 보정]
• Grade A (+1★): 2주 내 어닝 없음 + 최근 7일 내 강력한 호재 뉴스 + Strong Buy 컨센서스
• Grade B ( 0★): 2주 내 어닝 없음 + 최근 7일 내 특이 악재 없는 중립 뉴스 + Buy/Hold
• Grade C (-1★): 2주 이내 실적발표(어닝 변동성 위험) 또는 최근 7일 내 단기 악재/노이즈
• Grade D (-2★): 3일 내 실적발표 임박 또는 치명적 규제/조사 악재 (Stage 3 추천 제외)

[서식 및 출력 절대 규칙]
1. 모든 테이블은 1줄당 공백 포함 최대 34자(Characters)를 절대 초과하지 마라.
2. STAGE 2-A: 입력된 20개 종목 중 최상위 10개 종목에 대해 '순번. 티커 - 정식회사명 (시총)' 표기 후 사업/해자, 7일 뉴스, 리스크, 센티먼트/등급을 상세 작성하라.
3. STAGE 2-B: 20개 종목의 촉매 보정 후 최종 점수(6★>5★>4★) 내림차순으로 재정렬하여 **최종 TOP 10 테이블(01~10번)**만 출력하라.
4. STAGE 3-A: 최종 선정된 **TOP 10 종목 전체에 대해 실전 매매 실행표(01~10번)**를 34자 테이블로 작성하라. (1차: 2.0R 50% 분할익절 / 2차: 52주 고가)
5. STAGE 3-B: 최종 선정된 **TOP 10 종목 전체에 대해 시초가 매트릭스(01~10번)**를 34자 테이블로 작성하라. (정상:+0.5% | 갭상:+1.5% | 이탈:-1.5%)
6. 각 섹션은 반드시 '### [SECTION 2]', '### [SECTION 3]', '### [SECTION 4]', '### [SECTION 5]' 로 명확히 분리하여 출력하라.

[출력 양식 템플릿]

### [SECTION 2]
🏢 [STAGE 2-A: TOP 10 심층 펀더멘털 & 센티먼트 분석]
01. AAA - Company Name ($2800B)
 • 사업/해자: 핵심 사업 영역 및 해자 요약
 • 7일내 뉴스: 최근 7일 뉴스 기반 모멘텀
 • 리스크: 단기 매크로/산업 리스크
 • 센티먼트: Strong Buy (수혜 지속) | 등급: A (+1★)
... (01번부터 10번까지 총 10개 종목 상세 작성)

### [SECTION 3]
⚖️ [STAGE 2-B: 촉매 보정 최종 TOP 10]
최종 종목 기존  점수변동 등급 핵심사유
01  AAA (01) 5★->6★   A  클라우드수요폭증
... (01번부터 10번까지 총 10개 종목 출력)

### [SECTION 4]
🎯 [STAGE 3-A: 최종 TOP 10 실전 매매 실행표]
(※ 1차: 2.0R 50% 분할익절 / 2차: 52주 고가 라인)
순위 종목  매수가  손절가  1차(2R) 2차(52W)
01  AAA  $262.7 $257.5 $273.1 $287.2
... (01번부터 10번까지 총 10개 종목 출력)

### [SECTION 5]
🚦 [STAGE 3-B: 최종 TOP 10 시초가 매트릭스]
(※ 정상:+0.5% | 갭상:+1.5% | 이탈:-1.5%)
순위 종목  정상진입  갭상주의  이탈취소
01  AAA  ~$264.0  ~$266.6  <$258.7
... (01번부터 10번까지 총 10개 종목 출력)
"""

top20_payload = top20_df[["Symbol", "CompanyName", "MktCap($B)", "Price", "EMA20", "EMA_Diff(%)", "High52W", "Room52W(%)", "RelVol", "Stars", "Recent7DaysNews"]].to_string(index=False)

prompt_payload = f"""[분석 기준 정보 (미국 동부시각 ET)]
• 실행 일시: {run_date_str}
• 시장 데이터 기준일: {data_date_str}

아래는 파이썬에서 확정한 STAGE 1 TOP 20 종목의 정량 데이터 및 최근 7일 뉴스입니다:
{top20_payload}

위 20개 종목을 모두 평가하여:
- SECTION 2 (STAGE 2-A): 상위 10개 종목 심층 펀더멘털 분석
- SECTION 3 (STAGE 2-B): 촉매 보정 후 최종 TOP 10 재랭킹 테이블
- SECTION 4 (STAGE 3-A): 최종 TOP 10 실전 매매 실행표
- SECTION 5 (STAGE 3-B): 최종 TOP 10 시초가 매트릭스
를 34자 모바일 규격으로 작성해 주세요."""

print(f"🚀 [4/4] Gemini AI가 STAGE 2(TOP 10) & STAGE 3(TOP 10) 리포트 생성 중...")
ai_sections_text = None

for model_name in validated_queue:
    try:
        model = genai.GenerativeModel(
            model_name=model_name, 
            system_instruction=AI_PROMPT,
            generation_config={"temperature": 0.0}
        )
        response = model.generate_content(prompt_payload)
        if response and response.text:
            ai_sections_text = response.text
            confirmed_model = model_name
            print(f"  ✅ [{model_name}] 리포트 생성 완료!")
            break
    except Exception as e:
        print(f"  ⚠️ [{model_name}] 실패, 다음 후보 시도: {str(e)[:80]}")
        continue

if not ai_sections_text:
    ai_sections_text = "⚠️ AI 리포트 생성에 실패했습니다."

# ==============================================================================
# 8. STAGE 1(파이썬 20개) + STAGE 2~3(AI 10개) 통합 및 디스코드 발송
# ==============================================================================
final_full_report = f"{stage1_text}\n\n{ai_sections_text}"
send_discord_clean_report(DISCORD_WEBHOOK_URL, final_full_report, confirmed_model, run_date_str, data_date_str)
print("🎯 [완료] STAGE 1(20개) + STAGE 2~3(10개) 리포트가 디스코드에 성공적으로 발송되었습니다!")
