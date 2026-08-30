# 🎯 4-Core US Stock Swing Scanner
**미국 주식(S&P 500 + NASDAQ 100) 무인 자동화 스윙 트레이딩 스캐너 & 대시보드**

![Python](https://img.shields.io/badge/Python-3.10-blue)
![GitHub Actions](https://img.shields.io/badge/Automated_by-GitHub_Actions-2088FF)
![GitHub Pages](https://img.shields.io/badge/Hosted_on-GitHub_Pages-success)

이 프로젝트는 마크 미네르비니(Mark Minervini), 윌리엄 오닐(William O'Neil) 등 월가 최상위 트레이더들의 매매 기법을 파이썬 알고리즘으로 구현한 **100% 무인 자동화 스크리닝 시스템**입니다. 매일 미국 장 마감 후, 600여 개의 우량주 데이터를 분석하여 당장 매수해야 할(Action) 종목과 구조를 만들고 있는(Setup) 종목을 모바일 피드(Feed) 형태로 제공합니다.

🌐 **[모바일 대시보드 바로가기](https://jkshin933.github.io/stock-swing-screener/)** *(자신의 깃허브 주소로 변경)*

---

## ✨ 핵심 기능 (Key Features)

- **🤖 100% 무인 자동화:** GitHub Actions를 통해 평일 미국 장 마감 직후(매일 20:30 UTC) 자동으로 파이썬 엔진이 구동됩니다.
- **📱 모바일 최적화 UI:** 인스타그램 피드처럼 스마트폰에서 스크롤하며 차트와 타점을 확인할 수 있는 직관적인 인터페이스를 제공합니다.
- **🛡️ 우량주 핀셋 필터링:** S급(상위 5%), A급(상위 20%) 주도주만 선별하며, 시가총액 100억 달러($10B) 이상의 대형주 위주로 필터링합니다.
- **🛑 동적 리스크 관리 (Dynamic Stop-Loss):** 고정된 %가 아닌, 각 패턴의 '구조가 붕괴되는 지점'을 수학적으로 계산하여 기계적 손절가를 사전 제시합니다.

---

## 🧠 4대 핵심 매매 전략 (4-Core Strategies)

단순히 보조지표에 닿았다고 매수하는 것이 아니라, **변동성과 거래량의 압축(Contraction)** 및 **유의미한 지지/돌파**를 확인한 후 타점을 잡습니다.

### 1. 📉 20EMA Pullback (눌림목 반등)
- **조건:** Stage 2 상승 추세 종목이 20일 지수이동평균선(20 EMA) 부근까지 거래량 없이 조정을 받음.
- **트리거:** 20 EMA 지지 확인 후, 시가와 전일 종가를 모두 돌파하는 양봉(Reclaim) 발생 시 매수.

### 2. 🎯 VCP (변동성 수축 패턴)
- **조건:** 롤링 윈도우(Rolling Window) 상 고점 대비 하락폭이 단계적으로 줄어들며, 거래량이 완전히 고갈(Dry-up)된 극비수축 상태.
- **트리거:** 수축의 마지막 고점(Tight Pivot)을 평균 거래량의 1.5배 이상으로 강하게 뚫어낼 때 매수.

### 3. 🔄 Breakout & Retest (52주 메이저 돌파-지지)
- **조건:** 과거 52주(200일) 메이저 저항선을 강력하게 돌파했던 종목이 다시 해당 가격대까지 하락함.
- **트리거:** 과거의 저항선이 새로운 지지선으로 작용하여 아래꼬리나 양봉으로 반등을 시작할 때 매수.

### 4. 🔥 Momentum (High Tight Flag)
- **조건:** RS(상대강도) 점수 95 이상의 극강 주도주가 단기간 급등 후, 고점 부근에서 10% 이내의 좁은 박스권(Flag)을 형성하며 횡보함.
- **트리거:** 이 깃발(Flag)형 박스권 상단을 대량 거래량과 함께 재돌파할 때 매수.

---

## ⚙️ 시스템 아키텍처 (System Architecture)

1. **Backend (`screener.py`)**: `yfinance`와 `pandas`를 활용하여 데이터를 수집하고 4-Core 알고리즘 및 상태 머신(State Machine) 로직을 처리합니다.
2. **Database (`state.json`)**: 별도의 서버 DB 없이 JSON 파일을 통해 종목의 과거 상태(이탈일, 진입가 등)를 추적하고 기억합니다.
3. **Frontend (`index.html`)**: HTML/CSS/JS 단일 파일로 구성되며, 생성된 `dashboard_data.json`을 읽어와 다크모드 기반의 모바일 UI를 렌더링합니다.
4. **CI/CD (`scan.yml`)**: GitHub Actions가 스케줄러 역할을 수행하며, 결과를 GitHub Pages로 즉시 배포합니다.

---

## 🚀 직접 구축하는 방법 (How to Fork & Setup)

누구나 이 리포지토리를 포크(Fork)하여 자신만의 무인 스캐너를 만들 수 있습니다.

1. 이 리포지토리를 **Fork** 합니다.
2. 리포지토리의 `Settings` -> `Pages` 로 이동하여 **Source**를 `main` 브랜치로 설정합니다. (GitHub Pages 활성화)
3. 리포지토리의 `Settings` -> `General` 하단의 Danger Zone에서 리포지토리를 **Public**으로 변경합니다.
4. `Actions` 탭으로 이동하여 **"I understand my workflows, go ahead and enable them"**을 클릭합니다.
5. 수동으로 한 번 실행해 보려면, 좌측 `Daily Swing Screener` 클릭 후 **Run workflow**를 실행합니다.
6. 완료 후 `https://[본인계정].github.io/[리포지토리이름]/` 에 접속하면 나만의 대시보드가 열립니다.

---

## ⚠️ 면책 조항 (Disclaimer)

본 프로젝트가 제공하는 모든 데이터와 타점 정보는 시스템 알고리즘에 의한 기술적 분석 결과일 뿐이며, 투자 권유나 종목 추천이 아닙니다. 이 스캐너의 정보를 활용한 주식 거래의 모든 책임은 전적으로 투자자 본인에게 있습니다.
