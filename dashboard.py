import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Yeouido Pro Dashboard", layout="wide", page_icon="📈")

# [함수] 큰 숫자 포맷팅
def format_big_number(value):
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

    # 3. 이익률(OPM) - 보정 전 기초 계산
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] > 0 else 0, axis=1)

    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (스마트 보정 기능 추가)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🏢 Analysis Console")
    
    if not raw_df.empty:
        # [NEW] 4분기 보정 토글 (핵심 기능)
        st.subheader("⚙️ 데이터 보정 (Smart Fix)")
        use_iso_4q = st.checkbox("4Q(누적)를 개별 분기로 변환", value=True, help="체크 시: 4Q(1년치)에서 1~3Q 합계를 뺍니다.")
        
        st.divider()

        # 필터링
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("Target Companies", all_corps, placeholder="기업 선택")
        
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("Year", all_years, default=all_years[:2])
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("Quarter", all_q, default=all_q)
        
        st.divider()
        
        # 엑셀 다운로드
        st.subheader("💾 Export")
        
    else:
        selected_corps, sel_year, sel_q = [], [], []
        use_iso_4q = False

# -----------------------------------------------------------------------------
# 4. 스마트 데이터 가공 (4Q 역산 로직)
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.error("데이터 로딩 실패")
    st.stop()

df = raw_df.copy()

# [핵심 로직] 4분기 누적 -> 개별 분기 변환
if use_iso_4q:
    # 1. 계산을 위해 정렬
    df = df.sort_values(['corp_name', 'year', 'quarter'])
    
    # 2. 기업/연도별로 그룹화하여 1,2,3분기 합계 구하기
    # (pivot table을 이용해서 1,2,3Q 데이터를 옆으로 펼침)
    pivot = df[df['quarter'].isin(['1Q', '2Q', '3Q'])].pivot_table(
        index=['corp_name', 'year'], 
        values=['revenue', 'profit', 'net_income'], 
        aggfunc='sum'
    ).reset_index()
    
    pivot = pivot.rename(columns={
        'revenue': 'rev_sum_123', 
        'profit': 'prof_sum_123', 
        'net_income': 'net_sum_123'
    })
    
    # 3. 원본 데이터에 합계 데이터 붙이기
    df = pd.merge(df, pivot, on=['corp_name', 'year'], how='left')
    
    # 4. 4Q 데이터일 경우에만 뺄셈 수행 (누적 - 1~3Q합계)
    # (주의: 만약 1~3Q 데이터가 없어서 0이면 4Q가 그대로 유지됨)
    mask_4q = df['quarter'] == '4Q'
    
    # 4Q 값을 보정 (음수가 나오면 데이터 오류 가능성이 있으므로 0 처리 하거나 그대로 둠. 여기선 그대로 둠)
    for col in ['revenue', 'profit', 'net_income']:
        sum_col = f"{col[:4] if col!='net_income' else 'net'}_sum_123" # 컬럼명 매칭
        # 컬럼 이름이 달라서 수동 매핑
        if col == 'revenue': sum_col = 'rev_sum_123'
        if col == 'profit': sum_col = 'prof_sum_123'
        if col == 'net_income': sum_col = 'net_sum_123'
        
        # 4Q 값 = (원래 4Q값) - (1~3Q 합계)
        # 단, 1~3Q 합계가 NaN이 아니어야 함
        df.loc[mask_4q, col] = df.loc[mask_4q, col] - df.loc[mask_4q, sum_col].fillna(0)

    # 5. OPM(이익률) 재계산 (값이 바뀌었으므로)
    df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] != 0 else 0, axis=1)

# [기존 로직] YoY 계산
df['prev_year'] = df['year'] - 1
df_prev = df[['corp_name', 'year', 'quarter', 'revenue', 'profit']].copy()
df_prev = df_prev.rename(columns={'year': 'join_year', 'revenue': 'rev_prev', 'profit': 'prof_prev'})
df = pd.merge(df, df_prev, left_on=['corp_name', 'prev_year', 'quarter'], right_on=['corp_name', 'join_year', 'quarter'], how='left')
df['rev_yoy'] = ((df['revenue'] - df['rev_prev']) / df['rev_prev'] * 100).fillna(0)
df['prof_yoy'] = ((df['profit'] - df['prof_prev']) / df['prof_prev'] * 100).fillna(0)

# 필터 적용
if selected_corps: df = df[df['corp_name'].isin(selected_corps)]
if sel_year: df = df[df['year'].isin(sel_year)]
if sel_q: df = df[df['quarter'].isin(sel_q)]

# 엑셀 다운로드 버튼 데이터 생성
csv_data = df.to_csv(index=False).encode('utf-8-sig')

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📈 Yeouido Pro Dashboard")
st.markdown(f"**Data:** {len(df):,} rows | **Unit:** 백만 원 | **4Q Correction:** {'On' if use_iso_4q else 'Off'}")

if not raw_df.empty and use_iso_4q == False:
    st.warning("⚠️ 현재 4Q 데이터가 '1년 누적' 상태일 수 있습니다. 정확한 분석을 위해 사이드바의 **[4Q 개별 분기 변환]**을 체크하세요.")

# KPI
if not df.empty:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 매출액", format_big_number(df['revenue'].sum()))
    k2.metric("총 영업이익", format_big_number(df['profit'].sum()))
    k3.metric("평균 이익률 (OPM)", f"{df['opm'].mean():.1f}%")
    k4.metric("분석 대상", f"{df['corp_name'].nunique()}개사")

st.divider()

# 탭 메뉴
tab1, tab2, tab3, tab4 = st.tabs(["📊 종합 현황", "⚔️ 경쟁사 비교", "📅 분기 분석", "📈 추세"])

# --- Tab 1: 종합 현황 ---
with tab1:
    st.subheader("🏆 기업별 실적 (Smart Calc 적용됨)")
    if not df.empty:
        cols = ['corp_name', 'year', 'quarter', 'revenue', 'rev_yoy', 'profit', 'prof_yoy', 'opm']
        table_df = df[[c for c in cols if c in df.columns]].sort_values(['revenue'], ascending=False)
        st.dataframe(
            table_df,
            column_config={
                "corp_name": "기업명", "year": "연도", "quarter": "분기",
                "revenue": st.column_config.NumberColumn("매출", format="%d"),
                "rev_yoy": st.column_config.NumberColumn("매출성장", format="%.1f%%"),
                "profit": st.column_config.NumberColumn("이익", format="%d"),
                "prof_yoy": st.column_config.NumberColumn("이익성장", format="%.1f%%"),
                "opm": st.column_config.NumberColumn("이익률", format="%.1f%%")
            },
            use_container_width=True, height=600, hide_index=True
        )

# --- Tab 2: 경쟁사 비교 ---
with tab2:
    st.subheader("⚔️ Peer Group 1:1 비교")
    c1, c2 = st.columns(2)
    with c1: comp_a = st.selectbox("기업 A", options=sorted(raw_df['corp_name'].unique()), index=0)
    with c2: 
        opts = sorted(raw_df['corp_name'].unique())
        comp_b = st.selectbox("기업 B", options=opts, index=1 if len(opts)>1 else 0)

    df_comp = df[df['corp_name'].isin([comp_a, comp_b])].copy()
    if not df_comp.empty:
        fig = px.bar(df_comp.sort_values('period'), x='period', y='revenue', color='corp_name', barmode='group',
                     title="매출액 비교 (백만)", text_auto='.2s')
        st.plotly_chart(fig, use_container_width=True)
        
        fig2 = px.line(df_comp.sort_values('period'), x='period', y='opm', color='corp_name', markers=True,
                       title="이익률(%) 비교")
        st.plotly_chart(fig2, use_container_width=True)

# --- Tab 3: 분기 분석 ---
with tab3:
    st.subheader("📅 계절성 확인 (Seasonality)")
    if len(selected_corps) == 1:
        target = selected_corps[0]
        st.markdown(f"**{target}**의 분기별 패턴 (4Q 보정 여부 확인 필요)")
        
        target_df = df[df['corp_name'] == target].copy()
        target_df['year_str'] = target_df['year'].astype(str)
        
        fig = px.bar(target_df.sort_values(['year', 'quarter']), x='quarter', y='revenue', color='year_str', barmode='group',
                     title="분기별 실적 비교 (YoY)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("기업을 하나만 선택하면 상세 분기 분석 차트가 나옵니다.")

# --- Tab 4: 추세 ---
with tab4:
    st.subheader("📈 전체 추세")
    if not df.empty:
        d_sum = df.groupby('period')[['revenue', 'profit']].sum().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Bar(x=d_sum['period'], y=d_sum['revenue'], name='매출'))
        fig.add_trace(go.Scatter(x=d_sum['period'], y=d_sum['profit'], name='이익', line=dict(color='orange')))
        st.plotly_chart(fig, use_container_width=True)

# 사이드바 다운로드 버튼 (맨 아래로 이동)
with st.sidebar:
    st.download_button("💾 엑셀 다운로드 (보정된 데이터)", csv_data, "dart_analysis.csv", "text/csv")
