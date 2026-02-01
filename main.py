import OpenDartReader
import pandas as pd
import os
import requests
import time
from datetime import datetime, timedelta

# -----------------------------------------------------------
# 1. 설정 및 초기화
# -----------------------------------------------------------
print("🚀 [스마트 모드] 불필요한 조회 없이 '오늘의 공시'만 확인합니다.")

DART_API_KEY = os.environ.get('DART_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

if DART_API_KEY is None:
    print("❌ API 키가 없습니다. 설정(Secrets)을 확인해주세요.")
    exit(1)

try:
    dart = OpenDartReader(DART_API_KEY.strip())
except Exception as e:
    print(f"❌ DART 연결 실패: {e}")
    exit(1)

# -----------------------------------------------------------
# 2. 유틸리티 함수
# -----------------------------------------------------------
def send_slack(msg):
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        except: pass

def str_to_int(text):
    try:
        return int(str(text).replace(",", "").replace("(", "-").replace(")", "").strip())
    except:
        return 0

def format_diff(val):
    return f"(+{val:,})" if val > 0 else f"({val:,})" if val < 0 else "(-)"

# -----------------------------------------------------------
# 3. 핵심 로직: 11만 개 다 안 뒤지고, '오늘 리스트'만 조회
# -----------------------------------------------------------
# 오늘 날짜 구하기 (YYYYMMDD 포맷)
today_str = datetime.now().strftime('%Y%m%d')

print(f"📅 검색 일자: {today_str}")
print("🔍 DART 서버에 '오늘 올라온 공시' 리스트를 요청 중...")

try:
    # 여기가 핵심입니다! 기업마다 묻지 않고, 오늘 전체 리스트를 딱 1번만 받아옵니다.
    # kind='A': 정기공시(사업, 분기, 반기 보고서 등 실적 관련)
    report_list = dart.list(start=today_str, end=today_str, kind='A')
    
    # 공시가 아예 없는 경우 (주말, 공휴일, 장 시작 전)
    if report_list is None or report_list.empty:
        print("✅ 결과: 오늘 올라온 정기 공시(실적 발표)가 없습니다.")
        print("   (주말이거나, 아직 공시가 올라오지 않았습니다. 정상입니다.)")
        exit(0)

    # 보고서 제목에 '보고서'나 '실적'이 들어간 것만 필터링
    # 그리고 'stock_code'가 있는(상장사) 경우만 남김
    target_reports = report_list[
        (report_list['stock_code'].notnull()) & 
        (report_list['report_nm'].str.contains('보고서|실적', na=False))
    ]
    
    count = len(target_reports)
    print(f"🔎 오늘 발견된 상장사 실적 공시: 총 {count}건")

except Exception as e:
    print(f"❌ 공시 리스트 조회 중 오류: {e}")
    # 혹시 리스트 조회 자체가 안되면 여기서 멈춤
    exit(1)

# -----------------------------------------------------------
# 4. 발견된 건에 대해서만 상세 내용 털기 (API 절약)
# -----------------------------------------------------------
if count == 0:
    print("💤 실적 관련 공시는 발견되지 않았습니다.")
    exit(0)

print(f"🔥 발견된 {count}개 기업의 재무제표를 분석합니다...")

# CSV 파일 로드 (중복 발송 방지용)
FILE_NAME = 'financial_db.csv'
if os.path.exists(FILE_NAME):
    df_old = pd.read_csv(FILE_NAME, dtype={'rcept_no': str})
    old_rcepts = df_old['rcept_no'].tolist()
else:
    old_rcepts = []

new_data_list = []

for idx, row in target_reports.iterrows():
    corp_name = row['corp_name']
    corp_code = row['corp_code']
    rcept_no = row['rcept_no']
    
    # 이미 보낸 거면 패스
    if rcept_no in old_rcepts:
        continue

    print(f"   👉 분석 중: {corp_name} ...")
    
    try:
        # 재무제표 가져오기
        current_year = datetime.now().year
        fs = dart.finstate(corp_code, current_year)
        if fs is None:
            fs = dart.finstate(corp_code, current_year - 1)
        
        if fs is None:
            print(f"      -> 재무 데이터 없음 (패스)")
            continue

        # 데이터 추출 (매출, 영업이익, 순이익)
        targets = [('매출액', 'rev'), ('영업이익', 'prof'), ('당기순이익', 'net')]
        msg_lines = [f"📢 *DART 알림: {corp_name}*"]
        has_data = False
        
        save_row = {'rcept_no': rcept_no, 'corp_name': corp_name, 'date': today_str}

        for account_nm, key in targets:
            # 연결(CFS) 우선, 없으면 별도(OFS)
            data = fs.loc[(fs['account_nm'] == account_nm) & (fs['fs_div'] == 'CFS')]
            if data.empty:
                data = fs.loc[(fs['account_nm'] == account_nm) & (fs['fs_div'] == 'OFS')]
            
            if not data.empty:
                this_val = str_to_int(data['thstrm_amount'].values[0])
                prev_val = str_to_int(data['frmtrm_amount'].values[0])
                diff = this_val - prev_val
                
                msg_lines.append(f"- {account_nm}: {this_val:,}원 {format_diff(diff)}")
                save_row[key] = this_val
                has_data = True

        if has_data:
            send_slack("\n".join(msg_lines))
            new_data_list.append(save_row)
            print(f"      ✅ 슬랙 전송 완료")
            time.sleep(1) # 슬랙 도배 방지 1초 대기

    except Exception as e:
        print(f"      ⚠️ 에러 무시하고 계속 진행: {e}")

# -----------------------------------------------------------
# 5. 마무리 저장
# -----------------------------------------------------------
if new_data_list:
    df_new = pd.DataFrame(new_data_list)
    if os.path.exists(FILE_NAME):
        df_new.to_csv(FILE_NAME, mode='a', header=False, index=False)
    else:
        df_new.to_csv(FILE_NAME, index=False)
    print(f"💾 {len(new_data_list)}건 저장 완료. 퇴근합니다.")
else:
    print("🏁 분석 완료. 새로 전송할 내역이 없습니다.")
