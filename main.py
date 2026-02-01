import OpenDartReader
import pandas as pd
import os
import requests
import time
from datetime import datetime

# -----------------------------------------------------------
# 1. 설정 및 초기화
# -----------------------------------------------------------
print("🚀 [스마트 모드] 시스템 가동 시작...")

DART_API_KEY = os.environ.get('DART_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

# 슬랙 전송 함수 (가장 먼저 정의)
def send_slack(msg):
    if SLACK_WEBHOOK_URL:
        try:
            print(f"🔔 슬랙 전송: {msg[:20]}...")
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        except Exception as e:
            print(f"❌ 슬랙 전송 실패: {e}")

# API 키 확인
if DART_API_KEY is None:
    err_msg = "❌ [오류] API 키가 없습니다. 설정(Secrets)을 확인해주세요."
    print(err_msg)
    send_slack(err_msg) # 에러나도 알려줌
    exit(1)

try:
    dart = OpenDartReader(DART_API_KEY.strip())
except Exception as e:
    err_msg = f"❌ [오류] DART 연결 실패: {e}"
    print(err_msg)
    send_slack(err_msg)
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

# -----------------------------------------------------------
# 3. 핵심 로직: '오늘 리스트'만 1회 조회 (API 절약)
# -----------------------------------------------------------
# 오늘 날짜 구하기
today_str = datetime.now().strftime('%Y%m%d')

print(f"📅 검색 일자: {today_str}")

try:
    # ★ 전체 기업(11만개)을 돌지 않고, 오늘 올라온 리스트만 딱 받아옵니다.
    print("🔍 DART 서버에 '오늘의 공시'를 요청 중...")
    report_list = dart.list(start=today_str, end=today_str, kind='A') # kind='A': 정기공시
    
    # 1. 오늘 올라온 공시가 아예 없는 경우 (주말 등)
    if report_list is None or report_list.empty:
        msg = f"💤 [DART] {today_str}일자 실적 공시가 없습니다. (주말/공휴일)"
        print(msg)
        send_slack(msg) # <--- 종료 알림 추가
        exit(0)

    # 2. 공시는 있는데 '실적/보고서' 관련이 아닌 경우 필터링
    # stock_code가 있는(상장사) 경우만 남김
    target_reports = report_list[
        (report_list['stock_code'].notnull()) & 
        (report_list['report_nm'].str.contains('보고서|실적', na=False))
    ]
    
    count = len(target_reports)
    
    if count == 0:
        msg = f"💤 [DART] 오늘 공시는 있지만, 분석할 '실적 보고서'는 없습니다."
        print(msg)
        send_slack(msg) # <--- 종료 알림 추가
        exit(0)

    print(f"🔎 오늘 분석할 실적 공시: 총 {count}건")

except Exception as e:
    err_msg = f"❌ 공시 리스트 조회 중 오류 발생: {e}"
    print(err_msg)
    send_slack(err_msg)
    exit(1)

# -----------------------------------------------------------
# 4. 상세 분석 및 알림 발송
# -----------------------------------------------------------
# 중복 방지용 파일 로드
FILE_NAME = 'financial_db.csv'
if os.path.exists(FILE_NAME):
    df_old = pd.read_csv(FILE_NAME, dtype={'rcept_no': str})
    old_rcepts = df_old['rcept_no'].tolist()
else:
    old_rcepts = []

success_count = 0
error_count = 0

print(f"🔥 {count}개 기업 데이터 상세 분석 시작...")

for idx, row in target_reports.iterrows():
    corp_name = row['corp_name']
    corp_code = row['corp_code']
    rcept_no = row['rcept_no']
    
    # 이미 알림 보낸 공시면 패스
    if rcept_no in old_rcepts:
        print(f"   -> {corp_name}: 이미 전송함 (Skip)")
        continue

    try:
        # 재무제표 가져오기
        current_year = datetime.now().year
        fs = dart.finstate(corp_code, current_year)
        if fs is None:
            fs = dart.finstate(corp_code, current_year - 1)
        
        if fs is None:
            continue

        # 데이터 추출
        targets = [('매출액', 'rev'), ('영업이익', 'prof'), ('당기순이익', 'net')]
        msg_lines = [f"📢 *DART 알림: {corp_name}*"]
        has_data = False
        
        # CSV 저장용 데이터
        save_row = {'rcept_no': rcept_no, 'corp_name': corp_name, 'date': today_str}

        for account_nm, key in targets:
            # 연결(CFS) -> 별도(OFS)
            data = fs.loc[(fs['account_nm'] == account_nm) & (fs['fs_div'] == 'CFS')]
            if data.empty:
                data = fs.loc[(fs['account_nm'] == account_nm) & (fs['fs_div'] == 'OFS')]
            
            if not data.empty:
                this_val = str_to_int(data['thstrm_amount'].values[0])
                prev_val = str_to_int(data['frmtrm_amount'].values[0])
                diff = this_val - prev_val
                
                msg_lines.append(f"- {account_nm}: {this_val:,}원 {format_diff(diff)}")
                has_data = True

        if has_data:
            # 슬랙 전송
            send_slack("\n".join(msg_lines))
            
            # CSV 저장 (실시간 저장)
            df_new = pd.DataFrame([save_row])
            if os.path.exists(FILE_NAME):
                df_new.to_csv(FILE_NAME, mode='a', header=False, index=False)
            else:
                df_new.to_csv(FILE_NAME, index=False)
                
            success_count += 1
            print(f"   ✅ {corp_name} 알림 전송 완료")
            time.sleep(1) # 도배 방지

    except Exception as e:
        print(f"   ⚠️ {corp_name} 처리 중 에러: {e}")
        error_count += 1

# -----------------------------------------------------------
# 5. [중요] 모든 작업 완료 후 최종 보고
# -----------------------------------------------------------
finish_msg = (f"🏁 [작업 완료] 오늘의 스캔이 끝났습니다.\n"
              f"- 검색된 공시: {count}건\n"
              f"- 전송 성공: {success_count}건\n"
              f"- 에러/스킵: {error_count}건")

print(finish_msg)
send_slack(finish_msg) # <--- 마지막에 무조건 슬랙 보냄
