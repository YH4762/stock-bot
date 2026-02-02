import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정 & 스타일
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART Enterprise Dashboard", layout="wide", page_icon="🚀")

# (백만 단위 숫자를) '조/억' 단위 텍스트로 변환하는 함수
def format_currency(value):
    if pd.isna(value) or value == 0: return "-"
    val = float(value)
    if abs(val) >= 1000000: return f"{val/1000000:,.1f}조"
    elif abs(val) >= 100:   return f"{val/100:,.1f}억"
    else: return f"{val:,.0f}백만"

# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리 (QoQ 계산 추가)
# -----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=3600)
def load_data():
    try:
        try: df = pd.read_csv(CSV_URL)
        except UnicodeDecodeError: df = pd.read_csv(CSV_URL, encoding='cp949')
    except: return pd.DataFrame()

    # 1. 컬럼명 통일
    rename_map = {
        '매출액': 'revenue', '영업이익': 'profit', 
        '순이익': 'net_income', '당기순이익': 'net_income',
        '영업현금흐름': 'cash_flow', '수주잔고': 'backlog'
    }
    df = df.rename(columns=rename_map)
    
    # 2. 숫자 데이터 전처리 (백만 원 단위 변환)
    numeric_cols = ['revenue', 'profit', 'net_income', 'cash_flow']
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            df[col] = df[col] / 1000000 

    # 3. 파생 변수 생성
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] > 0 else 0, axis=1)

    # ---------------------------------------------------------
    # [핵심 추가] QoQ (전분기 대비) 증감액 계산
    # ---------------------------------------------------------
    # 기업별, 시간순 정렬
    df = df.sort_values(by=['corp_name', 'year', 'quarter'])
    
    # 기업별로 그룹지어서 '이전 행'과의 차이 계산
    # (주의: 데이터가 연속적이지 않으면 이전 데이터와의 단순 차이임)
    df['rev_qoq'] = df.groupby('corp_name')['revenue'].diff().fillna(0)
    df['prof_qoq'] = df.groupby('corp_name')['profit'].diff().fillna(0)
    df['opm_qoq'] = df.groupby('corp_name')['opm'].diff().fillna(0)

    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (필터링)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 Analyst Control Panel")
    
    if not raw_df.empty:
        st.subheader("Filter 1: Target")
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업 선택", all_corps, placeholder="전체 보기 (비워두면 전체)")
        
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("Year (연도)", all_years, default=all_years[:1])
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("Quarter (분기)", all_q, default=all_q)
        
        st.divider()
        st.subheader("Filter 2: Financial Range")
        
        def range_filter(label, col):
            if col not in raw_df.columns: return -1e15, 1e15
            _min, _max = int(raw_df[col].min()), int(raw_df[col].max())
            slider = st.slider(f"{label}", _min, _max, (_min, _max))
            return slider[0], slider[1]

        rev_min, rev_max = range_filter("매출", 'revenue')
        prof_min, prof_max = range_filter("영업이익", 'profit')
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

# 상단 KPI
if not df.empty:
    kpi1, kpi2 = st.columns(2)
    kpi1.metric("총 매출액", format_currency(df['revenue'].sum()))
    kpi2.metric("총 영업이익", format_currency(df['profit'].sum()))
    
    st.write("")
    kpi3, kpi4 = st.columns(2)
    avg_opm = df['opm'].mean() if not df.empty else 0
    kpi3.metric("평균 영업이익률", f"{avg_opm:.1f}%")
    kpi4.metric("분석 대상 기업 수", f"{df['corp_name'].nunique()}개")

st.divider()

# 탭 메뉴 (Growth 탭 추가됨)
tab1, tab2, tab3, tab4 = st.tabs([
    "🚀 Growth (QoQ 성장성)", 
    "📌 Overview (시장지도)", 
    "📈 Trend (시계열)", 
    "💎 Efficiency (수익성)"
])

# --- Tab 1: Growth Analysis (신규 추가된 핵심 기능) ---
with tab1:
    st.subheader("🔥 Quarter-to-Quarter Growth Champions")
    st.markdown("전분기 대비 실적이 가장 크게 개선된 **Top 10 기업**을 분석합니다.")

    if not df.empty:
        # 화면을 2분할하여 차트 배치
        row1_1, row1_2 = st.columns(2)
        
        # 1. 매출액 증가 Top 10
        with row1_1:
            st.markdown("##### 1️⃣ 매출액 급증 Top 10 (Amount)")
            top_rev_growth = df.nlargest(10, 'rev_qoq')
            fig_g1 = px.bar(
                top_rev_growth, y='corp_name', x='rev_qoq',
                orientation='h', text_auto=',.0f',
                color='rev_qoq', color_continuous_scale='Blues',
                title="전분기 대비 매출 증가액 (백만 원)"
            )
            fig_g1.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_g1, use_container_width=True)

        # 2. 영업이익 증가 Top 10
        with row1_2:
            st.markdown("##### 2️⃣ 영업이익 급증 Top 10 (Amount)")
            top_prof_growth = df.nlargest(10, 'prof_qoq')
            fig_g2 = px.bar(
                top_prof_growth, y='corp_name', x='prof_qoq',
                orientation='h', text_auto=',.0f',
                color='prof_qoq', color_continuous_scale='Greens',
                title="전분기 대비 영업이익 증가액 (백만 원)"
            )
            fig_g2.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_g2, use_container_width=True)

        st.divider()
        
        row2_1, row2_2 = st.columns(2)

        # 3. 영업이익률(OPM) 개선 Top 10
        with row2_1:
            st.markdown("##### 3️⃣ 영업이익률 개선 Top 10 (%p)")
            top_opm_growth = df.nlargest(10, 'opm_qoq')
            fig_g3 = px.bar(
                top_opm_growth, x='corp_name', y='opm_qoq',
                text_auto='+.1f', # +부호 표시
                color='opm_qoq', color_continuous_scale='Teal',
                title="전분기 대비 이익률 증가폭 (%p)"
            )
            st.plotly_chart(fig_g3, use_container_width=True)

        # 4. 매출 대비 이익분포 (알짜기업 Top 10)
        with row2_2:
            st.markdown("##### 4️⃣ 최고 효율(이익률) 기업 Top 10")
            top_opm = df.nlargest(10, 'opm')
            fig_g4 = px.scatter(
                top_opm, x='revenue', y='opm', size='profit',
                color='corp_name', text='corp_name',
                title="매출 대비 이익률 분포 (알짜기업)",
                labels={'revenue': '매출액', 'opm': '영업이익률(%)'}
            )
            st.plotly_chart(fig_g4, use_container_width=True)
            
    else:
        st.info("데이터가 충분하지 않아 비교할 수 없습니다.")

# --- Tab 2: 시장 지도 ---
with tab2:
    st.subheader("Market Map")
    if not df.empty:
        fig_tree = px.treemap(
            df, path=['year', 'corp_name'], values='revenue',
            color='profit', color_continuous_scale='RdBu',
            title="시장 지배력 지도 (Size: 매출 / Color: 이익)"
        )
        st.plotly_chart(fig_tree, use_container_width=True)
    
    st.subheader("🏆 Data Grid")
    cols = ['corp_name', 'year', 'quarter', 'revenue', 'rev_qoq', 'profit', 'prof_qoq', 'opm']
    
    st.dataframe(
        df[cols].sort_values('revenue', ascending=False).style.format({
            'revenue': '{:,.0f}', 'rev_qoq': '{:+,.0f}', 
            'profit': '{:,.0f}', 'prof_qoq': '{:+,.0f}',
            'opm': '{:.1f}%'
        }).background_gradient(subset=['profit'], cmap='RdYlGn'),
        use_container_width=True
    )

# --- Tab 3: 시계열 추세 ---
with tab3:
    st.subheader("Trend Analysis")
    if len(selected_corps) > 0:
        fig_trend = px.line(
            df.sort_values('period'), x='period', y='revenue', color='corp_name',
            markers=True, title="기업별 매출 추이"
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        yearly_sum = df.groupby('period')[['revenue', 'profit']].sum().reset_index()
        fig_trend_all = px.bar(yearly_sum, x='period', y='revenue', title="전체 매출 추이")
        st.plotly_chart(fig_trend_all, use_container_width=True)

# --- Tab 4: 수익성 분석 (Combo) ---
with tab4:
    st.subheader("Profitability Deep Dive")
    if not df.empty:
        top10 = df.nlargest(10, 'revenue')
        fig_combo = go.Figure()
        fig_combo.add_trace(go.Bar(x=top10['corp_name'], y=top10['revenue'], name='매출(좌)', marker_color='#3366CC', yaxis='y'))
        fig_combo.add_trace(go.Scatter(x=top10['corp_name'], y=top10['opm'], name='이익률(우)', marker_color='#FF9900', yaxis='y2'))
        fig_combo.update_layout(yaxis2=dict(overlaying='y', side='right'))
        st.plotly_chart(fig_combo, use_container_width=True)
