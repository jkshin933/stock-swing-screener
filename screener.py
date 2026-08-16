import io
import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf

# ==============================================================================
# 1. 환경변수 로드 (GitHub Secrets 우선 + 기본값 Fallback)
# ==============================================================================
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY", 
    "AQ.Ab8RN6KVNJKlJpNgNmoY2m4zsRrcjXbOpd0utS5tFK-u9TmcuQ"
)
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL", 
    "[https://discord.com/api/webhooks/1538571023287324843/oF9h8EkOpNvaZHHoFo-Y_CRNymsCca5TzFF1oLKacvVGiwj-e54e-gb7rvfjixYKcujB](https://discord.com/api/webhooks/1538571023287324843/oF9h8EkOpNvaZHHoFo-Y_CRNymsCca5TzFF1oLKacvVGiwj-e54e-gb7rvfjixYKcujB)"
)

ET_TZ = ZoneInfo("America/New_York")

MODEL_CANDIDATES = [
    "gemini-3.7-flash",
    "gemini-3.1-pro",
    "gemini-3.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

MAX_RETRIES_PER_MODEL = 3
RETRY_DELAYS = [5, 10, 15]

# ==============================================================================
# 2. AI 시스템 프롬프트
# ==============================================================================
SYSTEM_PROMPT = """# Role & Core Mission
너는 미국 대형주($10B+) 추세추종 · 20EMA 눌림목 스윙 트레이딩(보유 기간 2일~2주) 전문 퀀트 분석가다.
입력된 정량 데이터와 [최근 7일 이내 뉴스]를 바탕으로 디스코드 모바일 환경에 최적화된 리포트를 작성하라.

[⭐ STAGE 1 기술 점수(5★ 만점) 52W 저항 룸 핵심 채점 룰]
1. 52W 룸 (상방 여력):
   - 5.0% ~ 10.0% : 1.0점 만점 (1차 목표가 2.0R을 전고점 밑에서 안전하게 익절 가능한 스위트스팟)
   - 3.0% ~ 5.0% 또는 10.0% ~ 15.0% : 0.5점 (전고점 근접 저항 또는 다소 깊은 눌림목)
   - 3.0% 미만 : 0.0점 (전고점 저항에 막혀 1차 익절 실패 위험이 높으므로 감점 처리)
2. 거래량 급감 (RelVol < 0.60: 1.0점 / 0.60~0.90: 0.5점)
3. 20EMA 밀착도 (0.0~1.5%: 1.0점 / 1.5~3.0%: 0.5점)
4. 정배열 추세 (EMA20>SMA50>SMA200: 1.0점 / 기타: 0.5점)
5. 캔들 지지력 (강력 반등 캔들: 1.0점 / 기본 지지: 0.5점)

[⚠️ 리스크 등급(A/B/C/D) 절대 판정 기준]
• Grade A (+1★): 2주 내 어닝 없음 + 최근 7일 내 강력한 호재 뉴스 + Strong Buy 컨센서스
• Grade B ( 0★): 2주 내 어닝 없음 + 최근 7일 내 특이 악재 없는 중립 뉴스 + Buy/Hold
• Grade C (-1★): 2주 이내 실적발표(어닝 변동성 위험) 또는 최근 7일 내 단기 악재/노이즈
• Grade D (-2★): 3일 내 실적발표 임박 또는 치명적 규제/조사 악재 (Stage 3 추천 제외)

[서식 및 출력 절대 규칙]
1. 모든 테이블은 1줄당 공백 포함 최대 34자(Characters)를 절대 초과하지 마라.
2. STAGE 1에서는 현재가를 제외하고 작성하라. (52W 룸이 5~10%인 종목이 상위에 오르도록 랭킹 산출)
3. STAGE 2-A에서는 '순번. 티커 - 정식회사명 (시총)' 표기 후 [최근 7일 뉴스]를 반영하여 작성하라.
4. STAGE 2-B는 최종 점수(6★>5★>4★) 내림차순으로 정렬하라.
5. STAGE 3-A는 1차목표(2.0R)와 2차목표(52주 고가) 가격 중심으로 작성하라.
6. 각 섹션은 반드시 '### [SECTION 1]', '### [SECTION 2]', '### [SECTION 3]', '### [SECTION 4]', '### [SECTION 5]' 로 명확히 분리하여 출력하라.

[섹션별 리포트 작성 가이드]

### [SECTION 1]
🏆 [STAGE 1: 기술적 1차 셋업 TOP 10]
순위 종목  시총   이격  52W룸 RelV 점수
01  AWK  $27B  +1.6% 5.7% 0.71 5★
02  APH  $206B +2.1% 6.8% 0.67 5★
03  GE   $382B +1.3% 5.6% 0.89 5★
04  HWM  $115B +2.4% 7.2% 0.90 4★
05  MA   $499B +2.0% 5.1% 0.84 4★
06  WFC  $269B +2.0% 8.3% 0.67 4★
07  KO   $377B +2.0% 3.7% 0.58 4★
08  DDOG $92B  +0.3% 14.6 0.83 4★
09  APD  $69B  +2.8% 1.9% 0.46 4★
10  BA   $183B +2.1% 9.8% 0.43 4★

### [SECTION 2]
🏢 [STAGE 2-A: TOP 10 심층 펀더멘털 & 센티먼트 분석]
(※ 01번부터 10번까지 회사명과 최근 7일 뉴스를 반영하여 상세 작성)

01. AWK - American Water Works ($27B)
 • 사업/해자: 미국 최대 규제 기반 상하수도 유틸리티 독점망
 • 7일내 뉴스: 수도요금 인상 승인 및 배당 안정성 부각
 • 리스크: 금리 변동에 따른 배당주 매력도 변화
 • 센티먼트: Buy (실적 안정성 우수) | 등급: B (0★)

02. APH - Amphenol Corp ($206B)
 • 사업/해자: AI 데이터센터 및 방산용 고성능 커넥터 글로벌 1위
 • 7일내 뉴스: AI 서버용 초고속 백플레인 수주 확대
 • 리스크: IT 하드웨어 전반 공급망 병목 현상
 • 센티먼트: Strong Buy (AI 인프라 수혜) | 등급: A (+1★)

... (03번부터 10번까지 10개 기업 상세 작성)

### [SECTION 3]
⚖️ [STAGE 2-B: 촉매 보정 및 최종 재랭킹 (FINAL TOP 10)]
최종 종목 기존  점수변동 등급 핵심사유
01  APH (02) 5★->6★   A  AI커넥터 수요폭증
02  GE  (03) 5★->6★   A  항공엔진 MRO 호조
03  AWK (01) 5★->5★   B  수도유틸 방어우수
04  MA  (05) 4★->4★   B  결제망 견조/중립
05  HWM (04) 4★->4★   B  항공우주 밸류중립
06  WFC (06) 4★->4★   B  대형은행 마진안정
07  KO  (07) 4★->4★   B  필수소비재 배당형
08  DDOG(08) 4★->4★   B  클라우드/52W룸大
09  APD (09) 4★->4★   B  독점가스/52W룸좁음
10  BA  (10) 4★->3★   C  인도지연/품질이슈

### [SECTION 4]
🎯 [STAGE 3-A: 최종 TOP 5 실전 매매 실행표]
(※ 1차: 2.0R 50% 분할익절 / 2차: 52주 고가 라인)
순위 종목  매수가  손절가  1차(2R) 2차(52W)
01  APH  $167.1 $163.8 $173.8 $178.5
02  GE   $368.4 $361.0 $383.2 $388.8
03  AWK  $136.2 $133.5 $141.6 $143.9
04  MA   $569.3 $557.9 $592.1 $598.0
05  HWM  $289.2 $282.8 $302.0 $310.0

### [SECTION 5]
🚦 [STAGE 3-B: 최종 TOP 5 시초가(GAP) 가격 매트릭스]
[공통 가이드: +0.5% 정상진입 | +1.5% 갭상 | -1.5% 이탈금지]

01. APH (전일 $167.11)
 • 정상진입 : $167.11 ~ $167.95 (100% 진입)
 • 갭상주의 : $167.96 ~ $169.61 (비중 50%)
 • 과열금지 : $169.62 초과 (추격 매수 금지)
 • 이탈손절 : $164.60 미만 (당일 진입 취소)

02. GE (전일 $368.38)
 • 정상진입 : $368.38 ~ $370.22 (100% 진입)
 • 갭상주의 : $370.23 ~ $373.90 (비중 50%)
 • 과열금지 : $373.91 초과 (추격 매수 금지)
 • 이탈손절 : $362.85 미만 (당일 진입 취소)

03. AWK (전일 $136.20)
 • 정상진입 : $136.20 ~ $136.88 (100% 진입)
 • 갭상주의 : $136.89 ~ $138.24 (비중 50%)
 • 과열금지 : $138.25 초과 (추격 매수 금지)
 • 이탈손절 : $134.16 미만 (당일 진입 취소)

04. MA (전일 $569.29)
 • 정상진입 : $569.29 ~ $572.13 (100% 진입)
 • 갭상주의 : $572.14 ~ $577.83 (비중 50%)
 • 과열금지 : $577.84 초과 (추격 매수 금지)
 • 이탈손절 : $560.75 미만 (당일 진입 취소)

05. HWM (전일 $289.18)
 • 정상진입 : $289.18 ~ $290.63 (100% 진입)
 • 갭상주의 : $290.64 ~ $293.52 (비중 50%)
 • 과열금지 : $293.53 초과 (추격 매수 금지)
 • 이탈손절 : $284.84 미만 (당일 진입 취소)
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

print("🌐 [1/4] S&P 500 종목 리스트 수집 중...")
sp500_url = "[https://en.wikipedia.org/wiki/List_of_S%26P_500_companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)"
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
# 4. AI 리포트 생성 (지능형 재시도 및 폴백)
# ==============================================================================
used_model_info = "Unknown Model"

if candidate_df.empty:
    report_text = "📊 [데일리 20EMA 스윙 리포트]\n현재 10대 엄격 조건($10B+, RSI 45~65, 저항룸 0~15%, RelVol < 0.9)을 충족하는 종목이 없습니다.\n👉 무리한 진입을 지양하고 현금 관망(NO TRADE)을 권장합니다."
else:
    prompt_payload = f"""[분석 기준 정보 (미국 동부시각 ET)]
• 실행 일시: {run_date_str}
• 시장 데이터 기준일: {data_date_str}

아래는 파이썬에서 기업 정보, 52주 최고가 및 Room52W(%) 데이터가 포함된 $10B+ 스윙 셋업 종목 데이터입니다:
{candidate_df.to_string(index=False)}

위 데이터를 바탕으로 [52W 룸 배점 기준: 5~10% 만점, 3~5% 0.5점, <3% 0점]과 [A/B/C/D 리스크 등급 기준]에 따라 SECTION 1부터 SECTION 5까지 34자 모바일 최적화 규격으로 작성해 주세요."""

    print(f"🚀 [4/4] AI 퀀트 정밀 리포트 생성 중...")
    clean_api_key = str(GEMINI_API_KEY).strip().encode("ascii", "ignore").decode("ascii")
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt_payload}]}]
    }
    
    report_text = None
    
    for model_name in MODEL_CANDIDATES:
        api_url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model_name}:generateContent?key={clean_api_key}"
        
        current_payload = payload.copy()
        is_thinking = False
        if "3.7" in model_name:
            current_payload["generationConfig"] = {"thinking_config": {"thinking_budget": 2048}}
            is_thinking = True
            
        for attempt in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                response = requests.post(api_url, headers=headers, json=current_payload, timeout=60)
                
                if response.status_code != 200 and "thinking" in response.text.lower():
                    current_payload.pop("generationConfig", None)
                    is_thinking = False
                    response = requests.post(api_url, headers=headers, json=current_payload, timeout=60)
                
                if response.status_code == 200:
                    res_json = response.json()
                    report_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                    mode_str = " (Extended Thinking)" if is_thinking else ""
                    used_model_info = f"{model_name}{mode_str}"
                    break
                
                elif response.status_code in [503, 429]:
                    if attempt < MAX_RETRIES_PER_MODEL:
                        time.sleep(RETRY_DELAYS[attempt])
                else:
                    break
                    
            except Exception:
                if attempt < MAX_RETRIES_PER_MODEL:
                    time.sleep(RETRY_DELAYS[attempt])
                else:
                    break
                    
        if report_text:
            break

    if not report_text:
        report_text = "⚠️ 모든 Gemini 모델 호출에 실패했습니다."

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
print("🎯 [GitHub Actions] 디스코드 리포트 전송 성공!")
