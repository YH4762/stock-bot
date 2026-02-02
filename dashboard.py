import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 페이지 설정 & 단위 변환 함수
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART 실적 대시보드 Pro", layout="wide")

# (백만 단위로 변환된 숫자를) '조/억' 단위로 읽기 좋게 바꿔주는 함수
def format_millions_to_korean(value):
    if pd.isna(value) or value == 0:
        return "-"
    
    val = float(value)
    # 입력값은 이미 백만 단위임 (1,000,000 = 1조)
    if abs(val) >= 1000000: # 1조 이상
        return f"{val/1000000:,.1f}조"
    elif abs(val) >= 100:   # 1억 이상
        return f"{val/100:,.1f}억"
    else:
        return f"{val:,.0f}백만"

# -----------------------------------------------------------------------------
# 2. 데이터 로드 (백만 원 단위 변환)
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
    numeric_cols = ['revenue', 'profit', 'net_income', 'cash_flow']
    for col in numeric_cols:
        if col in df.columns:
            # 문자열(쉼표 포함)일 경우 제거 후 변환 안전장치
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            
            # 원 단위 -> 백만 단위 변환
            df[col] = df[col] / 1000000
            
    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (고급 필터링)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 고급 검색 옵션")
    
    if not raw_df.empty:
        # (1) 기본 필터
        st.subheader("📌 기본 정보")
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업 선택", all_corps, placeholder="기업을 선택하세요 (공란시 전체)")
        
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        selected_year = st.multiselect("연도", all_years, default=all_years[:1])
        
        all_quarters = sorted(raw_df['quarter'].unique())
        selected_quarter = st.multiselect("분기", all_quarters, default=all_quarters)

        st.divider()

        # (2) 재무 수치 필터 (슬라이더)
        st.subheader("💰 재무 범위 설정 (단위: 백만)")
        
        # 매출액 필터
        min_rev, max_rev = int(raw_df['revenue'].min()), int(raw_df['revenue'].max())
        rev_range = st.slider("매출액 범위", min_rev, max_rev, (min_rev, max_rev))

        # 순이익 필터 (데이터가 있을 때만)
        if 'net_income' in raw_df.columns:
            min_net, max_net = int(raw_df['net_income'].min()), int(raw_df['net_income'].max())
            net_range = st.slider("순이익 범위", min_net, max_net, (min_net, max_net))
        else:
            net_range = (-999999999, 999999999)

        # 영업현금흐름 필터
        if 'cash_flow' in raw_df.columns:
            # NaN 처리
            cf_clean = raw_df['cash_flow'].fillna(0)
            min_cf, max_cf = int(cf_clean.min()), int(cf_clean.max())
            cf_range = st.slider("영업현금흐름 범위", min_cf, max_cf, (min_cf, max_cf))
        else:
            cf_range = (-999999999, 999999999)

    else:
        st.error("데이터 로드 실패")
        selected_corps, selected_year, selected_quarter = [], [], []
        rev_range = (0, 0)

# -----------------------------------------------------------------------------
# 4. 필터링 로직 적용
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.info("데이터를 불러오는 중입니다...")
    st.stop()

filtered_df = raw_df.copy()

# 기본 필터
if selected_corps:
    filtered_df = filtered_df[filtered_df['corp_name'].isin(selected_corps)]
if selected_year:
    filtered_df = filtered_df[filtered_df['year'].isin(selected_year)]
if selected_quarter:
    filtered_df = filtered_df[filtered_df['quarter'].isin(selected_quarter)]

# 수치 필터
filtered_df = filtered_df[
    (filtered_df['revenue'] >= rev_range[0]) & (filtered_df['revenue'] <= rev_range[1])
]
if 'net_income' in filtered_df.columns:
    filtered_df = filtered_df[
        (filtered_df['net_income'] >= net_range[0]) & (filtered_df['net_income'] <= net_range[1])
    ]
if 'cash_flow' in filtered_df.columns:
    # cash_flow가 NaN이면 0으로 치고 필터링
    filtered_df['cash_flow'] = filtered_df['cash_flow'].fillna(0)
    filtered_df = filtered_df[
        (filtered_df['cash_flow'] >= cf_range[0]) & (filtered_df['cash_flow'] <= cf_range[1])
    ]

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📊 DART 실적 분석 (단위: 백만 원)")
st.markdown(f"검색 결과: **{len(filtered_df):,}**건")

# (1) KPI 스코어카드 (증감액 로직 추가)
if not filtered_df.empty:
    # 정렬: 시간순 (연도 -> 분기)
    filtered_df = filtered_df.sort_values(by=['year', 'quarter'])
    
    # 1. 가장 최근 데이터들의 합계 (Latest Period Sum)
    # 예: 2024 1Q, 2024 2Q가 섞여있으면 -> 2Q 데이터들의 합계를 '현재 값'으로 봄
    last_year = filtered_df['year'].max()
    # 해당 연도에서 가장 늦은 분기 찾기
    last_q_in_year = filtered_df[filtered_df['year'] == last_year]['quarter'].max()
    
    latest_df = filtered_df[
        (filtered_df['year'] == last_year) & (filtered_df['quarter'] == last_q_in_year)
    ]
    
    # 2. 가장 오래된 데이터들의 합계 (Oldest Period Sum - 비교군)
    first_year = filtered_df['year'].min()
    first_q_in_year = filtered_df[filtered_df['year'] == first_year]['quarter'].min()
    
    oldest_df = filtered_df[
        (filtered_df['year'] == first_year) & (filtered_df['quarter'] == first_q_in_year)
    ]
    
    # 만약 기간이 딱 하나만 선택되었다면 증감은 0
    is_same_period = (last_year == first_year) and (last_q_in_year == first_q_in_year)
    
    # KPI 계산
    metrics = [
        ("매출액", 'revenue'),
        ("영업이익", 'profit'),
        ("순이익", 'net_income')
    ]
    
    cols = st.columns(3)
    
    for idx, (label, col_name) in enumerate(metrics):
        if col_name in filtered_df.columns:
            current_val = latest_df[col_name].sum()
            old_val = oldest_df[col_name].sum()
            
            diff = current_val - old_val
            
            # 기간이 같으면 델타 표시 안 함, 다르면 표시
            delta_val = f"{diff:,.0f}백만" if not is_same_period else None
            
            cols[idx].metric(
                label=f"총 {label} ({last_year} {last_q_in_year})",
                value=format_millions_to_korean(current_val),
                delta=delta_val
            )

st.divider()

# (2) 차트 영역
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("💰 매출액 Top 10")
    if 'revenue' in filtered_df.columns:
        top_rev = filtered_df.nlargest(10, 'revenue')
        fig = px.bar(top_rev, x='corp_name', y='revenue', 
                     text_auto=',.0f', 
                     title="기업별 매출액", color='revenue')
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

with col_chart2:
    st.subheader("📈 순이익 Top 10")
    # 영업이익 대신 순이익으로 변경 (요청사항 반영)
    if 'net_income' in filtered_df.columns:
        top_net = filtered_df.nlargest(10, 'net_income')
        fig = px.bar(top_net, x='corp_name', y='net_income', 
                     color='net_income', text_auto=',.0f',
                     title="기업별 순이익")
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

# (3) 상세 표
st.subheader("📋 상세 데이터 (단위: 백만 원)")

column_config = {
    "corp_name": "기업명",
    "year": "연도",
    "quarter": "분기",
    "revenue": st.column_config.NumberColumn("매출액", format="%d"),
    "profit": st.column_config.NumberColumn("영업이익", format="%d"),
    "net_income": st.column_config.NumberColumn("순이익", format="%d"),
    "cash_flow": st.column_config.NumberColumn("영업현금흐름", format="%d"),
}

# 표시할 컬럼 정의
display_cols = ['corp_name', 'year', 'quarter', 'revenue', 'profit', 'net_income']
if 'cash_flow' in filtered_df.columns:
    display_cols.append('cash_flow')

final_table = filtered_df[display_cols].sort_values(by=['revenue'], ascending=False)

st.dataframe(
    final_table,
    column_config=column_config,
    use_container_width=True,
    hide_index=True,
    height=600
)
