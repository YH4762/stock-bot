import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Yeouido Pro Dashboard", layout="wide", page_icon="📈")

# [함수] 큰 숫자 포맷팅 (KPI 카드용)
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
    
    # 2. 숫자 전처리 (백만 단위 변환 & NaN 처리)
    target_cols = ['revenue', 'profit', 'net_income', 'cash_flow']
    for col in target_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce')
            
            df[col] = df[col].fillna(0)
            
            # [핵심] 백만 원 단위로 변환
            df[col] = df[col] / 1000000 

    # 3. 시계열 컬럼 생성 (안전장치 1)
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    
    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (필터 & 옵션)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🏢 Analysis Console")
    
    if not raw_df.empty:
        # 4Q 보정 옵션
        st.subheader("⚙️ 데이터 보정")
        use_iso_4q = st.checkbox("4Q(누적)를 개별 분기로 변환", value=True)
        
        st.divider()

        # 필터링
        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("Target Companies", all_corps, placeholder="기업 선택")
        
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("Year", all_years, default=all_years[:2])
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("Quarter", all_q, default=all_q)
        
        st.divider()
        st.caption("All units in Million KRW")
        
    else:
        selected_corps, sel_year, sel_q = [], [], []
        use_iso_4q = False

# -----------------------------------------------------------------------------
# 4. 데이터 가공 (4Q 역산 & YoY)
# -----------------------------------------------------------------------------
if raw_df.empty:
    st.error("데이터를 불러올 수 없습니다.")
    st.stop()

df = raw_df.copy()

# [로직 1] 4분기 누적 -> 개별 분기 변환
if use_iso_4q:
    df = df.sort_values(['corp_name', 'year', 'quarter'])
    
    # 1~3Q 합계 계산
    pivot = df[df['quarter'].isin(['1Q', '2Q', '3Q'])].pivot_table(
        index=['corp_name', 'year'], 
        values=['revenue', 'profit', 'net_income'], 
        aggfunc='sum'
    ).reset_index()
    
    pivot = pivot.rename(columns={'revenue': 'r_sum', 'profit': 'p_sum', 'net_income': 'n_sum'})
    
    # 원본에 병합
    df = pd.merge(df, pivot, on=['corp_name', 'year'], how='left')
    
    # 4Q 값 보정
    mask_4q = df['quarter'] == '4Q'
    for col, sum_col in zip(['revenue', 'profit', 'net_income'], ['r_sum', 'p_sum', 'n_sum']):
        if col in df.columns:
            # 4Q = 누적 - (1~3Q합)
            df.loc[mask_4q, col] = df.loc[mask_4q, col] - df.loc[mask_4q, sum_col].fillna(0)

# [로직 2] 이익률(OPM) 재계산 (보정된 값 반영)
if 'revenue' in df.columns and 'profit' in df.columns:
    df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] != 0 else 0, axis=1)

# [로직 3] YoY 계산
df['prev_year'] = df['year'] - 1
df_prev = df[['corp_name', 'year', 'quarter', 'revenue', 'profit']].copy()
df_prev = df_prev.rename(columns={'year': 'join_year', 'revenue': 'rev_prev', 'profit': 'prof_prev'})

# 병합
df = pd.merge(df, df_prev, left_on=['corp_name', 'prev_year', 'quarter'], right_on=['corp_name', 'join_year', 'quarter'], how='left')

# 증감률 계산
df['rev_yoy'] = ((df['revenue'] - df['rev_prev']) / df['rev_prev'] * 100).fillna(0)
df['prof_yoy'] = ((df['profit'] - df['prof_prev']) / df['prof_prev'] * 100).fillna(0)

# [안전장치] 병합 과정에서 period가 사라졌을 수 있으므로 다시 생성
df['period'] = df['year'].astype(str) + "-" + df['quarter']

# -----------------------------------------------------------------------------
# 5. 필터 적용
# -----------------------------------------------------------------------------
if selected_corps: df = df[df['corp_name'].isin(selected_corps)]
if sel_year: df = df[df['year'].isin(sel_year)]
if sel_q: df = df[df['quarter'].isin(sel_q)]

# 엑셀 다운로드용 데이터
csv_data = df.to_csv(index=False).encode('utf-8-sig')

# -----------------------------------------------------------------------------
# 6. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📈 Yeouido Pro Dashboard")
st.markdown(f"**Data:** {len(df):,} rows | **Unit:** 백만 원 (Million KRW) | **4Q Correction:** {'On' if use_iso_4q else 'Off'}")

# KPI 카드
if not df.empty:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 매출액", format_big_number(df['revenue'].sum()))
    k2.metric("총 영업이익", format_big_number(df['profit'].sum()))
    k3.metric("평균 이익률 (OPM)", f"{df['opm'].mean():.1f}%")
    k4.metric("분석 대상", f"{df['corp_name'].nunique()}개사")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📊 종합 현황", "⚔️ 경쟁사 비교", "📅 분기 분석", "📈 추세"])

# --- Tab 1: 종합 현황 (Fancy Formatting) ---
with tab1:
    st.subheader("🏆 기업별 실적 (백만 원 단위)")
    if not df.empty:
        cols = ['corp_name', 'year', 'quarter', 'revenue', 'rev_yoy', 'profit', 'prof_yoy', 'opm', 'net_income']
        # 컬럼 존재 여부 확인 후 선택
        valid_cols = [c for c in cols if c in df.columns]
        table_df = df[valid_cols].sort_values(['revenue'], ascending=False)
        
        st.dataframe(
            table_df,
            column_config={
                "corp_name": "기업명", "year": "연도", "quarter": "분기",
                # [핵심] format="%d" -> 소수점 숨기고 정수만 표시 (콤마 자동)
                "revenue": st.column_config.NumberColumn("매출액", format="%d"),
                "rev_yoy": st.column_config.NumberColumn("매출성장", format="%.1f%%"),
                "profit": st.column_config.NumberColumn("영업이익", format="%d"),
                "prof_yoy": st.column_config.NumberColumn("이익성장", format="%.1f%%"),
                "opm": st.column_config.NumberColumn("이익률", format="%.1f%%"),
                "net_income": st.column_config.NumberColumn("순이익", format="%d")
            },
            use_container_width=True, height=600, hide_index=True
        )

# --- Tab 2: 경쟁사 비교 ---
with tab2:
    st.subheader("⚔️ Peer Group 1:1 비교")
    c1, c2 = st.columns(2)
    # 기업 목록이 있을 때만 렌더링
    opts = sorted(raw_df['corp_name'].unique())
    if len(opts) > 0:
        with c1: comp_a = st.selectbox("기업 A", options=opts, index=0)
        with c2: comp_b = st.selectbox("기업 B", options=opts, index=1 if len(opts)>1 else 0)

        df_comp = df[df['corp_name'].isin([comp_a, comp_b])].copy()
        if not df_comp.empty:
            # text_auto='.2s' 대신 '%{y:,.0f}' 사용해서 정수 콤마 포맷 적용
            fig = px.bar(df_comp.sort_values('period'), x='period', y='revenue', color='corp_name', barmode='group',
                         title="매출액 비교 (백만)", text_auto=False)
            fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
            
            fig2 = px.line(df_comp.sort_values('period'), x='period', y='opm', color='corp_name', markers=True,
                           title="이익률(%) 비교")
            st.plotly_chart(fig2, use_container_width=True)

# --- Tab 3: 분기 분석 ---
with tab3:
    st.subheader("📅 계절성 확인")
    if len(selected_corps) == 1:
        target = selected_corps[0]
        st.markdown(f"**{target}**의 분기별 패턴")
        
        target_df = df[df['corp_name'] == target].copy()
        target_df['year_str'] = target_df['year'].astype(str)
        
        fig = px.bar(target_df.sort_values(['year', 'quarter']), x='quarter', y='revenue', color='year_str', barmode='group',
                     title="분기별 실적 비교 (YoY)")
        fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("기업을 하나만 선택하면 상세 분기 분석 차트가 나옵니다.")

# --- Tab 4: 추세 (에러 수정됨) ---
with tab4:
    st.subheader("📈 전체 추세")
    if not df.empty:
        # [에러 해결] period 컬럼을 기준으로 groupby
        # period 컬럼은 위에서 [안전장치]로 반드시 생성됨.
        d_sum = df.groupby('period')[['revenue', 'profit']].sum().reset_index()
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=d_sum['period'], y=d_sum['revenue'], name='매출',
            text=d_sum['revenue'], texttemplate='%{text:,.0f}', textposition='auto' # 콤마 포맷
        ))
        fig.add_trace(go.Scatter(
            x=d_sum['period'], y=d_sum['profit'], name='이익', line=dict(color='orange'),
            mode='lines+markers+text', text=d_sum['profit'], texttemplate='%{text:,.0f}', textposition='top center'
        ))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("표시할 데이터가 없습니다.")

with st.sidebar:
    st.download_button("💾 엑셀 다운로드", csv_data, "dart_analysis.csv", "text/csv")
