# 📈 S&P 500 20EMA Pullback Swing Screener & AI Quant Engine

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Gemini AI](https://img.shields.io/badge/AI-Google%20Gemini%203.7%20Flash-orange?logo=google)
![GitHub Actions](https://img.shields.io/badge/Automation-GitHub%20Actions-green?logo=githubactions)
![Discord](https://img.shields.io/badge/Alerts-Discord%20Webhook-purple?logo=discord)

미국 S&P 500 대형주($10B+)를 대상으로 **20EMA 눌림목 추세추종 스윙 트레이딩(보유 기간 2일~2주)** 기회를 포착하는 자동화 퀀트 스크리너입니다.

파이썬의 **100% 결정론적 정량 채점 알고리즘(STAGE 1)**과 구글 최신 Gemini AI의 **정성적 7일 뉴스·실적 리스크 심층 추론(STAGE 2~3)**을 결합하여, 매일 미국 증시 마감 후 디스코드 모바일 규격에 최적화된 리포트를 전송합니다.

---

## 🏗️ 시스템 아키텍처 & 3단계 파이프라인

```text
[S&P 500 전종목 (503개)]
   │
   ▼ [Python 100% 연산] 10대 하드필터 ($10B+, 정배열, RelVol < 0.90, 52W룸 0~15%)
[조건 충족 후보 종목군]
   │
   ▼ [Python 100% 연산] 5대 기술 지표 5.0★ 만점 수학적 정밀 채점
🏆 [STAGE 1: 기술적 1차 셋업 TOP 20 확정] (순위 오차 0%)
   │
   ▼ [Gemini AI Engine] 20개 종목 7일 뉴스 및 어닝 일정 전수 심사 (Grade A/B/C/D)
⚖️ [STAGE 2-A: 촉매 보정 최종 TOP 10 재랭킹]
   │
   ▼ [Gemini AI Engine] 최종 TOP 10 기업 해자, 뉴스 촉매, 리스크 심층 분석
🏢 [STAGE 2-B: 최종 TOP 10 심층 펀더멘털 & 센티먼트 리포트]
   │
   ▼ [Gemini AI Engine] 가격 산출 및 프리마켓/시초가 대응 전략 수립
🎯 [STAGE 3-A: 최종 TOP 10 실전 매매 실행표] (1차 2.0R 50% / 2차 52W 고가)
🚦 [STAGE 3-B: 최종 TOP 10 시초가(GAP) 매트릭스] (정상 / 갭상 / 이탈)
   │
   ▼ [Discord Webhook] 34자 모바일 최적화 자동 분할 발송
📱 [스마트폰 디스코드 알림 수신]
