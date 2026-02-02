import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 페이지 설정 & 단위 변환 함수
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART 실적 대시보드 Pro", layout="wide")

# (이미 백만 단위로 변환된 숫자를) '조/억' 단위로 읽기 좋게 바꿔주는 함수
# 입력값 10000 = 100억 (10000 * 백만)
def format_millions_to_korean(value):
    if pd.isna(value) or value == 0:
        return "-"
    
    # 입력값이 '백만 원' 단위이므로 조/억 계산을 조정
    # 1조 = 1,000,000 백만
    # 1억 = 100 백만
    val = float(value)
    
    if abs(val) >= 1000000: # 1조 이상
        return f"{val/1000000:,.1f}조"
    elif abs(val) >= 100:   # 1억 이상
        return f"{val/100:,.1f}억"
    else:
        return f"{val:,.0f}백만"

# -----------------------------------------------------------------------------
# 2. 데이터 로드 (핵심: 백만 원 단위로 변환)
# -----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=3600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_URL, encoding='cp949')
    except:
        return pd.DataFrame()

    # 1. 컬럼 이름 통일
    rename_map = {
        '매출액': 'revenue', '영업이익': 'profit', 
        '순이익': 'net_income', '당기순이익': 'net_income',
        '영업현금흐름': 'cash_flow', '수주잔고': 'backlog'
    }
    df = df.rename(columns=rename_map)
    
    # 2. 숫자 데이터들을 전부 '백만 원' 단위로 나누기
    numeric_cols = ['revenue', 'profit', 'net_income']
    for col in numeric_cols:
        if col in df.columns:
            # 원 단위 -> 백만 단위 변환 (소수점은 유지하되 나중에 포맷팅)
            df[col] = df[col] / 1000000
            
    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (필터링)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 검색 옵션")
    
    if not raw_df.empty:
        # 기업명 검색
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업 선택", all_corps)
        
        # 연도 선택
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        selected_year = st.multiselect("연도", all_years, default=all_years[:1])
        
        # 분기 선택
        all_quarters = sorted(raw_df['quarter'].unique())
        selected_quarter = st.multiselect("분기", all_quarters, default=all_quarters)
    else:
        st.error("데이터 로드 실패")
        selected_corps, selected_year, selected_quarter = [], [], []

# -----------------------------------------------------------------------------
# 4. 필터링 적용
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.info("데이터를 불러오는 중입니다...")
    st.stop()

filtered_df = raw_df.copy()

if selected_corps:
    filtered_df = filtered_df[filtered_df['corp_name'].isin(selected_corps)]
if selected_year:
    filtered_df = filtered_df[filtered_df['year'].isin(selected_year)]
if selected_quarter:
    filtered_df = filtered_df[filtered_df['quarter'].isin(selected_quarter)]

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📊 DART 실적 분석 (단위: 백만 원)")
st.markdown(f"검색 결과: **{len(filtered_df):,}**건")

# (1) KPI 스코어카드
if not filtered_df.empty:
    total_rev = filtered_df['revenue'].sum()
    total_prof = filtered_df['profit'].sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("총 매출액", format_millions_to_korean(total_rev))
    col2.metric("총 영업이익", format_millions_to_korean(total_prof))
    
    if total_rev > 0:
        margin = (total_prof / total_rev) * 100
