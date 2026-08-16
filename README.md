# 📈 S&P 500 20EMA Swing Trading Screener (AI-Powered)

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Automated%20Workflow-green?logo=githubactions)
![Gemini AI](https://img.shields.io/badge/Google%20Gemini-3.7%20Flash%20Thinking-orange?logo=google)
![Discord](https://img.shields.io/badge/Discord-Mobile%20Optimized%20(<34자)-5865F2?logo=discord)

미국 대형주($10B+) 대상 **20EMA 눌림목 추세추종 스윙 트레이딩 전략**을 정량 스크리닝하고, **Google Gemini 3.7 Flash (Extended Thinking)** 심층 추론 및 **최근 7일 실시간 뉴스**를 결합하여 **Discord 모바일 최적화(<34자) 리포트**를 매일 미국 장 마감 후 자동 발송하는 퀀트 파이프라인입니다.

---

## 🎯 1. 1차 정량 스크리닝 (10대 하드 필터)

전체 S&P 500 종목 중 아래의 엄격한 기술적/유동성 조건을 100% 동시 충족하는 종목만 1차 후보군으로 압축합니다.

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

## 📊 2. STAGE 1: 기술 점수 5대 평가 지표 (5.0★ 만점 채점표)

1차 하드 필터를 통과한 종목을 대상으로 5가지 핵심 퀀트 지표를 각 1.0점 만점으로 정밀 채점하여 기술적 순위를 산출합니다.

| 평가 항목 | 1.0점 (만점) | 0.5점 (보통) | 0.0점 (감점) | 파이썬 연산 지표 |
| :--- | :--- | :--- | :--- | :--- |
| **1. 52주 저항 룸** ⭐ | **5.0% ~ 10.0%**<br>(이상적 상방 룸) | **3.0% ~ 5.0%** 또는<br>**10.0% ~ 15.0%** | **3.0% 미만**<br>(전고점 저항 충돌 위험) | `Room52W(%)` |
| **2. 거래량 급감 (RelVol)** | **$RelVol < 0.60$**<br>(매도세 완전 소멸) | **$0.60 \le RelVol < 0.90$**<br>(건전한 거래량 감소) | $0.90 \le RelVol$<br>(하드 필터 탈락) | `RelVol` |
| **3. 20EMA 밀착도** | **$0.0\% \le \text{이격} \le 1.5\%$**<br>(지지선 초근접) | **$1.5\% < \text{이격} \le 3.0\%$**<br>(추격 가능 범위) | $+3.0\%$ 초과<br>(하드 필터 탈락) | `EMA_Diff(%)` |
| **4. 중장기 정배열 추세** | **$EMA20 > SMA50 > SMA200$**<br>(완전 퍼펙트 정배열) | **$Price > SMA200$ 혼합**<br>(단기 골든크로스 진행) | 역배열<br>(하드 필터 탈락) | `Trend` |
| **5. 캔들 지지력 (Price Action)** | **밑꼬리 $\ge 40\%$** 또는<br>**종가위치 $\ge 70\%$** | **밑꼬리 $\ge 35\%$** 또는<br>**종가위치 $\ge 60\%$** | 지지력 미달<br>(하드 필터 탈락) | `Shadow%`, `CloseLoc%` |

---

## 🧠 3. STAGE 2: 7일 뉴스 하이브리드 파싱 & 리스크 등급 (A/B/C/D)

최신 Yahoo Finance 데이터 구조(`content.pubDate`, `content.title`)와 레거시 구조를 모두 지원하는 하이브리드 뉴스 엔진을 통해 **최근 7일(168시간) 이내 뉴스만 정밀 추출**하여 촉매 점수를 가감합니다.

```text
[A/B/C/D 리스크 등급 및 촉매 보정 기준]
• Grade A (+1★) : 2주 내 어닝 없음 + 최근 7일 내 강력한 호재 뉴스 + Strong Buy 컨센서스
• Grade B ( 0★) : 2주 내 어닝 없음 + 최근 7일 내 특이 악재 없는 중립 흐름 + Buy/Hold
• Grade C (-1★) : 2주 이내 실적 발표 예정(어닝 변동성 위험) 또는 단기 악재/노이즈
• Grade D (-2★) : 3일 내 실적 발표 임박 또는 치명적 규제/품질 이슈 (Stage 3 추천 배제)
