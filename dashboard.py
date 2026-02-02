import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART 실적 대시보드", layout="wide")

st.title("📊 DART 상장사 실적 모니터링")
st.markdown("매일 자동으로 업데이트되는 실적 데이터를 시각화합니다.")

# -----------------------------------------------------------------------------
# 2. 데이터 로드 (GitHub Raw CSV URL 사용)
# -----------------------------------------------------------------------------
# ★ 수정필요: 본인의 GitHub ID로 변경하세요 (YH4762)
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=21600) # 수정됨: 6시간(21600초)마다 캐시 갱신
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        
        # [Tip] 혹시 나중에 차트가 이상하게 나오면(숫자 정렬 안됨 등), 아래 주석을 풀고 사용하세요
        # 숫자에 콤마(,)가 섞여서 문자로 인식될 경우를 대비한 안전장치입니다.
        # for col in ['revenue', 'profit']:
        #     if col in df.columns and df[col].dtype == object:
        #         df[col] = df[col].str.replace(',', '').astype(float)
        
        return df
    except Exception as e:
        # 에러 확인을 위해 에러 메시지를 잠깐 출력할 수도 있습니다 (선택사항)
        # st.error(f"데이터 로드 실패: {e}") 
        return pd.DataFrame()

df = load_data()

# -----------------------------------------------------------------------------
# 3. 대시보드 구성
# -----------------------------------------------------------------------------
if df.empty:
    st.info("⏳ 아직 수집된 데이터가 없습니다. (봇이 작동할 때까지 대기 중)")
    st.markdown("데이터가 쌓이면 이곳에 자동으로 차트와 표가 나타납니다.")
else:
    # (1) 최신 공시 요약 (상단 지표)
    st.subheader("🔥 최신 실적 공시 Top 5")
    # 최신순 정렬 (tail을 뒤집어서 보여줌)
    st.dataframe(df.tail(5)[::-1], use_container_width=True)

    # (2) 주요 지표 시각화
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💰 기업별 매출액 (Revenue)")
        if 'revenue' in df.columns:
            # 텍스트가 겹치지 않게 가로형 막대그래프(orientation='h') 추천
            fig_rev = px.bar(df, x='corp_name', y='revenue', 
                             title="매출액 비교", color='revenue')
            st.plotly_chart(fig_rev, use_container_width=True)

    with col2:
        st.subheader("📈 영업이익 (Profit)")
        if 'profit' in df.columns:
            fig_prof = px.bar(df, x='corp_name', y='profit', 
                              title="영업이익 비교", color='profit')
            st.plotly_chart(fig_prof, use_container_width=True)

    # (3) 원본 데이터 검색
    with st.expander("🔍 전체 데이터 리스트 보기"):
        st.dataframe(df.sort_index(ascending=False)) # 최신순으로 정렬해서 보여주기
