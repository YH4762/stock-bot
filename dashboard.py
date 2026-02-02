import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DART 실적 대시보드", layout="wide")

st.title("📊 DART 상장사 실적 모니터링")
st.markdown("매일 업데이트되는 기업 실적을 시각화합니다. (6시간 주기 갱신)")

# -----------------------------------------------------------------------------
# 2. 데이터 로드 (강력해진 버전)
# -----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/YH4762/stock-bot/main/financial_db.csv"

@st.cache_data(ttl=21600)
def load_data():
    df = pd.DataFrame()
    try:
        # [1단계] 기본(UTF-8)로 읽기 시도
        df = pd.read_csv(CSV_URL)
    except UnicodeDecodeError:
        try:
            # [2단계] 실패 시, 한국어 윈도우 형식(cp949)으로 재시도
            df = pd.read_csv(CSV_URL, encoding='cp949')
        except Exception as e:
            st.error(f"❌ 데이터 읽기 실패 (CP949): {e}")
            return pd.DataFrame()
    except Exception as e:
        # 그 외 다른 에러가 나면 화면에 출력해서 알려줌
        st.error(f"❌ 데이터 로드 중 알 수 없는 오류: {e}")
        return pd.DataFrame()

    # 데이터가 정상적으로 읽혔다면 컬럼 이름 변경
    if not df.empty:
        rename_map = {
            '매출액': 'revenue',
            '영업이익': 'profit',
            '순이익': 'net_income',
            '당기순이익': 'net_income'
        }
        df = df.rename(columns=rename_map)
    
    return df

df = load_data()

# -----------------------------------------------------------------------------
# 3. 대시보드 화면 구성
# -----------------------------------------------------------------------------
if df.empty:
    st.warning("⚠️ 데이터를 불러오지 못했습니다. 위의 에러 메시지를 확인해주세요.")
    st.info("팁: 파일이 GitHub에 'financial_db.csv'라는 이름으로 정확히 있는지 확인해주세요.")
else:
    # (1) 최신 데이터 테이블 (상단)
    st.subheader(f"🔥 최신 업데이트 ({len(df)}개 기업)")
    st.dataframe(df.tail(5)[::-1], use_container_width=True)

    # (2) 차트 그리기
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💰 매출액 Top 10")
        if 'revenue' in df.columns:
            top_rev = df.nlargest(10, 'revenue')
            fig_rev = px.bar(top_rev, x='corp_name', y='revenue', 
                             title="기업별 매출액", color='revenue')
            st.plotly_chart(fig_rev, use_container_width=True)
        else:
            st.error("데이터에 '매출액' 컬럼이 없습니다. (CSV 파일의 컬럼명을 확인하세요)")

    with col2:
        st.subheader("📈 영업이익 Top 10")
        if 'profit' in df.columns:
            top_prof = df.nlargest(10, 'profit')
            fig_prof = px.bar(top_prof, x='corp_name', y='profit', 
                              title="기업별 영업이익", color='profit')
            st.plotly_chart(fig_prof, use_container_width=True)
        else:
            st.error("데이터에 '영업이익' 컬럼이 없습니다.")

    # (3) 전체 데이터 보기 (하단)
    with st.expander("🔍 전체 데이터 리스트 열기"):
        st.dataframe(df.sort_index(ascending=False))
