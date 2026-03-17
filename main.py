import OpenDartReader
import pandas as pd
import os
import requests
import time
from datetime import datetime
import re

# -----------------------------------------------------------
# 1. 설정 및 초기화
# -----------------------------------------------------------
print("🚀 [데일리 모드] 시스템 가동 시작...")

DART_API_KEY = os.environ.get('DART_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

# 슬랙 전송 함수 (결과 로그 확인 기능 보강)
def send_slack(msg):
    if SLACK_WEBHOOK_URL:
        try:
            print(f"🔔 슬랙 전송 시도: {msg[:30]}...")
            response = requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
            # 슬랙 서버 응답 결과 출력 (성공 시 200 ok)
            if response.status_code == 200:
                print(f"✅ 슬랙 전송 성공! (상태 코드: {response.status_code})")
            else:
                print(f"⚠️ 슬랙 전송 응답 이상: {response.status_code}, {response.text}")
        except Exception as e:
            print(f"❌ 슬랙 전송 중 물리적 에러 발생: {e}")
    else:
        print("⚠️ SLACK_WEBHOOK_URL 설정이 없어 알림을 건너뜁니다.")

if DART_API_KEY is None:
    print("❌ [오류] API 키가 없습니다.")
    exit(1)

try:
    dart = OpenDartReader(DART_API_KEY.strip())
except Exception as e:
    print(f"❌ [오류] DART 연결 실패: {e}")
    exit(1)

# -----------------------------------------------------------
# 2. 유틸리티 함수
# -----------------------------------------------------------
def str_to_int(text):
    try:
        return int(str(text).replace(",", "").replace("(", "-").replace(")", "").strip())
    except:
        return 0

def format_diff(val):
    return f"(+{val:,})" if val > 0 else f"({val:,})" if val < 0 else "(-)"

def get_period_from_name(report_nm):
    if "1분기" in report_nm: return "1Q"
    elif "반기" in report_nm: return "2Q"
    elif "3분기" in report_nm: return "3Q"
    elif "사업보고서" in report_nm: return "4Q"
    return None

# -----------------------------------------------------------
# 3. 오늘의 공시 리스트 조회 (데일리 모드로 원복)
# -----------------------------------------------------------
# 실행 시점의 '오늘' 날짜를 자동으로 가져옵니다.
today_str = datetime.now().strftime('%Y%m%d')
print(f"📅 검색 일자: {today_str}")

try:
    # 정기공시(kind='A') 조회 (시작과 끝을 오늘로 설정)
    report_list = dart.list(start=today_str, end=today_str, kind='A') 
    
    if report_list is None or report_list.empty:
        print(f"💤 {today_str}일자 실적 공시가 없습니다. 작업을 종료합니다.")
        exit(0)

    target_reports = report_list[
        (report_list['stock_code'].notnull()) & 
        (report_list['report_nm'].str.contains('보고서|실적', na=False))
    ]
    
    count = len(target_reports)
    if count == 0:
        print(f"💤 분석할 실적 보고서가 없습니다.")
        exit(0)

    print(f"🔎 총 {count}건의 공시 분석 시작")

except Exception as e:
    print(f"❌ 공시 조회 중 오류: {e}")
    exit(1)

# -----------------------------------------------------------
# 4. 상세 분석 및 데이터 저장
# -----------------------------------------------------------
FILE_NAME = 'financial_db.csv'
success_count = 0
error_count = 0

for idx, row in target_reports.iterrows():
    corp_name = row['corp_name']
    corp_code = row['corp_code']
    report_nm = row['report_nm']
    
    quarter = get_period_from_name(report_nm)
    if not quarter: continue

    year_match = re.search(r'\((\d{4})\.', report_nm)
    if year_match:
        year = int(year_match.group(1))
    else:
        current_month = datetime.now().month
        year = datetime.now().year
        if quarter == '4Q' and current_month <= 3:
            year -= 1

    try:
        # 중복 체크
        if os.path.exists(FILE_NAME):
            df_existing = pd.read_csv(FILE_NAME)
            check = df_existing[
                (df_existing['corp_name'] == corp_name) & 
                (df_existing['year'] == year) & 
                (df_existing['quarter'] == quarter)
            ]
            if not check.empty:
                print(f"   ⚠️ [Skip] {corp_name} {year} {quarter} 이미 존재함")
                continue

        # 재무데이터 가져오기
        fs = dart.finstate(corp_code, year)
        if fs is None:
            fs = dart.finstate(corp_code, year - 1)
        
        if fs is None: continue

        accounts = {'매출액': 'revenue', '영업이익': 'profit', '당기순이익': 'net_income'}
        save_row = {'corp_code': corp_code, 'corp_name': corp_name, 'year': year, 'quarter': quarter}
        
        msg_lines = [f"📢 *{corp_name} {year}년 {quarter} 실적*"]
        has_data = False

        for ac_kor, ac_eng in accounts.items():
            data = fs.loc[(fs['account_nm'] == ac_kor) & (fs['fs_div'] == 'CFS')]
            if data.empty:
                data = fs.loc[(fs['account_nm'] == ac_kor) & (fs['fs_div'] == 'OFS')]
            
            if not data.empty:
                val = str_to_int(data['thstrm_amount'].values[0])
                save_row[ac_eng] = val
                prev_val = str_to_int(data['frmtrm_amount'].values[0])
                msg_lines.append(f"- {ac_kor}: {val:,}원 {format_diff(val - prev_val)}")
                if val != 0: has_data = True

        if has_data:
            df_new = pd.DataFrame([save_row])
            if not os.path.exists(FILE_NAME):
                df_new.to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
            else:
                df_new.to_csv(FILE_NAME, mode='a', header=False, index=False, encoding='utf-8-sig')
            
            send_slack("\n".join(msg_lines))
            print(f"   💾 {corp_name} 저장 완료")
            success_count += 1
            time.sleep(0.5)

    except Exception as e:
        print(f"   ⚠️ {corp_name} 에러: {e}")
        error_count += 1

print(f"🏁 작업 완료! (저장: {success_count}, 스킵/에러: {error_count})")
