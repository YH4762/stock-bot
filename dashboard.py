import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정 & 스타일
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART Enterprise Dashboard", layout="wide", page_icon="📈")

# 천단위 콤마 및 조/억 단위 변환 함수
def format_currency(value):
    if pd.isna(value) or value == 0: return "-"
    val = float(value)
    if abs(val) >= 1000000: return f"{val/1000000:,.1f}조"
    elif abs(val) >= 100:   return f"{val/100:,.1f}억"
    else: return f"{val:,.0f}백만"

# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리
# -----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=3600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
    except:
        try: df = pd.read_csv(CSV_URL, encoding='cp949')
        except: return pd.DataFrame()

    # 컬럼 영문 변환
    rename_map = {
        '매출액': 'revenue', '영업이익': 'profit', 
        '순이익': 'net_income', '당기순이익': 'net_income',
        '영업현금흐름': 'cash_flow', '수주잔고': 'backlog'
    }
    df = df.rename(columns=rename_map)
    
    # 숫자 데이터 전처리 (콤마 제거 및 백만 단위 변환)
    numeric_cols = ['revenue', 'profit', 'net_income', 'cash_flow']
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            df[col] = df[col] / 1000000 # 백만 단위로 변환

    # 시계열 정렬을 위한 'Period' 컬럼 생성
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    
    # 영업이익률(OPM) 계산
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] > 0 else 0, axis=1)

    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (UI 개선됨: 세로 배치)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 Analyst Control Panel")
    
    if not raw_df.empty:
        st.subheader("Filter 1: Target")
        
        # 1. 기업 선택
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업 선택 (Multi-Select)", all_corps, placeholder="전체 보기")
        
        # 2. 연도/분기 선택 (수정됨: 컬럼 나누지 않고 세로로 배치하여 공간 확보)
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("Year (연도)", all_years, default=all_years[:1])
        
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("Quarter (분기)", all_q, default=all_q)
        
        st.divider()
        
        # 3. 수치 범위 필터
        st.subheader("Filter 2: Financial Range")
        
        def range_filter(label, col):
            if col not in raw_df.columns: return -1e15, 1e15
            _min, _max = int(raw_df[col].min()), int(raw_df[col].max())
            slider = st.slider(f"{label} (Bar)", _min, _max, (_min, _max))
            
            # 입력창은 좁아도 되므로 2단 분리 유지
            c1, c2 = st.columns(2)
            i_min = c1.number_input(f"Min {label}", value=slider[0], step=1000)
            i_max = c2.number_input(f"Max {label}", value=slider[1], step=1000)
            return i_min, i_max

        rev_min, rev_max = range_filter("매출(Revenue)", 'revenue')
        prof_min, prof_max = range_filter("이익(Profit)", 'profit')
        
    else:
        selected_corps, sel_year, sel_q = [], [], []

# -----------------------------------------------------------------------------
# 4. 데이터 필터링
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.warning("데이터 로딩 중...")
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
st.markdown(f"**Selected Data:** {len(df):,} records | **Unit:** Million KRW (백만 원)")

# [수정됨] 상단 KPI: 4칸 -> 2칸씩 2줄 (숫자 잘림 방지)
if not df.empty:
    # 첫 번째 줄
    kpi1, kpi2 = st.columns(2)
    kpi1.metric("총 매출액", format_currency(df['revenue'].sum()))
    kpi2.metric("총 영업이익", format_currency(df['profit'].sum()))
    
    # 두 번째 줄 (여백 추가)
    st.write("") 
    kpi3, kpi4 = st.columns(2)
    avg_opm = df['opm'].mean() if not df.empty else 0
    kpi3.metric("평균 영업이익률", f"{avg_opm:.1f}%")
    kpi4.metric("분석 대상 기업 수", f"{df['corp_name'].nunique()}개")

st.divider()

# 탭 메뉴
tab1, tab2, tab3 = st.tabs(["📌 Overview (시장지도)", "📈 Trend (시계열)", "💎 Deep Dive (수익성)"])

# --- Tab 1: 시장 지도 (Treemap) ---
with tab1:
    st.subheader("Market Map (규모 비교)")
    if not df.empty:
        fig_tree = px.treemap(
            df, path=['year', 'corp_name'], values='revenue',
            color='profit', color_continuous_scale='RdBu',
            title="시장 지배력 및 수익성 지도 (크기: 매출 / 색상: 이익)"
        )
        st.plotly_chart(fig_tree, use_container_width=True)
    
    st.subheader("Top Performers Table")
    st.dataframe(
        df[['corp_name', 'year', 'quarter', 'revenue', 'profit', 'opm', 'net_income']]
        .sort_values('revenue', ascending=False)
        .style.background_gradient(subset=['profit'], cmap='Greens'),
        use_container_width=True
    )

# --- Tab 2: 시계열 추세 (Trend) ---
with tab2:
    st.subheader("Revenue & Profit Trends")
    if len(selected_corps) > 0:
        fig_trend = px.line(
            df.sort_values('period'), x='period', y='revenue', color='corp_name',
            markers=True, title="기업별 매출 추이"
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("왼쪽 사이드바에서 특정 기업을 선택하면 비교 그래프가 나타납니다.")
        yearly_sum = df.groupby('period')[['revenue', 'profit']].sum().reset_index()
        fig_trend_all = px.bar(yearly_sum, x='period', y='revenue', title="전체 매출 추이")
        st.plotly_chart(fig_trend_all, use_container_width=True)

# --- Tab 3: 수익성 분석 (Combo Chart) ---
with tab3:
    st.subheader("Efficiency Analysis")
    
    if not df.empty:
        # 매출 상위 10개 기업 추출
        top10 = df.groupby('corp_name')[['revenue', 'opm']].mean().reset_index().nlargest(10, 'revenue')
        
        fig_combo = go.Figure()
        fig_combo.add_trace(go.Bar(
            x=top10['corp_name'], y=top10['revenue'],
            name='매출액 (좌측)', marker_color='#3366CC', yaxis='y'
        ))
        fig_combo.add_trace(go.Scatter(
            x=top10['corp_name'], y=top10['opm'],
            name='영업이익률% (우측)', marker_color='#FF9900', mode='lines+markers', yaxis='y2'
        ))
        
        fig_combo.update_layout(
            title="Top 10 기업 매출 vs 이익률 분석",
            yaxis=dict(title="매출액 (백만 원)"),
            yaxis2=dict(title="영업이익률 (%)", overlaying='y', side='right'),
            legend=dict(x=0.01, y=0.99),
            hovermode='x unified'
        )
        st.plotly_chart(fig_combo, use_container_width=True)
        
        st.subheader("Risk vs Reward (Scatter Matrix)")
        fig_scatter = px.scatter(
            df, x='revenue', y='profit', size='revenue', color='corp_name',
            hover_name='corp_name', log_x=True,
            title="매출 대비 이익 분포 (Log Scale)"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
