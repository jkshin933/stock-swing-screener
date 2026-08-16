# 📈 S&P 500 20EMA Swing Trading Screener (AI-Powered)

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Automated%20Workflow-green?logo=githubactions)
![Gemini AI](https://img.shields.io/badge/Google%20Gemini-3.7%20Flash%20Thinking-orange?logo=google)
![Discord](https://img.shields.io/badge/Discord-Mobile%20Optimized-5865F2?logo=discord)

미국 대형주($10B+) 대상 **20EMA 눌림목 추세추종 스윙 트레이딩 전략**을 정량 스크리닝하고, **Google Gemini 3.7 Flash (Extended Thinking)** 심층 추론 및 **최근 7일 실시간 뉴스**를 결합하여 **Discord 모바일 최적화(<34자) 리포트**를 매일 미국 장 마감 후 자동 발송하는 퀀트 파이프라인입니다.

---

## 🎯 1. 핵심 전략 및 퀀트 10대 필터링 조건

| 항목 | 정량 조건 | 전략적 목적 및 의미 |
| :--- | :--- | :--- |
| **유니버스 (Universe)** | S&P 500 편입 대형주 ($10B+ Market Cap) | 페니주/잡주 리스크 원천 차단 및 풍부한 유동성 확보 |
| **중장기 추세 (Trend)** | $Price > SMA200$, $Price > SMA50$, $Price > EMA20$ | 정배열 상승 추세가 확립된 주도주만 선별 |
| **눌림목 이격 (Pullback)** | $0.0\% \le \frac{Price - EMA20}{EMA20} \le +3.0\%$ | 20EMA 지지선 부근 저위험 진입 타점 포착 |
| **저항 룸 (Room to 52W)** | $0.0\% \le \frac{High_{52W} - Price}{Price} \le 15.0\%$ | 직전 매물대 저항이 적고 신고가 돌파 가능성이 높은 종목 |
| **모멘텀 (Momentum)** | $45.0 \le RSI(14) \le 65.0$ | 과매수(과열) 및 과매도(추세 붕괴) 구간 배제 |
| **눌림목 거래량 (Volume)** | 당일 거래량 / 20일 평균 거래량 $< 0.90$ (RelVol) | 거래량이 실리지 않은 **건전한 거래량 급감 눌림목** 확인 |
| **캔들 지지력 (Price Action)** | 밑꼬리 비율 $\ge 35\%$ 또는 종가 형성 위치 $\ge 60\%$ | 20EMA 지지선 터치 후 매수세 유입(하락 거부) 캔들 검증 |
| **거래대금 유동성** | 90일 평균 거래량 $\ge 1,000,000$ 주 | 슬리피지(Slippage) 없는 쾌적한 호가 진입 보장 |

---

## 📐 2. STAGE 1: 52주 저항 룸 스위트스팟 채점 룰 (5★ 만점)

1차 목표가(2.0R, 통상 +4~5%)를 52주 최고가 저항선 아래에서 안전하게 분할 익절할 수 있는지를 평가합니다.

| 52주 저항 룸 구간 | 배점 | 트레이딩 평가 및 랭킹 영향 |
| :---: | :---: | :--- |
| **5.0% ~ 10.0%** ⭐ | **1.0점 (만점)** | **이상적 스윙 타점.** 전고점 저항선에 닿기 전에 1차 목표가(2.0R) 도달 및 50% 분할 익절 가능. |
| **3.0% ~ 5.0%** | **0.5점** | 1차 목표가 부근에 전고점이 걸쳐 있어 돌파 매수세 필요. |
| **10.0% ~ 15.0%** | **0.5점** | 상방 여력은 충분하나 눌림 폭이 다소 깊어 매물 소화 필요. |
| **3.0% 미만** ⚠️ | **0.0점 (감점)** | **상방 저항 충돌 위험.** 1차 익절 전 전고점에 막힐 위험으로 순위 하향 (돌파 매매 영역). |

---

## 🧠 3. STAGE 2: 7일 뉴스 하이브리드 파싱 & 리스크 등급 (A/B/C/D)

최신 Yahoo Finance 데이터 구조(`content.pubDate`, `content.title`)와 구형 구조를 모두 호환하는 하이브리드 뉴스 엔진을 통해 **최근 7일(168시간) 이내 뉴스만 정밀 추출**합니다.

```text
[A/B/C/D 리스크 등급 분류 기준]
• Grade A (+1★) : 2주 내 어닝 없음 + 7일 내 강력한 호재 뉴스 + Strong Buy 컨센서스
• Grade B ( 0★) : 2주 내 어닝 없음 + 7일 내 특이 악재 없는 중립 흐름 + Buy/Hold
• Grade C (-1★) : 2주 이내 실적 발표 예정(어닝 변동성 위험) 또는 단기 악재/노이즈
• Grade D (-2★) : 3일 내 실적 발표 임박 또는 치명적 규제/품질 이슈 (Stage 3 추천 배제)
