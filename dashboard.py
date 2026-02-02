import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART 실적 대시보드", layout="wide")

st.title("📊 DART 상장사 실적 모니터링")

# -----------------------------------------------------------------------------
# 2. 데이터 로드
# -----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=21600) 
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        
        # [핵심 수정] 한글 컬럼명을 코드가 인식하는 영어 이름으로 변경
        # 파일에 있는 '매출액' -> 'revenue', '영업이익' -> 'profit'으로 인식시킴
        rename_map = {
            '매출액': 'revenue',
            '영업이익': 'profit', 
            '순이익': 'net_income',
            '당기순이익': 'net_income'
        }
        df = df.rename(columns=rename_map)
        
        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# -----------------------------------------------------------------------------
# 3. 대시보드 구성
# -----------------------------------------------------------------------------
if df.empty:
    st.info("데이터를 불러오는 중이거나 비어있습니다.")
else:
    # (1) 데이터가 잘 로드되었는지 확인용 (상단에 살짝 보여줌)
    st.write(f"✅ 총 {len(df)}개의 데이터를 불러왔습니다.")

    # (2) 최신 데이터 보여주기
    st.subheader("🔥 데이터 미리보기")
    st.dataframe(df.head(5), use_container_width=True)

    # (3) 차트 그리기
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💰 매출액 (Revenue)")
        if 'revenue' in df.columns:
            # 상위 10개만 추려서 그리기 (데이터가 너무 많으면 그래프가 깨짐)
            top_rev = df.nlargest(10, 'revenue')
            fig_rev = px.bar(top_rev, x='corp_name', y='revenue', 
                             title="매출액 Top 10", color='revenue')
            st.plotly_chart(fig_rev, use_container_width=True)
        else:
            st.warning("'매출액' 데이터를 찾을 수 없습니다.")

    with col2:
        st.subheader("📈 영업이익 (Profit)")
        if 'profit' in df.columns:
            top_prof = df.nlargest(10, 'profit')
            fig_prof = px.bar(top_prof, x='corp_name', y='profit', 
                              title="영업이익 Top 10", color='profit')
            st.plotly_chart(fig_prof, use_container_width=True)

    with st.expander("🔍 전체 데이터 리스트"):
        st.dataframe(df)
