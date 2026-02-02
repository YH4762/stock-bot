import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정 & 스타일
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART Enterprise Dashboard", layout="wide", page_icon="📈")

# [핵심] 큰 숫자를 '조/억/만' 단위로 예쁘게 변환하는 함수 (KPI 카드용)
def format_korean_human(value):
    if pd.isna(value) or value == 0: return "-"
    
    # 입력값이 '백만 원' 단위라고 가정
    val = float(value)
    
    # 1조 이상 (1,000,000 백만)
    if abs(val) >= 1000000:
        return f"{val/1000000:,.1f}조"
    # 1억 이상 (100 백만)
    elif abs(val) >= 100:
        return f"{val/100:,.1f}억"
    else:
        return f"{val:,.0f}백만"

# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리
# -----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=3600)
def load_data():
    try:
        # 인코딩 문제 자동 해결 시도
        try:
            df = pd.read_csv(CSV_URL)
        except UnicodeDecodeError:
            df = pd.read_csv(CSV_URL, encoding='cp949')
    except:
        return pd.DataFrame()

    # 컬럼명 한글 -> 영어 변환
    rename_map = {
        '매출액': 'revenue', '영업이익': 'profit', 
        '순이익': 'net_income', '당기순이익': 'net_income',
        '영업현금흐름': 'cash_flow', '수주잔고': 'backlog'
    }
    df = df.rename(columns=rename_map)
    
    # 숫자 데이터 전처리: 콤마 제거 & 백만 단위 변환
    numeric_cols = ['revenue', 'profit', 'net_income', 'cash_flow']
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            
            # [중요] 모든 금액을 '백만 원' 단위로 변환하여 저장
            df[col] = df[col] / 1000000 

    # 시계열 정렬용 컬럼
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    
    # 이익률(OPM) 계산
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] > 0 else 0, axis=1)

    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (필터링)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 Analyst Control Panel")
    
    if not raw_df.empty:
        st.subheader("Filter 1: Target")
        
        # 기업 선택
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업 선택", all_corps, placeholder="전체 보기")
        
        # 연도/분기
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("Year", all_years, default=all_years[:1])
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("Quarter", all_q, default=all_q)
        
        st.divider()
        
        # 수치 범위 필터 (슬라이더 + 입력창)
        st.subheader("Filter 2: Financial Range")
        st.caption("단위: 백만 원")
        
        def range_filter(label, col):
            if col not in raw_df.columns: return -1e15, 1e15
            _min, _max = int(raw_df[col].min()), int(raw_df[col].max())
            slider = st.slider(f"{label} 범위", _min, _max, (_min, _max))
            c1, c2 = st.columns(2)
            i_min = c1.number_input(f"Min", value=slider[0], step=1000, key=f"{col}_min")
            i_max = c2.number_input(f"Max", value=slider[1], step=1000, key=f"{col}_max")
            return i_min, i_max

        rev_min, rev_max = range_filter("매출", 'revenue')
        prof_min, prof_max = range_filter("영업이익", 'profit')
        
    else:
        selected_corps, sel_year, sel_q = [], [], []

# -----------------------------------------------------------------------------
# 4. 데이터 필터링
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.warning("데이터를 불러오는 중입니다...")
    st.stop()

df = raw_df.copy()
if selected_corps: df = df[df['corp_name'].isin(selected_corps)]
if sel_year: df = df[df['year'].isin(sel_year)]
if sel_q: df = df[df['quarter'].isin(sel_q)]

df = df[(df['revenue'] >= rev_min) & (df['revenue'] <= rev_max)]
df = df[(df['profit'] >= prof_min) & (df['profit'] <= prof_max)]

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📊 Enterprise Financial Dashboard")
st.markdown(f"**Data:** {len(df):,} records | **Unit:** 백만 원 (Million KRW)")

# (1) 상단 KPI (한국식 조/억 단위 적용)
if not df.empty:
    kpi1, kpi2 = st.columns(2)
    kpi1.metric("총 매출액", format_korean_human(df['revenue'].sum()))
    kpi2.metric("총 영업이익", format_korean_human(df['profit'].sum()))
    
    st.write("") 
    kpi3, kpi4 = st.columns(2)
    avg_opm = df['opm'].mean() if not df.empty else 0
    kpi3.metric("평균 영업이익률", f"{avg_opm:.1f}%")
    kpi4.metric("분석 대상 기업 수", f"{df['corp_name'].nunique()}개")

st.divider()

# 탭 구성
tab1, tab2, tab3 = st.tabs(["📌 Overview", "📈 Trend", "💎 Analysis"])

# --- Tab 1: 상세 테이블 (Fancy Style) ---
with tab1:
    st.subheader("🏆 Top Performers Table")
    st.caption("팁: 컬럼 헤더를 클릭하면 정렬됩니다. 이익 컬럼은 막대그래프로 표시됩니다.")

    if not df.empty:
        # 보여줄 컬럼만 선택
        cols = ['corp_name', 'year', 'quarter', 'revenue', 'profit', 'opm', 'net_income']
        table_df = df[cols].sort_values('revenue', ascending=False)
        
        # [핵심] Streamlit Column Config를 이용한 디자인 (Matplotlib 불필요!)
        st.dataframe(
            table_df,
            column_config={
                "corp_name": st.column_config.TextColumn("기업명", width="medium"),
                "year": st.column_config.TextColumn("연도"),
                "quarter": st.column_config.TextColumn("분기"),
                
                # 1. 콤마 포맷팅 (format="%d")
                "revenue": st.column_config.NumberColumn(
                    "매출액 (백만)",
                    format="%d",  # 1,234,567 형태로 콤마 자동 삽입
                    help="단위: 백만 원"
                ),
                
                # 2. 막대그래프 포맷팅 (ProgressColumn)
                "profit": st.column_config.ProgressColumn(
                    "영업이익 (Visual)",
                    format="%d", # 숫자도 콤마 찍어서 보여줌
                    min_value=int(df['profit'].min()),
                    max_value=int(df['profit'].max()),
                ),
                
                # 3. 퍼센트 포맷팅
                "opm": st.column_config.NumberColumn(
                    "이익률",
                    format="%.1f%%" # 15.3% 형태로 표시
                ),
                "net_income": st.column_config.NumberColumn(
                    "순이익",
                    format="%d"
                )
            },
            use_container_width=True,
            height=600,
            hide_index=True
        )

# --- Tab 2: 시계열 추세 ---
with tab2:
    st.subheader("Revenue Trend")
    if len(selected_corps) > 0:
        fig_trend = px.line(
            df.sort_values('period'), x='period', y='revenue', color='corp_name',
            markers=True, title="기업별 매출 추이"
        )
        # 차트 툴팁 숫자도 예쁘게 (콤마)
        fig_trend.update_traces(yhoverformat=",d") 
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        yearly_sum = df.groupby('period')[['revenue', 'profit']].sum().reset_index()
        fig_trend_all = px.bar(yearly_sum, x='period', y='revenue', title="전체 시장 매출 추이")
        fig_trend_all.update_traces(yhoverformat=",d")
        st.plotly_chart(fig_trend_all, use_container_width=True)

# --- Tab 3: 수익성 분석 ---
with tab3:
    st.subheader("Efficiency Analysis")
    
    if not df.empty:
        top10 = df.groupby('corp_name')[['revenue', 'opm']].mean().reset_index().nlargest(10, 'revenue')
        
        fig_combo = go.Figure()
        fig_combo.add_trace(go.Bar(
            x=top10['corp_name'], y=top10['revenue'],
            name='매출액', marker_color='#3366CC', yaxis='y'
        ))
        fig_combo.add_trace(go.Scatter(
            x=top10['corp_name'], y=top10['opm'],
            name='이익률', marker_color='#FF9900', mode='lines+markers', yaxis='y2'
        ))
        
        fig_combo.update_layout(
            title="Top 10 기업 매출 vs 이익률",
            yaxis=dict(title="매출액 (백만)", tickformat=","), # Y축 콤마
            yaxis2=dict(title="영업이익률 (%)", overlaying='y', side='right'),
            legend=dict(x=0.01, y=0.99),
            hovermode='x unified'
        )
        st.plotly_chart(fig_combo, use_container_width=True)
