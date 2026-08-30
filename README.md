# 🎯 4-Core US Stock Swing Scanner (v2.0)
**미국 우량주(S&P 500 + NASDAQ 100) 무인 자동화 스윙 트레이딩 스캐너 & 모바일 대시보드**

![Python](https://img.shields.io/badge/Python-3.10-blue)
![GitHub Actions](https://img.shields.io/badge/Automated_by-GitHub_Actions-2088FF)
![GitHub Pages](https://img.shields.io/badge/Hosted_on-GitHub_Pages-success)

본 프로젝트는 마크 미네르비니(Mark Minervini), 윌리엄 오닐(William O'Neil) 등 월가 최상위 프랍 트레이더들의 매매 기법을 파이썬 알고리즘으로 구현한 **100% 무인 자동화 스크리닝 시스템**입니다. 

기존의 단순 O/X 조건 검색기의 한계(Lookahead Bias, 거짓 신호)를 극복하기 위해 **[기본 요건 검증 $\rightarrow$ 패턴 감지 $\rightarrow$ 품질 점수화]**의 3단 퀀트 엔진 아키텍처로 설계되었습니다. 매일 미국 장 마감 후 알고리즘이 자동으로 구동되며, 결과를 모바일 피드(Feed) 형태로 제공합니다.

🌐 **[모바일 대시보드 바로가기](https://jkshin933.github.io/stock-swing-screener/)** *(자신의 깃허브 주소로 변경)*

---

## ⚙️ 3-Stage Engine Architecture (핵심 알고리즘 구조)

이 스캐너는 단순히 보조지표가 겹치는 종목을 찾는 것이 아니라, 시장의 구조를 읽어내는 3단계 게이트를 거칩니다.

### [Gate 1] Hard Eligibility (시장 주도주 필터링)
잡주와 유동성 부족 종목을 원천 차단하는 기본 입장권입니다.
- **Price & Liquidity:** 주가 $10 이상, 50일 평균 일일 거래대금(Average Dollar Volume) $50M 이상.
- **Relative Strength (RS):** RS 점수 70 미만 하위 종목 자동 탈락.

### [Gate 2] Pattern Detection (4-Core 전략 감지)
시장 주도주를 대상으로 아래 4가지 셋업 구조가 성립하는지 정밀 검증합니다.

1. **📉 20EMA Pullback (Touch & Hold):** 상승하는 20일 지수이동평균선을 장중 하락(Undercut)으로 터치하되, 종가는 20일선 위에서 강력하게 말아 올리며 지지(Hold)한 종목.
2. **🎯 VCP (Volatility Contraction Pattern):** 20일 $\rightarrow$ 10일 $\rightarrow$ 5일로 갈수록 변동폭(Range)이 순차적으로 감소하며, 거래량이 극도로 마른 다단계 압축 종목. (부분집합 착시 방지 알고리즘 적용)
3. **🔄 Breakout & Retest (B&R):** 과거 메이저 저항선을 거대한 거래량과 함께 뚫어낸 '돌파 기준일(Breakout Day)'의 피벗(Pivot) 가격을 동결(Freeze)한 뒤, 주가가 산을 만들고 정확히 그 피벗으로 조정을 받아 지지력을 테스트하는 종목.
4. **🔥 Momentum Tight Flag (MTF):** 최근 40일 내 최소 25% 이상의 폭발적인 랠리(Run-up)를 기록한 극강의 주도주(RS 90+)가, 고점 부근에서 12% 이내의 타이트한 깃발형 횡보를 보이는 종목.

### [Gate 3] Quality Scoring (0~100점 연속 점수화)
패턴이 감지된 종목을 대상으로 '구조의 완성도'를 채점하여 등급을 부여합니다.
- **Volume Contraction (Max 25):** 3일 평균 거래량이 50일 평균 대비 얼마나 고갈(Dry-up) 되었는가?
- **RS Trend (Max 15):** 20일 전 대비 상대강도(RS Line)가 우상향하고 있는가?
- **Structure Precision (Max 60):** 피벗과의 오차율은 몇 %인가? VCP 압축의 강도는 어느 정도인가?
- 🏆 **S급(85점 이상), A급(70~84점)** 부여. 다중 셋업(Confluence) 발생 시 모든 전략 점수를 보존.

---

## ✨ 대시보드 주요 기능

- **🤖 100% 무인 자동화:** GitHub Actions를 통해 평일 미국 장 마감 직후(매일 20:30 UTC) 자동으로 파이썬 엔진 구동. (수동 갱신 버튼 지원)
- **📱 모바일 최적화 UI:** 인스타그램 피드처럼 스마트폰에서 스크롤하며 차트와 타점, 스코어 배지를 직관적으로 확인.
- **🎯 다중 셋업(Confluence) 렌더링:** 한 종목이 여러 패턴(예: VCP이면서 동시에 20EMA 지지)을 동시에 만족할 경우, `+ Also: 20EMA 84` 형태로 시너지 타점을 표시.
- **🛡️ 맞춤형 필터:** 대시보드 내에서 시가총액(Mega, Large, Mid)별, 매매 전략별 즉각적인 필터링 지원.

---

## 🚀 직접 구축하는 방법 (How to Fork & Setup)

누구나 이 리포지토리를 포크(Fork)하여 자신만의 무인 시스템을 구축할 수 있습니다.

1. 이 리포지토리를 **Fork** 합니다.
2. 리포지토리의 `Settings` $\rightarrow$ `General` 하단의 Danger Zone에서 리포지토리를 **Public**으로 변경합니다.
3. 리포지토리의 `Settings` $\rightarrow$ `Pages` 로 이동하여 **Source**를 `main` 브랜치로 설정합니다. (GitHub Pages 활성화)
4. `Actions` 탭으로 이동하여 **"I understand my workflows, go ahead and enable them"**을 클릭하여 자동 실행 스케줄러를 활성화합니다.
5. 완료 후 `https://[본인계정].github.io/[리포지토리이름]/` 에 접속하면 매일 갱신되는 나만의 퀀트 대시보드가 열립니다.

---

## ⚠️ 면책 조항 (Disclaimer)

본 프로젝트가 제공하는 모든 데이터와 타점 정보는 시스템 알고리즘에 의한 기술적 분석 결과일 뿐이며, 투자 권유나 종목 추천이 아닙니다. 이 스캐너의 정보를 활용한 주식 거래의 모든 책임은 전적으로 투자자 본인에게 있습니다.
