# 🤖 DART Stock Bot (Smart Auto-Notifier)

대한민국 주식시장(KOSPI, KOSDAQ)에 상장된 **모든 기업의 실적 발표**를 실시간으로 감시하고, **Slack으로 알림**을 보내주는 자동화 봇입니다.
GitHub Actions를 통해 서버 없이 **100% 무료**로 구동되며, 불필요한 조회를 최소화한 **'스마트 스캔'** 방식으로 단 10초 만에 분석을 마칩니다.

## DAILY UPDATE FILE LOCATOIN 업뎃파일
- financial_db.csv

## ✨ 주요 기능 (Key Features)

* **⚡ 초고속 스마트 스캔**: 3,700개 기업을 전수조사하지 않고, DART 서버에 **"오늘 올라온 공시 목록"**만 요청하여 API 사용량을 획기적으로 절약합니다. (실행 시간 약 10초)
* **📢 Slack 실시간 알림**: 새로운 실적 공시(매출액, 영업이익, 당기순이익)가 뜨면 즉시 슬랙으로 메시지를 보냅니다.
* **📉 전분기 대비 증감(YoY/QoQ) 자동 계산**: 단순 수치뿐만 아니라, 직전 기간 대비 얼마가 올랐는지 `(+30억)`, `(-5억)` 형태로 직관적으로 보여줍니다.
* **💾 데이터 자동 축적**: 한 번 알림을 보낸 공시는 `financial_db.csv` 파일에 자동 저장되어 중복 알림을 방지합니다.
* **⏰ 완전 자동화**: 평일 아침/저녁 지정된 시간에 봇이 알아서 깨어나 공시를 확인하고 퇴근합니다.

## 🛠️ 사용된 기술 (Tech Stack)

* **Language**: Python 3.9+
* **Libraries**: `OpenDartReader`, `pandas`, `requests`
* **Infrastructure**: GitHub Actions (Scheduled Cron Job)
* **Data Source**: 금융감독원 DART API

## 🚀 설치 및 설정 방법 (Setup)

### 1. 필수 준비물
* **DART API 키**: [DART Open API](https://opendart.fss.or.kr/)에서 발급 (무료)
* **Slack Webhook URL**: Slack 채널 설정에서 'Incoming Webhook' 생성

### 2. GitHub Secrets 설정
보안을 위해 API 키는 코드에 직접 적지 않고 GitHub Secrets에 저장합니다.
1.  GitHub 저장소 상단 메뉴 **Settings** 클릭
2.  왼쪽 메뉴 **Secrets and variables** > **Actions** 클릭
3.  **New repository secret** 버튼 클릭 후 아래 2개 추가:
    * Name: `DART_API_KEY` / Value: (본인의 DART API 키)
    * Name: `SLACK_WEBHOOK_URL` / Value: (본인의 슬랙 웹훅 URL)

### 3. 작동 시간 변경 (옵션)
`.github/workflows/dart_update.yml` 파일에서 `cron` 시간을 수정하여 원하는 시간에 실행할 수 있습니다.
(기본 설정: 한국 시간 기준 오전/오후 주기적 실행)

## 📂 파일 구조 (File Structure)

```text
📦 stock-bot
 ┣ 📂 .github/workflows
 ┃ ┗ 📜 dart_update.yml    # 봇 자동 실행 스케줄러 (GitHub Actions)
 ┣ 📜 main.py              # 핵심 로직 (공시 조회 및 알림 발송)
 ┣ 📜 financial_db.csv     # 발송 내역 저장소 (중복 방지용 DB)
 ┗ 📜 README.md            # 프로젝트 설명서
