import streamlit as st
import pandas as pd
import numpy as np # inf 처리를 위해 추가
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

    # 3. 정렬 및 시계열 컬럼
    df = df.sort_values(['corp_name', 'year', 'quarter'])
    df['period'] = df['year'].astype(str) + "-" + df['quarter']

    # 4. 이익률(OPM)
    if 'revenue' in df.columns and 'profit' in df.columns:
        df['opm'] = df.apply(lambda x: (x['profit'] / x['revenue'] * 100) if x['revenue'] != 0 else 0, axis=1)

    # ---------------------------------------------------------
    # [QoQ & YoY 계산] - 전체 데이터 기준 (필터링 전 수행해야 정확함)
    # ---------------------------------------------------------
    # QoQ
    df['rev_qoq'] = df.groupby('corp_name')['revenue'].pct_change().fillna(0) * 100
    df['prof_qoq'] = df.groupby('corp_name')['profit'].pct_change().fillna(0) * 100

    # 무한대(inf) 처리: 전분기 0원이었던 경우 성장률이 무한대로 뜸 -> 0이나 999%로 치환
    df.replace([np.inf, -np.inf], 0, inplace=True)

    # YoY
    df['prev_year'] = df['year'] - 1
    df_prev = df[['corp_name', 'year', 'quarter', 'revenue', 'profit']].copy()
    df_prev = df_prev.rename(columns={'year': 'join_year', 'revenue': 'rev_prev', 'profit': 'prof_prev'})
    
    df = pd.merge(df, df_prev, left_on=['corp_name', 'prev_year', 'quarter'], right_on=['corp_name', 'join_year', 'quarter'], how='left')
    
    df['rev_yoy'] = ((df['revenue'] - df['rev_prev']) / df['rev_prev'] * 100).fillna(0)
    df['prof_yoy'] = ((df['profit'] - df['prof_prev']) / df['prof_prev'] * 100).fillna(0)
    df.replace([np.inf, -np.inf], 0, inplace=True) # YoY도 inf 제거
    
    # 안전장치
    df['period'] = df['year'].astype(str) + "-" + df['quarter']
    
    return df

raw_df = load_data()

# -----------------------------------------------------------------------------
# 3. 사이드바 (필터링)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🏢 Analysis Console")
    
    if not raw_df.empty:
        st.subheader("⚙️ 데이터 옵션")
        use_iso_4q = st.checkbox("4Q(누적) 개별 분기 변환", value=True)
        
        st.divider()

        all_corps = sorted(raw_df['corp_name'].unique())
        selected_corps = st.multiselect("기업 선택", all_corps, placeholder="전체 보기 (비워두면 전체)")
        
        all_years = sorted(raw_df['year'].unique(), reverse=True)
        sel_year = st.multiselect("연도", all_years, default=all_years[:1]) # 기본: 최신 연도만
        all_q = sorted(raw_df['quarter'].unique())
        sel_q = st.multiselect("분기", all_q, default=['1Q', '2Q', '3Q', '4Q']) # 기본: 전체 분기
        
        st.divider()
        st.caption("모든 금액 단위: 백만 원")
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

# [핵심 변경] 필터 적용 (이제 이 filtered_df가 모든 탭의 기준이 됩니다)
filtered_df = df.copy()
if selected_corps: filtered_df = filtered_df[filtered_df['corp_name'].isin(selected_corps)]
if sel_year: filtered_df = filtered_df[filtered_df['year'].isin(sel_year)]
if sel_q: filtered_df = filtered_df[filtered_df['quarter'].isin(sel_q)]

csv_data = filtered_df.to_csv(index=False).encode('utf-8-sig')

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📈 Yeouido Pro Dashboard")
st.markdown(f"**Selected Data:** {len(filtered_df):,} rows | **Unit:** 백만 원 (Million KRW)")

if not filtered_df.empty:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 매출액", format_big_number(filtered_df['revenue'].sum()))
    k2.metric("총 영업이익", format_big_number(filtered_df['profit'].sum()))
    k3.metric("평균 이익률", f"{filtered_df['opm'].mean():.1f}%")
    k4.metric("분석 대상", f"{filtered_df['corp_name'].nunique()}개사")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 종합 현황", 
    "🔥 급상승 Top 20", 
    "⚔️ 경쟁사 비교", 
    "📅 분기 분석", 
    "📈 추세"
])

# [스타일 함수] 콤마 강제 적용을 위한 Pandas Styler
def apply_comma_style(dataframe, cols_to_format):
    format_dict = {}
    for col in cols_to_format:
        if col in dataframe.columns:
            if 'qoq' in col or 'yoy' in col or 'opm' in col:
                format_dict[col] = "{:+.1f}%"
            else:
                format_dict[col] = "{:,.0f}"
    return dataframe.style.format(format_dict)

# --- Tab 1: 종합 현황 ---
with tab1:
    st.subheader("🏆 상세 실적 리스트")
    if not filtered_df.empty:
        cols = ['corp_name', 'year', 'quarter', 'revenue', 'rev_qoq', 'rev_yoy', 'profit', 'prof_qoq', 'opm', 'net_income']
        table_df = filtered_df[[c for c in cols if c in filtered_df.columns]].sort_values(['revenue'], ascending=False)
        
        styled_df = apply_comma_style(table_df, ['revenue', 'profit', 'net_income', 'rev_qoq', 'rev_yoy', 'prof_qoq', 'opm'])
        
        st.dataframe(
            styled_df,
            column_config={
                "corp_name": "기업명", "year": "연도", "quarter": "분기",
                "revenue": "매출액", "rev_qoq": "매출QoQ", "rev_yoy": "매출YoY",
                "profit": "영업이익", "prof_qoq": "이익QoQ", "opm": "이익률", "net_income": "순이익"
            },
            use_container_width=True, height=600, hide_index=True
        )

# --- Tab 2: 급상승 Top 20 (필터 연동됨) ---
with tab2:
    st.subheader("🔥 선택된 기간 내 급상승 Top 20")
    st.markdown("사이드바에서 선택한 **연도/분기** 데이터 중 성장률이 높은 기업을 보여줍니다. (매출 100억 이상)")
    
    if not filtered_df.empty:
        # [수정됨] filtered_df를 사용하므로 사이드바 선택 값만 남음
        # 노이즈 제거: 매출 100억 이상
        growth_df = filtered_df[filtered_df['revenue'] > 10000].copy()

        if growth_df.empty:
            st.warning("조건에 맞는 데이터가 없습니다. (매출 100억 미만이거나 데이터 부족)")
        else:
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("#### 🚀 매출 급상승 (QoQ)")
                # 필터링된 데이터 중에서 Top 20 선정
                top_rev = growth_df.nlargest(20, 'rev_qoq')[['corp_name', 'year', 'quarter', 'revenue', 'rev_qoq']]
                st.dataframe(
                    apply_comma_style(top_rev, ['revenue', 'rev_qoq']),
                    column_config={"corp_name": "기업명", "revenue": "매출액", "rev_qoq": "성장률"},
                    hide_index=True, use_container_width=True
                )

            with c2:
                st.markdown("#### 💰 이익 급상승 (QoQ)")
                top_prof = growth_df.nlargest(20, 'prof_qoq')[['corp_name', 'year', 'quarter', 'profit', 'prof_qoq']]
                st.dataframe(
                    apply_comma_style(top_prof, ['profit', 'prof_qoq']),
                    column_config={"corp_name": "기업명", "profit": "영업이익", "prof_qoq": "성장률"},
                    hide_index=True, use_container_width=True
                )

# --- Tab 3: 경쟁사 비교 ---
with tab3:
    st.subheader("⚔️ Peer Group 비교")
    c1, c2 = st.columns(2)
    opts = sorted(raw_df['corp_name'].unique())
    if len(opts) > 0:
        with c1: comp_a = st.selectbox("기업 A", opts, index=0)
        with c2: comp_b = st.selectbox("기업 B", opts, index=1 if len(opts)>1 else 0)

        # 필터링된 데이터 안에서 비교 (선택된 기간만 비교됨)
        df_comp = filtered_df[filtered_df['corp_name'].isin([comp_a, comp_b])].copy()
        
        if not df_comp.empty:
            cc1, cc2 = st.columns(2)
            with cc1:
                fig = px.bar(df_comp.sort_values('period'), x='period', y='revenue', color='corp_name', barmode='group', title="매출액 비교")
                fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
            with cc2:
                fig2 = px.bar(df_comp.sort_values('period'), x='period', y='profit', color='corp_name', barmode='group', title="영업이익 비교")
                fig2.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("선택된 기간에 해당 기업의 데이터가 없습니다.")

# --- Tab 4: 분기 분석 ---
with tab4:
    st.subheader("📅 분기별 계절성")
    if len(selected_corps) == 1:
        target = selected_corps[0]
        # 여기서는 연도 비교를 위해 전체 데이터(df)에서 해당 기업만 다시 가져오는 게 좋을 수도 있지만,
        # 사용자 요청대로 "선택된 기간" 내에서 보여줍니다.
        target_df = filtered_df[filtered_df['corp_name'] == target].copy()
        target_df['year_str'] = target_df['year'].astype(str)
        
        if not target_df.empty:
            cc1, cc2 = st.columns(2)
            with cc1:
                fig = px.bar(target_df.sort_values(['year', 'quarter']), x='quarter', y='revenue', color='year_str', barmode='group', title="매출액")
                fig.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
            with cc2:
                fig2 = px.bar(target_df.sort_values(['year', 'quarter']), x='quarter', y='profit', color='year_str', barmode='group', title="영업이익")
                fig2.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("선택된 기간에 데이터가 없습니다.")
    else:
        st.info("기업을 하나만 선택하면 상세 차트가 나옵니다.")

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
