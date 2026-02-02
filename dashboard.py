import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Yeouido Pro Dashboard", layout="wide", page_icon="📈")

# [함수] 큰 숫자 포맷팅 (조/억 단위)
def format_big_number(value):
    if pd.isna(value) or value == 0: return "-"
    val = float(value)
    if abs(val) >= 1000000: return f"{val/1000000:,.1f}조"
    elif abs(val) >= 100:   return f"{val/100:,.1f}억"
    else: return f"{val:,.0f}백만"

# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리 (YoY 계산 로직 추가됨)
# -----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=3600)
def load_data():
    try:
        try: df = pd.read_csv(CSV_URL)
        except UnicodeDecodeError: df = pd.read_csv(CSV_URL, encoding='cp949')
    except: return pd.DataFrame()

    # 1. 컬럼명 통합
    rename_map = {
        '매출액': 'revenue', '영업이익': 'profit', '영업현금흐름': 'cash_flow', 
        '당기순이익': 'net_income', '순이익': 'net_income', 
        '분기순이익': 'net_income', '반기순이익': 'net_income', '연결당기순이익': 'net_income'
    }
    col_map = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=col_map)
    
    # 2. 숫자 전처리 (백만 단위)
    target_cols = ['revenue', 'profit', 'net_income', 'cash_flow']
    for col in target_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            df[col] = df[col].fillna(0) / 1000000 

    # 3. 시계열 컬럼
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    
    # 4. 이익률(OPM)
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] > 0 else 0, axis=1)

    # ---------------------------------------------------------
    # [NEW] YoY (전년 동기 대비 증감률) 계산 로직
    # ---------------------------------------------------------
    # 작년 데이터를 찾기 위해 '작년 연도' 컬럼 생성
    df['prev_year'] = df['year'] - 1
    
    # 자기 자신과 병합 (Self Merge) -> (현재 연도, 분기) == (작년 연도, 분기) 매칭
    df_prev = df[['corp_name', 'year', 'quarter', 'revenue', 'profit']].copy()
    df_prev = df_prev.rename(columns={'year': 'join_year', 'revenue': 'rev_prev', 'profit': 'prof_prev'})
    
    # 현재 데이터에 작년 데이터 붙이기
    df = pd.merge(
        df, df_prev, 
        left_on=['corp_name', 'prev_year', 'quarter'], 
        right_on=['corp_name', 'join_year', 'quarter'], 
        how='left'
    )
    
    # 증감률 계산 (%)
    df['rev_yoy'] = ((df['revenue'] - df['rev_prev']) / df['rev_prev'] * 100).fillna(0)
    df['prof_yoy'] = ((df['profit'] - df['prof_prev']) / df['prof_prev'] * 100).fillna(0)
    
    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (필터 & 다운로드)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🏢 Analysis Console")
    
    if not raw_df.empty:
        # 기업 선택
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("Target Companies", all_corps, placeholder="기업 선택")
        
        # 연도/분기
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("Year", all_years, default=all_years[:2])
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("Quarter", all_q, default=all_q)
        
        st.divider()
        
        # [NEW] 데이터 다운로드 버튼
        st.subheader("💾 Data Export")
        csv_data = raw_df.to_csv(index=False).encode('utf-8-sig') # 엑셀 한글 깨짐 방지
        st.download_button(
            label="전체 데이터 엑셀 다운로드",
            data=csv_data,
            file_name='dart_financial_data.csv',
            mime='text/csv',
        )
    else:
        selected_corps, sel_year, sel_q = [], [], []

# -----------------------------------------------------------------------------
# 4. 데이터 필터링
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.error("데이터 로딩 실패")
    st.stop()

df = raw_df.copy()
if selected_corps: df = df[df['corp_name'].isin(selected_corps)]
if sel_year: df = df[df['year'].isin(sel_year)]
if sel_q: df = df[df['quarter'].isin(sel_q)]

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📈 Yeouido Pro Dashboard")
st.markdown(f"**Data:** {len(df):,} rows | **Unit:** 백만 원 (Million KRW)")

# KPI 카드
if not df.empty:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 매출액", format_big_number(df['revenue'].sum()))
    k2.metric("총 영업이익", format_big_number(df['profit'].sum()))
    avg_opm = df['opm'].mean()
    k3.metric("평균 이익률 (OPM)", f"{avg_opm:.1f}%")
    k4.metric("분석 대상 기업", f"{df['corp_name'].nunique()}개사")

st.divider()

# 탭 메뉴 (경쟁사 비교 탭 추가됨)
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 종합 현황 (Overview)", 
    "⚔️ 경쟁사 비교 (Peer Group)", 
    "📅 분기 분석 (Seasonality)", 
    "📈 추세 (Trend)"
])

# --- Tab 1: 종합 현황 (YoY 추가) ---
with tab1:
    st.subheader("🏆 기업별 실적 및 성장률 (YoY)")
    st.caption("YoY: 전년 동기 대비 성장률 (Red: 성장, Blue: 역성장)")
    
    if not df.empty:
        cols = ['corp_name', 'year', 'quarter', 'revenue', 'rev_yoy', 'profit', 'prof_yoy', 'opm']
        # 필요한 컬럼만 추출
        table_df = df[[c for c in cols if c in df.columns]].sort_values(['revenue'], ascending=False)
        
        st.dataframe(
            table_df,
            column_config={
                "corp_name": "기업명", "year": "연도", "quarter": "분기",
                "revenue": st.column_config.NumberColumn("매출액", format="%d"),
                # [NEW] YoY 컬럼 포맷팅
                "rev_yoy": st.column_config.NumberColumn("매출성장(%)", format="%.1f%%"),
                "profit": st.column_config.NumberColumn("영업이익", format="%d"),
                "prof_yoy": st.column_config.NumberColumn("이익성장(%)", format="%.1f%%"),
                "opm": st.column_config.NumberColumn("이익률", format="%.1f%%")
            },
            use_container_width=True,
            height=600,
            hide_index=True
        )

# --- Tab 2: 경쟁사 비교 (New Feature) ---
with tab2:
    st.subheader("⚔️ Peer Group 1:1 비교 분석")
    
    # 비교할 두 기업 선택
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        comp_a = st.selectbox("기업 A 선택", options=sorted(raw_df['corp_name'].unique()), index=0)
    with col_sel2:
        # 두 번째 기업은 목록의 두 번째 값으로 기본 설정
        options_b = sorted(raw_df['corp_name'].unique())
        idx_b = 1 if len(options_b) > 1 else 0
        comp_b = st.selectbox("기업 B 선택", options=options_b, index=idx_b)

    # 데이터 준비
    df_compare = raw_df[raw_df['corp_name'].isin([comp_a, comp_b])].copy()
    
    if not df_compare.empty:
        # 1. 주요 지표 막대 비교
        st.markdown("#### 💰 매출액 & 영업이익 비교")
        fig_comp = px.bar(
            df_compare.sort_values('period'), 
            x='period', y='revenue', color='corp_name', barmode='group',
            title=f"{comp_a} vs {comp_b} 매출액 비교",
            color_discrete_sequence=['#3366CC', '#FF9900'] # 파랑 vs 주황
        )
        fig_comp.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
        st.plotly_chart(fig_comp, use_container_width=True)
        
        # 2. 이익률 꺾은선 비교
        st.markdown("#### 📊 영업이익률(OPM) 추이 비교")
        fig_opm = px.line(
            df_compare.sort_values('period'),
            x='period', y='opm', color='corp_name', markers=True,
            title=f"{comp_a} vs {comp_b} 수익성(OPM) 비교",
             color_discrete_sequence=['#3366CC', '#FF9900']
        )
        st.plotly_chart(fig_opm, use_container_width=True)

# --- Tab 3: 분기 분석 ---
with tab3:
    st.subheader("📅 연도별/분기별 실적 매트릭스")
    
    if len(selected_corps) == 1:
        target_corp = selected_corps[0]
        st.markdown(f"**{target_corp}**의 계절성 및 YoY 흐름 확인")
        
        corp_df = raw_df[raw_df['corp_name'] == target_corp].copy()
        corp_df['year_str'] = corp_df['year'].astype(str)
        
        # 그룹 바 차트
        fig_q = px.bar(
            corp_df.sort_values(['year', 'quarter']), 
            x='quarter', y='revenue', color='year_str', barmode='group',
            title=f"{target_corp} 분기별 매출 비교 (동기 대비)",
            color_discrete_sequence=px.colors.sequential.Blues
        )
        st.plotly_chart(fig_q, use_container_width=True)
        
        # 피벗 테이블
        pivot = corp_df.pivot_table(index='year', columns='quarter', values='revenue', aggfunc='sum')
        st.dataframe(pivot.style.format("{:,.0f}").background_gradient(cmap="Reds"), use_container_width=True)
        
    else:
        st.info("👈 사이드바에서 기업을 '1개만' 선택하면 상세 분기 분석 화면이 나타납니다.")

# --- Tab 4: 추세 분석 ---
with tab4:
    st.subheader("📈 전체 시장 트렌드")
    if not df.empty:
        daily_sum = df.groupby('period')[['revenue', 'profit']].sum().reset_index()
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(x=daily_sum['period'], y=daily_sum['revenue'], name='매출액', marker_color='#8884d8'))
        fig_trend.add_trace(go.Scatter(x=daily_sum['period'], y=daily_sum['profit'], name='영업이익', line=dict(color='orange', width=3)))
        st.plotly_chart(fig_trend, use_container_width=True)
