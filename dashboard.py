import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 페이지 설정 & 유틸리티 함수
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART 실적 대시보드 Pro", layout="wide")

# 한국식 화폐 단위 변환 함수 (예: 100000000 -> 1억)
def format_korean_currency(value):
    if pd.isna(value) or value == 0:
        return "-"
    value = float(value)
    if abs(value) >= 1000000000000: # 1조 이상
        return f"{value/1000000000000:,.1f}조"
    elif abs(value) >= 100000000: # 1억 이상
        return f"{value/100000000:,.1f}억"
    else:
        return f"{value:,.0f}원"

# -----------------------------------------------------------------------------
# 2. 데이터 로드
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

    # 컬럼 이름 통일 (한글 -> 영어)
    rename_map = {
        '매출액': 'revenue', '영업이익': 'profit', 
        '순이익': 'net_income', '당기순이익': 'net_income',
        '영업현금흐름': 'cash_flow', '수주잔고': 'backlog'
    }
    df = df.rename(columns=rename_map)
    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (필터링 기능)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 검색 및 필터")
    
    if not raw_df.empty:
        # 1. 기업 이름 검색 (멀티 선택)
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업명 검색 (여러 개 선택 가능)", all_corps)
        
        # 2. 연도 선택
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        selected_year = st.multiselect("연도 (Year)", all_years, default=all_years[:1])
        
        # 3. 분기 선택
        all_quarters = sorted(raw_df['quarter'].unique())
        selected_quarter = st.multiselect("분기 (Quarter)", all_quarters, default=all_quarters)
    else:
        st.error("데이터가 없습니다.")
        selected_corps, selected_year, selected_quarter = [], [], []

# -----------------------------------------------------------------------------
# 4. 데이터 필터링 로직
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.info("데이터를 불러오는 중입니다...")
    st.stop()

filtered_df = raw_df.copy()

# 필터 적용
if selected_corps:
    filtered_df = filtered_df[filtered_df['corp_name'].isin(selected_corps)]
if selected_year:
    filtered_df = filtered_df[filtered_df['year'].isin(selected_year)]
if selected_quarter:
    filtered_df = filtered_df[filtered_df['quarter'].isin(selected_quarter)]

# -----------------------------------------------------------------------------
# 5. 메인 대시보드 화면
# -----------------------------------------------------------------------------
st.title("📊 DART 실적 분석 대시보드")
st.markdown(f"총 **{len(filtered_df):,}**개의 데이터가 검색되었습니다.")

# (1) KPI 스코어카드 (핵심 지표 요약)
# 선택된 데이터들의 합계나 평균을 보여줌
if not filtered_df.empty:
    total_revenue = filtered_df['revenue'].sum()
    total_profit = filtered_df['profit'].sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("검색된 기업 총 매출", format_korean_currency(total_revenue))
    col2.metric("검색된 기업 총 영업이익", format_korean_currency(total_profit))
    
    # 영업이익률 계산
    if total_revenue > 0:
        margin = (total_profit / total_revenue) * 100
        col3.metric("평균 영업이익률", f"{margin:.1f}%")

st.divider()

# (2) 차트 영역
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("💰 매출액 Top 10")
    if 'revenue' in filtered_df.columns:
        top_rev = filtered_df.nlargest(10, 'revenue')
        fig = px.bar(top_rev, x='corp_name', y='revenue', 
                     color='revenue', text_auto='.2s',
                     title="기업별 매출액 (단위: 원)")
        st.plotly_chart(fig, use_container_width=True)

with col_chart2:
    st.subheader("📈 영업이익 Top 10")
    if 'profit' in filtered_df.columns:
        top_prof = filtered_df.nlargest(10, 'profit')
        fig = px.bar(top_prof, x='corp_name', y='profit', 
                     color='profit', text_auto='.2s',
                     title="기업별 영업이익 (단위: 원)")
        st.plotly_chart(fig, use_container_width=True)

# (3) 상세 데이터 표 (Fancy Table)
st.subheader("📋 상세 데이터 리스트")

# 표에 표시할 컬럼 설정 (천단위 콤마 & 막대그래프 효과)
column_config = {
    "corp_name": "기업명",
    "year": "연도",
    "quarter": "분기",
    "revenue": st.column_config.NumberColumn(
        "매출액",
        format="%d원",   # 숫자로 표시
        help="기업의 총 매출액입니다."
    ),
    "profit": st.column_config.ProgressColumn(
        "영업이익 (규모)",
        format="%d원",
        min_value=int(filtered_df['profit'].min()) if not filtered_df.empty else 0,
        max_value=int(filtered_df['profit'].max()) if not filtered_df.empty else 100,
    ),
    "net_income": st.column_config.NumberColumn(
        "당기순이익",
        format="%d원"
    )
}

# 보여줄 컬럼만 선택
display_cols = ['corp_name', 'year', 'quarter', 'revenue', 'profit', 'net_income']
# 데이터가 있는 경우만 표시
final_table = filtered_df[display_cols].sort_values(by=['year', 'quarter', 'revenue'], ascending=False)

st.dataframe(
    final_table,
    column_config=column_config,
    use_container_width=True,
    hide_index=True,
    height=500
)
