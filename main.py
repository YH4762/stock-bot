import opendartreader
import pandas as pd
import os
import requests
import time
from datetime import datetime

# -----------------------------------------------------------
# 1. 환경변수(Secrets) 로드
# -----------------------------------------------------------
print("🔄 [시스템 시작] 환경변수 및 API 키 확인 중...")

DART_API_KEY = os.environ.get('DART_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

if DART_API_KEY is None:
    print("❌ [오류] DART_API_KEY가 없습니다. Secrets 설정을 확인하세요.")
    exit(1)
else:
    DART_API_KEY = DART_API_KEY.strip()

# -----------------------------------------------------------
# 2. DART 객체 초기화
# -----------------------------------------------------------
try:
    dart = opendartreader.OpenDartReader(DART_API_KEY)
    print("✅ DART 서버 연결 성공!")
except Exception as e:
    print(f"❌ [오류] DART 객체 생성 실패: {e}")
    exit(1)

# -----------------------------------------------------------
# 3. 전체 상장사 리스트 가져오기
# -----------------------------------------------------------
print("📥 전체 기업 리스트를 다운로드하고 있습니다... (약 1~2분 소요)")
try:
    all_corps = dart.corp_codes
    target_corps_df = all_corps[all_corps['stock_code'].notnull()]
    total_count = len(target_corps_df)
    print(f"✅ 분석 대상: 총 {total_count}개의 상장 기업을 찾았습니다.")
except Exception as e:
    print(f"❌ 기업 리스트 가져오기 실패: {e}")
    exit(1)

FILE_NAME = 'financial_db.csv'

# -----------------------------------------------------------
# 4. 유틸리티 함수 (문자열 -> 숫자 변환)
# -----------------------------------------------------------
def str_to_int(text):
    """'1,234,000' 같은 문자열을 정수(1234000)로 변환"""
    if not text:
        return 0
    try:
        # 괄호나 공백 제거 및 콤마 제거
        clean_text = text.replace(",", "").replace("(", "-").replace(")", "").strip()
        return int(clean_text)
    except:
        return 0

def format_diff(value):
    """숫자를 (+100) 또는 (-100) 형태의 문자열로 변환"""
    if value > 0:
        return f"(+{value:,})"
    elif value < 0:
        return f"({value:,})"
    else:
        return "(-)"

# -----------------------------------------------------------
# 5. 데이터 수집 및 알림 함수
# -----------------------------------------------------------
def send_slack_message(msg):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
    except Exception as e:
        print(f"❌ 슬랙 전송 실패: {e}")

def get_financial_data(corp_code, corp_name):
    try:
        current_year = datetime.now().year
        # 1차 시도: 올해 데이터
        report = dart.finstate(corp_code, current_year)
        
        # 2차 시도: 없으면 작년 데이터
        if report is None:
            report = dart.finstate(corp_code, current_year - 1)

        if report is None:
            return None

        # 데이터를 담을 딕셔너리 초기화
        result = {
            'corp_code': corp_code,
            'corp_name': corp_name,
            'rcept_no': '0',
            'date': datetime.now().strftime('%Y-%m-%d'),
            # 당기 금액
            'revenue': '0', 'profit': '0', 'net_income': '0',
            # 증감액 (Diff)
            'revenue_diff': 0, 'profit_diff': 0, 'net_income_diff': 0
        }

        # 접수번호 확인
        if not report.empty:
            result['rcept_no'] = report['rcept_no'].values[0]

        # -------------------------------------------------------
        # 데이터 추출 로직 (매출, 영업이익, 순이익)
        # -------------------------------------------------------
        targets = [
            ('매출액', 'revenue', 'revenue_diff'),
            ('영업이익', 'profit', 'profit_diff'),
            ('당기순이익', 'net_income', 'net_income_diff')
        ]

        for account_nm, field_val, field_diff in targets:
            # 연결재무제표(CFS) 우선 검색, 없으면 별도(OFS)
            row = report.loc[(report['account_nm'] == account_nm) & (report['fs_div'] == 'CFS')]
            if row.empty:
                row = report.loc[(report['account_nm'] == account_nm) & (report['fs_div'] == 'OFS')]
            
            if not row.empty:
                # 당기 금액 (This Term)
                thstrm = str_to_int(row['thstrm_amount'].values[0])
                # 전기 금액 (Former Term) - 비교 대상
                frmtrm = str_to_int(row['frmtrm_amount'].values[0])
                
                # 저장용 데이터 (문자열)
                result[field_val] = str(thstrm)
                # 차액 계산 (당기 - 전기)
                result[field_diff] = thstrm - frmtrm

        return result

    except Exception as e:
        return None

# -----------------------------------------------------------
# 6. 메인 루프
# -----------------------------------------------------------
# 기존 CSV 파일 로드 (컬럼이 늘어났으므로 재설정 필요할 수 있음)
if os.path.exists(FILE_NAME):
    try:
        df_old = pd.read_csv(FILE_NAME, dtype={'rcept_no': str})
        # 구버전 파일이라 새 컬럼(diff)이 없으면 에러 날 수 있으므로 컬럼 확인
        if 'revenue_diff' not in df_old.columns:
            df_old = pd.DataFrame(columns=['corp_code', 'corp_name', 'rcept_no', 'date', 
                                         'revenue', 'revenue_diff', 
                                         'profit', 'profit_diff', 
                                         'net_income', 'net_income_diff'])
    except:
        df_old = pd.DataFrame(columns=['corp_code', 'corp_name', 'rcept_no', 'date', 
                                     'revenue', 'revenue_diff', 
                                     'profit', 'profit_diff', 
                                     'net_income', 'net_income_diff'])
    
    old_rcept_list = df_old['rcept_no'].tolist()
else:
    df_old = pd.DataFrame(columns=['corp_code', 'corp_name', 'rcept_no', 'date', 
                                 'revenue', 'revenue_diff', 
                                 'profit', 'profit_diff', 
                                 'net_income', 'net_income_diff'])
    old_rcept_list = []

new_data_list = []
updated_count = 0

print("\n🚀 데이터 수집 시작 (전체 상장사 검색)...")

for idx, row in target_corps_df.iterrows():
    code = row['corp_code']
    name = row['corp_name']
    
    if idx % 100 == 0:
        print(f"⏳ 진행 중... ({idx}/{total_count})")

    data = get_financial_data(code, name)
    
    if data:
        if data['rcept_no'] not in old_rcept_list and data['rcept_no'] != "0":
            print(f"✨ [NEW] {name} 공시 발견!")
            
            # ---------------------------------------------------
            # 슬랙 메시지 포맷팅 (금액 + 증감)
            # ---------------------------------------------------
            rev_str = f"{int(data['revenue']):,}원 {format_diff(data['revenue_diff'])}"
            prof_str = f"{int(data['profit']):,}원 {format_diff(data['profit_diff'])}"
            net_str = f"{int(data['net_income']):,}원 {format_diff(data['net_income_diff'])}"

            msg = (f"📢 *DART 알림: {name} 실적발표*\n"
                   f"💰 매출액: {rev_str}\n"
                   f"📈 영업이익: {prof_str}\n"
                   f"💵 당기순이익: {net_str}")
            
            send_slack_message(msg)
            
            new_data_list.append(data)
            updated_count += 1
            time.sleep(0.1)

# -----------------------------------------------------------
# 7. 결과 저장
# -----------------------------------------------------------
print(f"\n🏁 수집 종료. 총 {updated_count}건의 새로운 공시를 찾았습니다.")

if updated_count > 0:
    df_new = pd.DataFrame(new_data_list)
    # 기존 데이터와 병합 전 컬럼 순서 통일
    df_final = pd.concat([df_old, df_new], ignore_index=True)
    df_final.to_csv(FILE_NAME, index=False)
    print("💾 financial_db.csv 업데이트 및 저장 완료.")
else:
    print("💤 업데이트할 내역이 없습니다.")
