# 📈 S&P 500 20EMA Swing Trading Screener (AI-Powered)

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Automated%20Workflow-green?logo=githubactions)
![Gemini AI](https://img.shields.io/badge/Google%20Gemini-3.7%20Flash%20Thinking-orange?logo=google)
![Discord](https://img.shields.io/badge/Discord-Webhook%20Alert-5865F2?logo=discord)

미국 대형주($10B+) 대상 **20EMA 눌림목 추세추종 스윙 트레이딩 전략**을 정량 스크리닝하고, **Google Gemini 3.7 Flash (Extended Thinking)** 심층 추론 및 **최근 7일 실시간 뉴스**를 결합하여 **Discord 모바일 최적화 리포트**를 매일 자동 발송하는 퀀트 파이프라인입니다.

---

## 🎯 핵심 전략 및 퀀트 필터링 기준

| 항목 | 정량 조건 | 전략적 목적 |
| :--- | :--- | :--- |
| **유니버스 (Universe)** | S&P 500 편입 대형주 ($10B+ Market Cap) | 페니주/잡주 리스크 원천 차단 및 풍부한 유동성 확보 |
| **중장기 추세 (Trend)** | $Price > SMA200 > SMA50 > EMA20$ | 정배열 상승 추세가 확립된 주도주만 선별 |
| **눌림목 이격 (Pullback)** | $0.0\% \le \frac{Price - EMA20}{EMA20} \le +3.0\%$ | 20EMA 지지선 부근 저위험 진입 타점 포착 |
| **저항 룸 (Room to 52W)** | $0.0\% \le \frac{High_{52W} - Price}{Price} \le 15.0\%$ | 직전 매물대 저항이 적고 신고가 돌파 가능성이 높은 종목 |
| **모멘텀 (Momentum)** | $45.0 \le RSI(14) \le 65.0$ | 과매수(과열) 및 과매도(추세 붕괴) 구간 배제 |
| **눌림목 거래량 (Volume)** | 당일 거래량 / 20일 평균 거래량 $< 0.90$ (RelVol) | 거래량이 실리지 않은 **건전한 거래량 급감 눌림목** 확인 |
| **캔들 지지력 (Price Action)** | 밑꼬리 비율 $\ge 35\%$ 또는 종가 형성 위치 $\ge 60\%$ | 20EMA 지지선 터치 후 매수세 유입(하락 거부) 캔들 검증 |

---

## 🧠 AI 펀더멘털 & 7일 뉴스 촉매 재랭킹

파이썬이 수집한 **최근 7일(168시간) 야후 파이낸스 실시간 뉴스**와 **실적 발표 일정(어닝 리스크)**을 바탕으로 Gemini 3.7 Flash 모델이 단계별 리스크 등급을 판정합니다.

* **Grade A (+1★)**: 2주 내 어닝 없음 + 7일 내 강력한 호재(수주/실적 상향) + Strong Buy
* **Grade B ( 0★)**: 2주 내 어닝 없음 + 특이 악재 없는 중립적 흐름 + Buy/Hold
* **Grade C (-1★)**: **2주 이내 실적 발표 예정(어닝 변동성 위험)** 또는 단기 노이즈
* **Grade D (-2★)**: **3일 이내 실적 임박** 또는 치명적 규제/품질 리스크 (Stage 3 추천 배제)

---

## 📱 5단계 디스코드 리포트 구조 (모바일 34자 최적화)

모바일 디스코드 앱에서 줄바꿈 깨짐이 없도록 고정폭(34자 이내) 테이블 및 순수 코드 블록으로 출력됩니다.

```text
[헤더]
📅 리포트 생성 : 2026-08-16 18:00 ET (미국 동부시각)
📊 데이터 기준 : 2026-08-16 (미국 정규장 종가)
🤖 AI Engine  : gemini-3.7-flash (Extended Thinking)
==================================

🏆 [STAGE 1: 기술적 1차 셋업 TOP 10]
순위 종목  시총   이격  52W룸 RelV 점수
01  APD  $69B  +2.8% 1.9% 0.46 5★
...

🏢 [STAGE 2-A: TOP 10 심층 펀더멘털 & 7일 뉴스 분석]
01. APD - Air Products & Chemicals ($69B)
 • 사업/해자: 산업용 가스 글로벌 과점 공급망 및 장기 계약
 • 7일내 뉴스: 수소/청정에너지 인프라 프로젝트 수주
 • 센티먼트: Strong Buy | 등급: A (+1★)
...

⚖️ [STAGE 2-B: 촉매 보정 및 최종 재랭킹 (FINAL TOP 10)]
최종 종목 기존  점수변동 등급 핵심사유
01  APD (01) 5★->6★   A  독점가스/어닝無
...

🎯 [STAGE 3-A: 최종 TOP 5 실전 매매 실행표]
(※ 1차: 2.0R 50% 분할익절 / 2차: 52주 고가 라인)
순위 종목  매수가  손절가  1차(2R) 2차(52W)
01  APD  $309.0 $302.8 $321.4 $325.0
...

🚦 [STAGE 3-B: 최종 TOP 5 시초가(GAP) 가격 매트릭스]
[공통 가이드: +0.5% 정상진입 | +1.5% 갭상 | -1.5% 이탈금지]
01. APD (전일 $308.97)
 • 정상진입 : $308.97 ~ $310.51 (100% 진입)
 • 갭상주의 : $310.52 ~ $313.60 (비중 50%)
 • 과열금지 : $313.61 초과 (추격 매수 금지)
 • 이탈손절 : $304.33 미만 (당일 진입 취소)
