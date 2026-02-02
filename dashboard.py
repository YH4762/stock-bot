import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Yeouido Pro Dashboard", layout="wide", page_icon="📈")

# [함수] 큰 숫자 포맷팅 (KPI 카드용 - 조/억/백만)
def format_big_number(value):
    if pd.isna(value) or value == 0: return "-"
    val = float(value)
    if abs(val) >= 1000000: return f"{val/1000000:,.1f}조"
    elif abs(val) >= 100:   return f"{val/100:,.1f}억"
    else: return f"{val:,.0f}백만"

# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리 (QoQ 로직 추가)
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
    
    # 2. 숫자 전처리 (백만 단위 변환)
    target_cols = ['revenue', 'profit', 'net_income', 'cash_flow']
    for col in target_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            df[col] = df[col].fillna(0) / 1000000 

    # 3. 시계열 컬럼 및 정렬
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    df = df.sort_values(['corp_name', 'year', 'quarter']) # 정렬 필수

    # 4. 이익률(OPM)
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] != 0 else 0, axis=1)

    # ---------------------------------------------------------
    # [NEW] QoQ (전분기 대비 증감률) 계산
    # ---------------------------------------------------------
    # 기업별로 그룹핑하여 바로 앞 행(shift(1))과 비교
    df['rev_qoq'] = df.groupby('corp_name')['revenue'].pct_change().fillna(0) * 100
    df['prof_qoq'] = df.groupby('corp_name')['profit'].pct_change().fillna(0) * 100

    # YoY (전년 동기 대비) 계산
    df['prev_year'] = df['year'] - 1
    df_prev = df[['corp_name', 'year', 'quarter', 'revenue', 'profit']].copy()
    df_prev = df_prev.rename(columns={'year': 'join_year', 'revenue': 'rev_prev', 'profit': 'prof_prev'})
    
    df = pd.merge(df, df_prev, left_on=['corp_name', 'prev_year', 'quarter'], right_on=['corp_name', 'join_year', 'quarter'], how='left')
    
    df['rev_yoy'] = ((df['revenue'] - df['rev_prev']) / df['rev_prev'] * 100).fillna(0)
    df['prof_yoy'] = ((df['profit'] - df['prof_prev']) / df['prof_prev'] * 100).fillna(0)
    
    # 안전장치: 병합 후 period 다시 확인
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    
    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🏢 Analysis Console")
    
    if not raw_df.empty:
        # 4Q 보정
        st.subheader("⚙️ 옵션")
        use_iso_4q = st.checkbox("4Q(누적) 개별 분기 변환", value=True)
        
        st.divider()

        # 필터링
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업 선택 (Target)", all_corps, placeholder="기업을 선택하세요")
        
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("연도 (Year)", all_years, default=all_years[:2])
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("분기 (Quarter)", all_q, default=all_q)
        
        st.divider()
        st.info("💡 팁: '급상승 Top 20' 메뉴에서 유망 기업을 발굴하세요.")
        
    else:
        selected_corps, sel_year, sel_q = [], [], []
        use_iso_4q = False

# -----------------------------------------------------------------------------
# 4. 데이터 가공 (4Q 보정)
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.error("데이터 로딩 실패")
    st.stop()

df = raw_df.copy()

if use_iso_4q:
    df = df.sort_values(['corp_name', 'year', 'quarter'])
    pivot = df[df['quarter'].isin(['1Q', '2Q', '3Q'])].pivot_table(
        index=['corp_name', 'year'], values=['revenue', 'profit', 'net_income'], aggfunc='sum'
    ).reset_index().rename(columns={'revenue': 'r_sum', 'profit': 'p_sum', 'net_income': 'n_sum'})
    
    df = pd.merge(df, pivot, on=['corp_name', 'year'], how='left')
    mask_4q = df['quarter'] == '4Q'
    for col, sum_col in zip(['revenue', 'profit', 'net_income'], ['r_sum', 'p_sum', 'n_sum']):
        if col in df.columns:
            df.loc[mask_4q, col] = df.loc[mask_4q, col] - df.loc[mask_4q, sum_col].fillna(0)
    
    # 보정 후 OPM 재계산
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] != 0 else 0, axis=1)

# 필터 적용
filtered_df = df.copy()
if selected_corps: filtered_df = filtered_df[filtered_df['corp_name'].isin(selected_corps)]
if sel_year: filtered_df = filtered_df[filtered_df['year'].isin(sel_year)]
if sel_q: filtered_df = filtered_df[filtered_df['quarter'].isin(sel_q)]

# 엑셀 데이터
csv_data = filtered_df.to_csv(index=False).encode('utf-8-sig')

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📈 Yeouido Pro Dashboard")
st.markdown(f"**Data:** {len(filtered_df):,} rows | **Unit:** 백만 원 (Million KRW) | **4Q Fix:** {'On' if use_iso_4q else 'Off'}")

# KPI
if not filtered_df.empty:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 매출액", format_big_number(filtered_df['revenue'].sum()))
    k2.metric("총 영업이익", format_big_number(filtered_df['profit'].sum()))
    k3.metric("평균 이익률", f"{filtered_df['opm'].mean():.1f}%")
    k4.metric("분석 대상", f"{filtered_df['corp_name'].nunique()}개사")

st.divider()

# 탭 메뉴
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 종합 현황", 
    "🔥 급상승 Top 20 (NEW)", 
    "⚔️ 경쟁사 비교", 
    "📅 분기 분석", 
    "📈 추세"
])

# --- Tab 1: 종합 현황 ---
with tab1:
    st.subheader("🏆 상세 실적 리스트")
    if not filtered_df.empty:
        cols = ['corp_name', 'year', 'quarter', 'revenue', 'rev_qoq', 'rev_yoy', 'profit', 'prof_qoq', 'opm']
        table_df = filtered_df[[c for c in cols if c in filtered_df.columns]].sort_values(['revenue'], ascending=False)
        
        # [핵심] format=None으로 설정하면 Streamlit이 기본적으로 천단위 콤마를 넣어줍니다.
        st.dataframe(
            table_df,
            column_config={
                "corp_name": "기업명", "year": "연도", "quarter": "분기",
                "revenue": st.column_config.NumberColumn("매출액", format=None), # 콤마 자동 적용
                "rev_qoq": st.column_config.NumberColumn("매출QoQ", format="%.1f%%"),
                "rev_yoy": st.column_config.NumberColumn("매출YoY", format="%.1f%%"),
                "profit": st.column_config.NumberColumn("영업이익", format=None), # 콤마 자동 적용
                "prof_qoq": st.column_config.NumberColumn("이익QoQ", format="%.1f%%"),
                "opm": st.column_config.NumberColumn("이익률", format="%.1f%%")
            },
            use_container_width=True, height=600, hide_index=True
        )

# --- Tab 2: 급상승 Top 20 (NEW) ---
with tab2:
    st.subheader("🔥 지난 분기(QoQ) 대비 급상승 기업 Top 20")
    st.markdown("최근 데이터 기준, 직전 분기보다 실적이 크게 뛴 기업을 발굴합니다. (매출액 100억 이상 기업 대상)")
    
    # 최신 기간 데이터만 추출 (가장 최근 연도/분기)
    if not df.empty:
        last_year = df['year'].max()
        # 필터링과 무관하게 전체 데이터에서 발굴
        growth_df = df[
            (df['year'] == last_year) & 
            (df['revenue'] > 10000) # 매출 100억(10,000백만) 이상만 필터링 (노이즈 제거)
        ].copy()

        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("#### 🚀 매출액 성장률 (Revenue Growth)")
            top_rev = growth_df.nlargest(20, 'rev_qoq')[['corp_name', 'quarter', 'revenue', 'rev_qoq']]
            st.dataframe(
                top_rev,
                column_config={
                    "corp_name": "기업명", "quarter": "분기",
                    "revenue": st.column_config.NumberColumn("매출액 (백만)", format=None),
                    "rev_qoq": st.column_config.NumberColumn("성장률(QoQ)", format="%.1f%%")
                },
                hide_index=True, use_container_width=True
            )

        with c2:
            st.markdown("#### 💰 영업이익 성장률 (Profit Growth)")
            top_prof = growth_df.nlargest(20, 'prof_qoq')[['corp_name', 'quarter', 'profit', 'prof_qoq']]
            st.dataframe(
                top_prof,
                column_config={
                    "corp_name": "기업명", "quarter": "분기",
                    "profit": st.column_config.NumberColumn("영업이익 (백만)", format=None),
                    "prof_qoq": st.column_config.NumberColumn("성장률(QoQ)", format="%.1f%%")
                },
                hide_index=True, use_container_width=True
            )

# --- Tab 3: 경쟁사 비교 (매출 & 이익 동시 비교) ---
with tab3:
    st.subheader("⚔️ Peer Group 비교 (매출 & 이익)")
    c1, c2 = st.columns(2)
    opts = sorted(raw_df['corp_name'].unique())
    if len(opts) > 0:
        with c1: comp_a = st.selectbox("기업 A", opts, index=0)
        with c2: comp_b = st.selectbox("기업 B", opts, index=1 if len(opts)>1 else 0)

        df_comp = filtered_df[filtered_df['corp_name'].isin([comp_a, comp_b])].copy()
        
        if not df_comp.empty:
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                # 매출 비교
                fig = px.bar(df_comp.sort_values('period'), x='period', y='revenue', color='corp_name', barmode='group',
                             title="매출액 비교", text_auto=False)
                fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
            
            with col_chart2:
                # 영업이익 비교 (추가됨)
                fig2 = px.bar(df_comp.sort_values('period'), x='period', y='profit', color='corp_name', barmode='group',
                             title="영업이익 비교", text_auto=False)
                fig2.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                st.plotly_chart(fig2, use_container_width=True)

# --- Tab 4: 분기 분석 (매출 & 이익 동시) ---
with tab4:
    st.subheader("📅 분기별 계절성 (Seasonality)")
    if len(selected_corps) == 1:
        target = selected_corps[0]
        st.markdown(f"**{target}**의 연도별 실적 비교")
        
        target_df = filtered_df[filtered_df['corp_name'] == target].copy()
        target_df['year_str'] = target_df['year'].astype(str)
        
        col_q1, col_q2 = st.columns(2)
        
        with col_q1:
            fig = px.bar(target_df.sort_values(['year', 'quarter']), x='quarter', y='revenue', color='year_str', barmode='group',
                         title="분기별 매출액 (YoY)")
            fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
            
        with col_q2:
            fig2 = px.bar(target_df.sort_values(['year', 'quarter']), x='quarter', y='profit', color='year_str', barmode='group',
                         title="분기별 영업이익 (YoY)")
            fig2.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
            st.plotly_chart(fig2, use_container_width=True)
            
    else:
        st.info("기업을 하나만 선택하면 상세 분기 분석 차트가 나옵니다.")

# --- Tab 5: 추세 ---
with tab5:
    st.subheader("📈 전체 추세")
    if not filtered_df.empty:
        d_sum = filtered_df.groupby('period')[['revenue', 'profit']].sum().reset_index()
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=d_sum['period'], y=d_sum['revenue'], name='매출',
            text=d_sum['revenue'], texttemplate='%{text:,.0f}', textposition='auto'
        ))
        fig.add_trace(go.Scatter(
            x=d_sum['period'], y=d_sum['profit'], name='이익', line=dict(color='orange', width=3),
            mode='lines+markers+text', text=d_sum['profit'], texttemplate='%{text:,.0f}', textposition='top center'
        ))
        st.plotly_chart(fig, use_container_width=True)

with st.sidebar:
    st.download_button("💾 엑셀 다운로드", csv_data, "dart_analysis.csv", "text/csv")
