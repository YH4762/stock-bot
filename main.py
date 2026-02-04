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

# 환경변수에서 키 가져오기 (GitHub Secrets 등 활용)
DART_API_KEY = os.environ.get('DART_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

# 슬랙 전송 함수
def send_slack(msg):
    if SLACK_WEBHOOK_URL:
        try:
            print(f"🔔 슬랙 전송: {msg[:30]}...")
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        except Exception as e:
            print(f"❌ 슬랙 전송 실패: {e}")

# API 키 확인
if DART_API_KEY is None:
    err_msg = "❌ [오류] API 키가 없습니다. 환경변수 설정을 확인해주세요."
    print(err_msg)
    send_slack(err_msg)
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
    """문자열(1,000) 등을 정수형으로 변환"""
    try:
        return int(str(text).replace(",", "").replace("(", "-").replace(")", "").strip())
    except:
        return 0

def format_diff(val):
    """증감액 포맷팅 (+100, -100)"""
    return f"(+{val:,})" if val > 0 else f"({val:,})" if val < 0 else "(-)"

def get_period_from_name(report_nm):
    """보고서 이름에서 분기(Quarter) 추출"""
    if "1분기" in report_nm: return "1Q"
    elif "반기" in report_nm: return "2Q"
    elif "3분기" in report_nm: return "3Q"
    elif "사업보고서" in report_nm: return "4Q"
    return None

# -----------------------------------------------------------
# 3. 오늘의 공시 리스트 조회
# -----------------------------------------------------------
today_str = datetime.now().strftime('%Y%m%d')
print(f"📅 검색 일자: {today_str}")

try:
    # kind='A': 정기공시 (사업/분기/반기 보고서 등)
    print("🔍 DART 서버에 '오늘의 공시'를 요청 중...")
    report_list = dart.list(start=today_str, end=today_str, kind='A') 
    
    # 1. 공시 없음
    if report_list is None or report_list.empty:
        msg = f"💤 [DART] {today_str}일자 실적 공시가 없습니다."
        print(msg)
        exit(0)

    # 2. 실적 보고서만 필터링 (상장사 & 보고서 키워드)
    target_reports = report_list[
        (report_list['stock_code'].notnull()) & 
        (report_list['report_nm'].str.contains('보고서|실적', na=False))
    ]
    
    count = len(target_reports)
    if count == 0:
        msg = f"💤 [DART] 오늘 공시는 있지만, 분석할 실적 보고서는 없습니다."
        print(msg)
        exit(0)

    print(f"🔎 오늘 분석할 실적 공시: 총 {count}건")

except Exception as e:
    err_msg = f"❌ 공시 리스트 조회 중 오류 발생: {e}"
    print(err_msg)
    send_slack(err_msg)
    exit(1)

# -----------------------------------------------------------
# 4. 상세 분석 및 데이터 저장 (중복 방지 포함)
# -----------------------------------------------------------
FILE_NAME = 'financial_db.csv'
success_count = 0
error_count = 0

print(f"🔥 {count}개 기업 데이터 상세 분석 시작...")

for idx, row in target_reports.iterrows():
    corp_name = row['corp_name']
    corp_code = row['corp_code']
    report_nm = row['report_nm']
    rcept_no = row['rcept_no'] # 접수번호 (고유값)
    
    # 연도와 분기 식별
    quarter = get_period_from_name(report_nm)
    # 보고서 이름에 연도가 없으면 오늘 날짜 기준 연도 사용 (단순화)
    year = datetime.now().year 
    # 4Q(사업보고서)는 보통 다음 해에 나오므로 연도 보정이 필요할 수 있으나, 
    # 여기서는 데이터의 '접수일 기준' 혹은 보고서 내 '기수'를 따르는 게 정확함.
    # 편의상 수집 시점의 연도를 사용하되, 필요 시 보정 로직 추가 가능.

    if not quarter:
        continue # 분기를 알 수 없는 보고서(정정신고 등)는 스킵

    try:
        # 재무제표 가져오기 (연결 -> 별도 순)
        fs = dart.finstate(corp_code, year) # API 호출
        if fs is None:
            # 올해 데이터가 아직 없으면 작년 기준으로 재시도 (API 특성 고려)
            fs = dart.finstate(corp_code, year - 1)
        
        if fs is None:
            continue

        # 데이터 추출 (매출, 영업이익, 순이익)
        # (DART 표준 계정명 사용)
        accounts = {
            '매출액': 'revenue', 
            '영업이익': 'profit', 
            '당기순이익': 'net_income',
            '영업활동현금흐름': 'cash_flow' # 필요 시 추가
        }
        
        save_row = {
            'corp_code': corp_code,
            'corp_name': corp_name,
            'year': year,
            'quarter': quarter,
            'revenue': 0, 'profit': 0, 'net_income': 0, 'cash_flow': 0 # 초기화
        }
        
        msg_lines = [f"📢 *{corp_name} {year}년 {quarter} 잠정실적*"]
        has_valuable_data = False

        for ac_kor, ac_eng in accounts.items():
            # 1. 연결재무제표(CFS) 우선 검색
            data = fs.loc[(fs['account_nm'] == ac_kor) & (fs['fs_div'] == 'CFS')]
            # 2. 없으면 별도재무제표(OFS) 검색
            if data.empty:
                data = fs.loc[(fs['account_nm'] == ac_kor) & (fs['fs_div'] == 'OFS')]
            
            if not data.empty:
                # 당기 금액 (This Term Amount)
                val = str_to_int(data['thstrm_amount'].values[0])
                save_row[ac_eng] = val # 딕셔너리에 저장
                
                # 메시지 작성용 (전기 대비 증감 등)
                prev_val = str_to_int(data['frmtrm_amount'].values[0])
                diff = val - prev_val
                msg_lines.append(f"- {ac_kor}: {val:,}원 {format_diff(diff)}")
                
                if val != 0: has_valuable_data = True

        # -----------------------------------------------------------
        # [핵심] 중복 방지 및 저장 로직
        # -----------------------------------------------------------
        if has_valuable_data:
            # 1. 슬랙 알림 발송
            send_slack("\n".join(msg_lines))
            
            # 2. 중복 검사
            save_allowed = True
            
            if os.path.exists(FILE_NAME):
                try:
                    df_existing = pd.read_csv(FILE_NAME)
                    # 동일 기업 + 동일 연도 + 동일 분기 데이터가 있는지 확인
                    check = df_existing[
                        (df_existing['corp_name'] == corp_name) & 
                        (df_existing['year'] == year) & 
                        (df_existing['quarter'] == quarter)
                    ]
                    
                    if not check.empty:
                        save_allowed = False
                        print(f"   ⚠️ [Skip] {corp_name} {year} {quarter} 데이터 중복 (저장 안 함)")
                except Exception as e:
                    print(f"   ⚠️ 파일 읽기 오류 (덮어쓰기 시도): {e}")

            # 3. CSV 저장
            if save_allowed:
                df_new = pd.DataFrame([save_row])
                
                # 파일이 없으면 헤더 포함 저장, 있으면 헤더 제외하고 내용만 추가(mode='a')
                if not os.path.exists(FILE_NAME):
                    df_new.to_csv(FILE_NAME, index=False, encoding='utf-8-sig')
                else:
                    df_new.to_csv(FILE_NAME, mode='a', header=False, index=False, encoding='utf-8-sig')
                
                print(f"   💾 {corp_name} 데이터 저장 완료")
                success_count += 1
            
            time.sleep(1) # API 호출 제한 고려

    except Exception as e:
        print(f"   ⚠️ {corp_name} 처리 중 에러: {e}")
        error_count += 1

# -----------------------------------------------------------
# 5. 최종 리포트
# -----------------------------------------------------------
finish_msg = (f"🏁 [작업 완료] 오늘의 공시 스캔 종료\n"
              f"- 대상: {count}건\n"
              f"- 저장/전송: {success_count}건\n"
              f"- 에러/스킵: {error_count}건")
print(finish_msg)
