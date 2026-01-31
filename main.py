import OpenDartReader
import pandas as pd
import os
import requests
import json
from datetime import datetime, timedelta, timezone
import time

# ---------------------------------------------------------
# [설정] GitHub Secrets에서 키를 가져옵니다
# ---------------------------------------------------------
API_KEY = os.environ.get('304b8ce936e5111f1c210ca242816717bf425fcb')
SLACK_URL = os.environ.get('https://hooks.slack.com/services/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')

DB_FILE = 'financial_db.csv'

dart = OpenDartReader(API_KEY)

# ---------------------------------------------------------
# [함수] 슬랙 전송
# ---------------------------------------------------------
def send_slack(msg):
    if not SLACK_URL: return
    try:
        requests.post(SLACK_URL, json={
            "text": msg,
            "icon_emoji": ":chart_with_upwards_trend:"
        })
    except: pass

# ---------------------------------------------------------
# [함수] 데이터 추출
# ---------------------------------------------------------
def get_financials(code, year, r_code):
    try:
        df = dart.finstate_all(code, year, r_code)
        if df is None: return None
        
        def f(keywords):
            for k in keywords:
                row = df[df['account_nm'].str.contains(k, na=False)]
                if not row.empty:
                    val = row.iloc[0]['thstrm_amount']
                    if val == '-' or pd.isna(val): return 0
                    return float(str(val).replace(',', ''))
            return 0
        
        backlog = f(['수주총액', '수주잔고', '계약부채', '공사선수금', '초과청구공사'])
        
        return {
            '매출액': f(['매출액', '수익(매출액)']),
            '영업이익': f(['영업이익', '영업이익(손실)']),
            '순이익': f(['당기순이익', '당기순이익(손실)']),
            '영업현금흐름': f(['영업활동', '현금흐름']),
            '수주잔고': backlog
        }
    except: return None

# ---------------------------------------------------------
# [메인] 실행 로직
# ---------------------------------------------------------
def main():
    # 1. 기존 DB 파일 읽기 (없으면 새로 생성)
    if os.path.exists(DB_FILE):
        db = pd.read_csv(DB_FILE, dtype={'corp_code': str})
        print(f"📂 기존 DB 로드 완료: {len(db)}행")
    else:
        print("📂 기존 DB가 없습니다. 새로 시작합니다.")
        db = pd.DataFrame(columns=['corp_code','corp_name','year','quarter','매출액','영업이익','순이익','영업현금흐름','수주잔고','수주잔고_증감'])

    # 2. 오늘 날짜(KST) 구하기
    kst = timezone(timedelta(hours=9))
    today_dt = datetime.now(kst)
    today_str = today_dt.strftime('%Y%m%d')
    
    print(f"📅 오늘({today_str}) 공시를 확인합니다...")

    # 3. 공시 검색
    filings = dart.list(start=today_str, end=today_str, kind='A') # A=정기공시
    
    if filings is None or filings.empty:
        print("📭 오늘 올라온 실적 공시가 없습니다.")
        return

    new_rows = []
    
    for _, row in filings.iterrows():
        nm = row['report_nm']
        y = today_dt.year
        rc, q = '', ''
        
        # 보고서 종류 구분
        if '1분기' in nm: rc, q = '11013', '1Q'
        elif '반기' in nm: rc, q = '11012', '2Q'
        elif '3분기' in nm: rc, q = '11014', '3Q'
        elif '사업보고서' in nm: rc, q = '11011', '4Q'; y -= 1
        else: continue

        # 이미 DB에 있는 내용이면 건너뜀 (중복 방지)
        if not db.empty:
            is_exist = not db[(db['corp_code'] == row['corp_code']) & (db['year'] == y) & (db['quarter'] == q)].empty
            if is_exist: continue

        print(f"🔍 발견: {row['corp_name']} {q}")
        
        # 데이터 가져오기
        curr_data = get_financials(row['corp_code'], y, rc)
        
        if curr_data:
            # [로직 1] 수주잔고 증감 계산 (DB에서 직전 데이터 찾기)
            prev_backlog = 0
            if not db.empty:
                # 같은 기업의 데이터를 찾아서
                corp_hist = db[db['corp_code'] == row['corp_code']]
                if not corp_hist.empty:
                    # 가장 마지막(최신) 행의 수주잔고를 가져옴
                    prev_backlog = corp_hist.iloc[-1]['수주잔고']
            
            diff = curr_data['수주잔고'] - prev_backlog

            # [로직 2] 4분기 누적 차감 (매출, 이익만)
            if q == '4Q':
                 q3_data = get_financials(row['corp_code'], y, '11014')
                 if q3_data:
                     curr_data['매출액'] -= q3_data['매출액']
                     curr_data['영업이익'] -= q3_data['영업이익']
                     curr_data['순이익'] -= q3_data['순이익']
                     # 현금흐름, 수주잔고는 잔액 개념이거나 복잡해서 그대로 둠

            # 행 생성
            new_record = {
                'corp_code': row['corp_code'],
                'corp_name': row['corp_name'],
                'year': y,
                'quarter': q,
                **curr_data,
                '수주잔고_증감': diff
            }
            new_rows.append(new_record)
            
            # 슬랙 알림 보내기
            def to_b(v): return f"{v/100000000:,.1f}억"
            msg = (f"📢 *[{row['corp_name']}] {q} 실적발표*\n"
                   f"💰 매출: {to_b(curr_data['매출액'])}\n"
                   f"📈 영업이익: {to_b(curr_data['영업이익'])}\n"
                   f"🌊 수주잔고: {to_b(curr_data['수주잔고'])} (변동: {to_b(diff)})")
            send_slack(msg)
            
            time.sleep(1) # API 보호

    # 4. 저장 (Append)
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        # 기존 DB 뒤에 이어붙이기
        updated_db = pd.concat([db, new_df], ignore_index=True)
        updated_db.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
        print(f"✅ 총 {len(new_rows)}건 업데이트 완료.")
    else:
        print("업데이트할 내역이 없습니다.")

if __name__ == "__main__":
    main()