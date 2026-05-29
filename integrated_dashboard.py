"""
integrated_dashboard.py — 주식종목추천 앱과 매수 타이밍 앱을 하나로 통합한 웹앱
기존의 app.py 와 market_timing_app.py 의 기능을 모두 포함하며,
탭(Tabs) 인터페이스를 통해 한 화면에서 쉽게 전환하며 볼 수 있습니다.
"""

import sys
import os
import warnings
from datetime import datetime, timedelta
from io import StringIO

import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
import FinanceDataReader as fdr

warnings.filterwarnings("ignore")

# pykrx는 OHLCV 및 투자자별 수급용 (app.py 종속성)
try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
    PYKRX_ERROR = ""
except Exception as e:
    PYKRX_AVAILABLE = False
    PYKRX_ERROR = str(e)

# ──────────────────────────────────────────
# Streamlit 페이지 설정 (최상단)
# ──────────────────────────────────────────
st.set_page_config(page_title="AI 통합 주식 대시보드", page_icon="📈", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #f1f5f9; }

/* 기본 메뉴 및 푸터 숨기기 (한글화/깔끔한 UI용) */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* 공통 타이틀 */
.main-title {
    font-size: 2.5rem; font-weight: 900; text-align: center; margin-top: 1rem;
    background: linear-gradient(to right, #38bdf8, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.sub-title { text-align: center; color: #94a3b8; font-size: 1.1rem; margin-bottom: 2rem; }

/* 타이밍 앱 카드 */
.card {
    background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(56, 189, 248, 0.2);
    border-radius: 1rem; padding: 1.5rem; margin-bottom: 1rem;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3); transition: transform 0.2s;
}
.card:hover { transform: translateY(-3px); border-color: rgba(56, 189, 248, 0.5); }
.card-title { font-size: 1.2rem; font-weight: 700; color: #38bdf8; margin-bottom: 0.5rem; }
.card-value { font-size: 2rem; font-weight: 900; color: #f8fafc; }
.card-desc { font-size: 0.95rem; color: #cbd5e1; margin-top: 0.5rem; line-height:1.4; }

/* 점수 표시 */
.score-huge { font-size: 5rem; font-weight: 900; text-align: center; margin: 0; line-height: 1; }
.score-label { font-size: 1.5rem; font-weight: 700; text-align: center; margin-top: 0.5rem; color: #cbd5e1; }
.text-bull { color: #10b981 !important; }
.text-bear { color: #ef4444 !important; }
.text-neutral { color: #f59e0b !important; }
hr { border-color: rgba(148, 163, 184, 0.2); }

/* 탭 스타일 조정 */
.stTabs [data-baseweb="tab-list"] {
    gap: 2rem;
}
.stTabs [data-baseweb="tab"] {
    height: 3rem;
    white-space: pre-wrap;
    background-color: transparent;
    border-radius: 0.5rem 0.5rem 0 0;
    gap: 1rem;
    padding-top: 1rem;
    padding-bottom: 1rem;
}
.stTabs [aria-selected="true"] {
    background-color: rgba(56, 189, 248, 0.1);
    border-bottom-color: #38bdf8;
}
</style>
""", unsafe_allow_html=True)


# =====================================================================
# [PART 1] 마켓 타이밍 로직 (market_timing_app.py 기반)
# =====================================================================

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def yahoo_chart(symbol: str, range_: str = "3mo", interval: str = "1d") -> dict | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        j = res.json()
        return j["chart"]["result"][0]
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_exchange_rate() -> float:
    try:
        url = "https://finance.naver.com/marketindex/exchangeList.naver"
        res = requests.get(url, timeout=8, headers=HEADERS)
        res.encoding = "euc-kr"
        df = pd.read_html(StringIO(res.text))[0]
        val = str(df.iloc[0, 1]).replace(",", "")
        return float(val)
    except Exception:
        pass
    try:
        result = yahoo_chart("USDKRW=X", range_="5d")
        if result:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
            return float(closes[-1])
    except Exception:
        pass
    return 1350.0

@st.cache_data(ttl=3600)
def get_us_treasury() -> float:
    try:
        result = yahoo_chart("^TNX", range_="5d")
        if result:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
            return round(float(closes[-1]), 2)
    except Exception:
        pass
    return 4.2

@st.cache_data(ttl=3600)
def get_kospi_series() -> pd.DataFrame:
    try:
        result = yahoo_chart("^KS11", range_="6mo")
        if result:
            ts = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
            df = pd.DataFrame({"date": pd.to_datetime(ts, unit="s"), "Close": closes})
            df = df.dropna(subset=["Close"]).set_index("date")
            df["MA20"] = df["Close"].rolling(20).mean()
            df["MA60"] = df["Close"].rolling(60).mean()
            return df.tail(70)
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_market_flow() -> dict:
    default = {"f_sum": 0, "i_sum": 0, "score": 0, "status": "데이터 없음"}
    try:
        result = yahoo_chart("069500.KS", range_="1mo")
        if not result: return default
        closes  = result["indicators"]["quote"][0]["close"]
        volumes = result["indicators"]["quote"][0]["volume"]
        data = [(c, v) for c, v in zip(closes, volumes) if c and v]
        if len(data) < 5: return default
        
        df = pd.DataFrame(data, columns=["close", "volume"])
        df["ma5"] = df["close"].rolling(5).mean()
        
        recent = df.tail(5)
        curr_close = recent["close"].iloc[-1]
        ma5_close  = recent["ma5"].iloc[-1]
        
        prev5_vol = df.iloc[-10:-5]["volume"].mean() if len(df) >= 10 else df["volume"].mean()
        curr5_vol = recent["volume"].mean()
        vol_ratio = curr5_vol / prev5_vol if prev5_vol > 0 else 1.0
        
        price_up = curr_close > ma5_close
        vol_surge = vol_ratio > 1.1
        
        flow_score = 0
        if price_up:   flow_score += 20
        if vol_surge:  flow_score += 20
        
        if price_up and vol_surge: status = "강한 매수세 (가격↑ + 거래량↑)"
        elif price_up: status = "완만한 매수세 (가격↑)"
        elif vol_surge: status = "거래량 급증 (방향 불확실)"
        else: status = "매도/관망 우세"
        
        avg_price = df["close"].mean()
        f_proxy = int((curr5_vol - prev5_vol) * avg_price / 1e8) if price_up else 0
        i_proxy = int(f_proxy * 0.4)
        
        return {
            "f_sum": f_proxy * 1e8, "i_sum": i_proxy * 1e8,
            "score": flow_score, "status": status,
            "vol_ratio": round(vol_ratio, 2), "price_up": price_up
        }
    except Exception:
        return default

def calc_market_timing():
    score = 0
    details = {}
    usd = get_exchange_rate()
    ust = get_us_treasury()
    macro_score = 0
    if usd < 1320:   macro_score += 15
    elif usd < 1370: macro_score += 10
    elif usd < 1400: macro_score += 5
    if ust < 4.0:    macro_score += 15
    elif ust < 4.4:  macro_score += 10
    elif ust < 4.6:  macro_score += 5
    score += macro_score
    details["macro"] = {"score": macro_score, "usd": usd, "ust": ust}

    kdf = get_kospi_series()
    tech_score = 0
    k_status, k_curr = "데이터 없음", 0
    if not kdf.empty and not kdf["MA60"].isna().all():
        curr = kdf["Close"].iloc[-1]
        ma20 = kdf["MA20"].iloc[-1]
        ma60 = kdf["MA60"].iloc[-1]
        k_curr = curr
        if curr > ma20:  tech_score += 15
        if ma20 > ma60:  tech_score += 15
        if curr > ma20 and ma20 > ma60: k_status = "정배열 상승추세"
        elif curr < ma20 and ma20 < ma60: k_status = "역배열 하락추세"
        else: k_status = "혼조세"
    score += tech_score
    details["tech"] = {"score": tech_score, "status": k_status, "kospi": k_curr}

    flow = get_market_flow()
    score += flow["score"]
    details["flow"] = flow

    return int(score), details

@st.cache_data(ttl=1800)
def get_top_stock_picks() -> pd.DataFrame:
    CANDIDATES = [
        ("005930", "삼성전자"),  ("000660", "SK하이닉스"), ("035420", "NAVER"),    ("005380", "현대차"),
        ("000270", "기아"),      ("051910", "LG화학"),    ("068270", "셀트리온"),  ("035720", "카카오"),
        ("105560", "KB금융"),    ("055550", "신한지주"),  ("028260", "삼성물산"),  ("012330", "현대모비스"),
        ("066570", "LG전자"),    ("003670", "포스코퓨처엠"), ("207940", "삼성바이오로직스"), ("006400", "삼성SDI"),
        ("096770", "SK이노베이션"), ("034020", "두산에너빌리티"), ("009150", "삼성전기"),  ("011200", "HMM"),
    ]
    picks = []
    for code, name in CANDIDATES:
        try:
            sym = f"{code}.KS"
            result = yahoo_chart(sym, range_="1mo")
            if not result: continue
            closes  = [c for c in result["indicators"]["quote"][0]["close"] if c]
            volumes = [v for v in result["indicators"]["quote"][0]["volume"] if v]
            if len(closes) < 10: continue
            curr = closes[-1]
            close_arr = np.array(closes)
            ma5, ma10 = close_arr[-5:].mean(), close_arr[-10:].mean()
            if curr < ma5 or ma5 < ma10: continue
            
            vol_arr  = np.array(volumes)
            avg_vol, curr_vol = vol_arr[:-5].mean(), vol_arr[-5:].mean()
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
            score = (curr * curr_vol) * 0.1 + (ma5 - ma10) / ma10 * 1000
            picks.append({
                "코드": code, "종목명": name, "현재가": int(curr),
                "거래대금(억)": int(curr * curr_vol / 1e8), "거래량비율": round(vol_ratio, 2), "점수": score
            })
        except Exception: continue

    if not picks: return pd.DataFrame()
    pdf = pd.DataFrame(picks).sort_values("점수", ascending=False).head(5)
    return pdf[["종목명", "현재가", "거래대금(억)", "거래량비율"]].reset_index(drop=True)


# =====================================================================
# [PART 2] 스마트 수급 스캐너 로직 (app.py 기반)
# =====================================================================

@st.cache_data(ttl=600)
def get_latest_valid_date():
    try:
        now = datetime.now()
        df = fdr.DataReader("005930", (now - timedelta(days=10)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'))
        if not df.empty: return df.index[-1].strftime('%Y%m%d')
    except: pass
    return (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

@st.cache_data(ttl=3600)
def scan_hybrid_flow(min_mktcap=2000, min_trading=5):
    try:
        df_krx = fdr.StockListing('KRX')
        df_krx['시가총액(억)'] = df_krx['Marcap'] / 1e8
        df_krx['거래대금(억)'] = df_krx['Amount'] / 1e8
        target_df = df_krx[(df_krx['시가총액(억)'] >= min_mktcap) & (df_krx['거래대금(억)'] >= min_trading)].copy()
        target_df = target_df.sort_values('거래대금(억)', ascending=False).head(200)

        rows = []
        progress_text = st.empty()
        bar = st.progress(0)
        total = len(target_df)

        for i, (_, row) in enumerate(target_df.iterrows()):
            try:
                if i % 5 == 0:
                    progress_text.text(f"스마트 스캔 중... ({i}/{total})")
                    bar.progress(i / total)
                volume_ratio = row['Volume'] / (row['Stocks'] * 0.001) if row['Stocks'] > 0 else 0
                rows.append({
                    '티커': row['Code'], '종목명': row['Name'], '현재가': int(row['Close']),
                    '등락률(%)': round(row['ChagesRatio'], 2), '시가총액(억)': round(row['시가총액(억)']),
                    '거래대금(억)': round(row['거래대금(억)'], 1), '수급점수': round(volume_ratio * abs(row['ChagesRatio']), 2),
                })
            except: continue

        progress_text.empty()
        bar.empty()
        df_result = pd.DataFrame(rows)
        if not df_result.empty: df_result.sort_values('수급점수', ascending=False, inplace=True)
        return df_result, get_latest_valid_date()
    except Exception as e:
        st.error(f"데이터 스캔 중 오류: {e}")
        return pd.DataFrame(), ""

@st.cache_data
def analyze_technical(ticker, base_date, engine="자동"):
    try:
        end = datetime.strptime(base_date, '%Y%m%d')
        start = end - timedelta(days=400)
        
        df = None
        use_pykrx = "pykrx" in engine or "자동" in engine
        use_fdr = "Naver" in engine or "자동" in engine
        
        if use_pykrx:
            try:
                df = stock.get_market_ohlcv_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
            except:
                pass
            
        if (df is None or df.empty) and use_fdr:
            df = fdr.DataReader(ticker, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if not df.empty:
                df = df.rename(columns={'Open': '시가', 'High': '고가', 'Low': '저가', 'Close': '종가', 'Volume': '거래량'})
                
        if df is None or df.empty or len(df) < 60: return '데이터부족', 0
        close = df['종가']
        df['MA20'], df['MA60'] = close.rolling(20).mean(), close.rolling(60).mean()
        delta = close.diff()
        up, down = delta.clip(lower=0), (-delta).clip(lower=0)
        rs = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
        rsi = 100 - (100 / (1 + rs))
        trend = '🔥정배열' if df['MA20'].iloc[-1] > df['MA60'].iloc[-1] else '❄️역배열'
        return trend, round(float(rsi.iloc[-1]), 1)
    except: return '오류', 0

@st.cache_data
def get_investor_flow(ticker, base_date, days=20, engine="자동"):
    end = datetime.strptime(base_date, '%Y%m%d')
    start = end - timedelta(days=days * 2)
    
    use_pykrx = "pykrx" in engine or "자동" in engine
    use_fdr = "Naver" in engine or "자동" in engine
    
    if use_pykrx:
        try:
            df = stock.get_market_trading_value_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
            if not df.empty and ('기관합계' in df.columns or '외국인합계' in df.columns):
                return df.tail(days)
        except:
            pass
        
    if use_fdr:
        try:
            url = f'https://finance.naver.com/item/frgn.naver?code={ticker}'
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, headers=headers, timeout=10)
            r.encoding = 'euc-kr'
            dfs = pd.read_html(StringIO(r.text), encoding='euc-kr')
            df3 = dfs[3]
            df3.columns = ['_'.join(str(c) for c in col).strip() if isinstance(col, tuple) else col for col in df3.columns]
            dfclean = df3.dropna(subset=['날짜_날짜', '기관_순매매량', '외국인_순매매량']).copy()
            dfclean['날짜'] = pd.to_datetime(dfclean['날짜_날짜'], format='%Y.%m.%d', errors='coerce')
            dfclean['종가_종가'] = pd.to_numeric(dfclean['종가_종가'], errors='coerce')
            dfclean['기관_순매매량'] = pd.to_numeric(dfclean['기관_순매매량'], errors='coerce')
            dfclean['외국인_순매매량'] = pd.to_numeric(dfclean['외국인_순매매량'], errors='coerce')
            dfclean = dfclean.dropna(subset=['날짜'])
            dfclean['기관합계'] = dfclean['기관_순매매량'] * dfclean['종가_종가']
            dfclean['외국인합계'] = dfclean['외국인_순매매량'] * dfclean['종가_종가']
            dfclean = dfclean.set_index('날짜').sort_index()
            return dfclean.tail(days)
        except Exception as e:
            st.warning(f"Naver 수급 파싱 에러: {e}")
            return pd.DataFrame()
            
    return pd.DataFrame()

def compute_recommendation_score(row):
    score = 0.0
    score += min(row.get('수급점수', 0) / 10.0, 1.0) * 40
    score += row.get('거래대금_rank', 0) * 20
    rsi = row.get('RSI', 50)
    if 40 <= rsi <= 60: rsi_score = 1.0
    elif 30 <= rsi < 40 or 60 < rsi <= 70: rsi_score = 0.6
    elif rsi < 30: rsi_score = 0.4
    else: rsi_score = 0.1
    score += rsi_score * 25
    score += (1.0 if '정배열' in str(row.get('추세', '')) else 0.0) * 15
    return round(score, 1)

@st.cache_data
def load_ohlcv(ticker, base_date, days=300, engine="자동"):
    end = datetime.strptime(base_date, '%Y%m%d')
    start = end - timedelta(days=days)
    
    df = None
    use_pykrx = "pykrx" in engine or "자동" in engine
    use_fdr = "Naver" in engine or "자동" in engine
    
    if use_pykrx:
        try:
            df = stock.get_market_ohlcv_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
        except:
            pass
            
    if (df is None or df.empty) and use_fdr:
        try:
            df = fdr.DataReader(ticker, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if not df.empty:
                df = df.rename(columns={'Open': '시가', 'High': '고가', 'Low': '저가', 'Close': '종가', 'Volume': '거래량'})
        except:
            pass
            
    return df if df is not None else pd.DataFrame()

def show_advanced_candle(ticker, ticker_name, base_date, engine="자동"):
    try:
        df = load_ohlcv(ticker, base_date, 300, engine)
        if df.empty:
            st.warning("OHLCV 데이터가 없습니다.")
            return
        close = df['종가']
        df['MA5']   = close.rolling(5).mean()
        df['MA20']  = close.rolling(20).mean()
        df['MA60']  = close.rolling(60).mean()
        df['MA120'] = close.rolling(120).mean()

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], name='캔들',
            increasing_line_color='#FF4B4B', decreasing_line_color='#0068FF',
        ))
        ma_colors = {'MA5': '#FFC107', 'MA20': '#FF6B00', 'MA60': '#0099FF', 'MA120': '#9C27B0'}
        ma_names  = {'MA5': '5일선', 'MA20': '20일선', 'MA60': '60일선', 'MA120': '120일선'}
        for col, color in ma_colors.items():
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], mode='lines', line=dict(color=color, width=1.5), name=ma_names[col]
            ))
        fig.update_layout(
            title=f"📈 {ticker_name} ({ticker}) — {base_date[:4]}.{base_date[4:6]}.{base_date[6:]}",
            height=500, xaxis_rangeslider_visible=False,
            xaxis=dict(type='category', rangeslider=dict(visible=False)),
            yaxis=dict(fixedrange=False), dragmode='zoom', margin=dict(l=10, r=10, t=50, b=10),
            legend=dict(orientation='h', y=1.02, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("💰 투자자별 순매수 동향 (최근 20거래일)")
        inv_df = get_investor_flow(ticker, base_date, 20, engine)
        if inv_df.empty: st.info("수급 데이터를 가져올 수 없습니다.")
        else:
            investor_cols = [c for c in ['기관합계', '외국인합계', '금융투자', '개인'] if c in inv_df.columns]
            tab_labels = {'기관합계': '🏢 기관', '외국인합계': '🌎 외국인', '금융투자': '💼 금융투자', '개인': '👤 개인'}
            tabs = st.tabs([tab_labels.get(c, c) for c in investor_cols])
            for tab, col in zip(tabs, investor_cols):
                with tab:
                    series = inv_df[col] / 1e8
                    colors = ['#FF4B4B' if v > 0 else '#0068FF' for v in series]
                    bar_fig = go.Figure(go.Bar(
                        x=inv_df.index.strftime('%m/%d'), y=series, marker_color=colors, name=col
                    ))
                    bar_fig.update_layout(yaxis_title='순매수 (억원)', height=300, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(bar_fig, use_container_width=True)
    except Exception as e:
        st.error(f"차트 로딩 실패: {e}")


# =====================================================================
# [PART 3] 렌더링 함수 (UI)
# =====================================================================

def render_market_timing():
    st.markdown('<div class="sub-title">거시경제(환율/금리) · KOSPI 기술적 분석 · 수급 동향을 융합한 시장 진입 최적화 솔루션</div>', unsafe_allow_html=True)
    with st.spinner("시장 데이터 실시간 분석 중..."):
        score, details = calc_market_timing()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if score >= 70: color_class, status_text = "text-bull", "매수 적극 권장 (강세장)"
        elif score >= 40: color_class, status_text = "text-neutral", "부분 매수 / 관망 (중립)"
        else: color_class, status_text = "text-bear", "매수 보류 / 현금 확보 (약세장)"
        st.markdown(f"""
        <div class="card" style="text-align:center; padding:2rem;">
            <div class="card-title" style="justify-content:center;">현재 시장 진입(매수) 점수</div>
            <div class="score-huge {color_class}">{score}</div>
            <div class="score-label {color_class}">{status_text}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 📊 부문별 시장 동향 분석")
    c1, c2, c3 = st.columns(3)
    macro = details["macro"]
    macro_color = "text-bull" if macro["score"] >= 20 else "text-neutral" if macro["score"] >= 10 else "text-bear"
    with c1:
        st.markdown(f"""
        <div class="card">
            <div class="card-title">🌐 거시경제 지표 ({macro['score']}/30점)</div>
            <div class="card-value {macro_color}">{macro['usd']:.1f} 원</div>
            <div class="card-desc">
                • <b>달러/원 환율</b>: {macro['usd']:.1f}원<br>
                • <b>미국채 10년물</b>: {macro['ust']:.2f}%<br>
            </div>
        </div>
        """, unsafe_allow_html=True)

    tech = details["tech"]
    tech_color = "text-bull" if tech["score"] >= 20 else "text-neutral" if tech["score"] >= 10 else "text-bear"
    with c2:
        st.markdown(f"""
        <div class="card">
            <div class="card-title">📈 시장기술적 추세 ({tech['score']}/30점)</div>
            <div class="card-value {tech_color}">{int(tech['kospi'])} pt</div>
            <div class="card-desc">
                • <b>KOSPI 추세</b>: {tech['status']}<br>
            </div>
        </div>
        """, unsafe_allow_html=True)

    flow = details["flow"]
    flow_color = "text-bull" if flow["score"] >= 30 else "text-neutral" if flow["score"] >= 15 else "text-bear"
    vol_ratio_txt = f"{flow.get('vol_ratio', 0):.2f}배" if "vol_ratio" in flow else "-"
    with c3:
        st.markdown(f"""
        <div class="card">
            <div class="card-title">💰 수급 동향 ({flow['score']}/40점)</div>
            <div class="card-value {flow_color}">{flow['status']}</div>
            <div class="card-desc">
                • <b>최근 거래량 비율</b>: {vol_ratio_txt}<br>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    kdf = get_kospi_series()
    if not kdf.empty:
        st.markdown("### 📉 KOSPI 지수 추이")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=kdf.index, y=kdf["Close"], mode="lines", name="KOSPI", line=dict(color="#38bdf8", width=2)))
        if "MA20" in kdf.columns:
            fig.add_trace(go.Scatter(x=kdf.index, y=kdf["MA20"], mode="lines", name="20일선", line=dict(color="#f59e0b", width=1.2, dash="dot")))
        if "MA60" in kdf.columns:
            fig.add_trace(go.Scatter(x=kdf.index, y=kdf["MA60"], mode="lines", name="60일선", line=dict(color="#818cf8", width=1.2, dash="dot")))
        fig.update_layout(height=320, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"),
                          margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.05))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 🏆 오늘 시장의 핵심 픽 (Top 5 유망 종목)")
    with st.spinner("최근 수급이 몰리는 우량 종목 추출 중..."):
        top_df = get_top_stock_picks()
    if top_df.empty: st.info("조건에 부합하는 종목을 찾지 못했습니다.")
    else:
        st.dataframe(top_df, use_container_width=True, hide_index=True,
                     column_config={"현재가": st.column_config.NumberColumn("현재가 (원)", format="%d"),
                                    "거래대금(억)": st.column_config.NumberColumn("거래대금 (억원)", format="%d"),
                                    "거래량비율": st.column_config.NumberColumn("거래량 비율 (최근/이전)", format="%.2f")})

def render_stock_scanner():
    st.markdown('<div class="sub-title">FinanceDataReader × pykrx 하이브리드 엔진 | 거래량·모멘텀 기반 Smart Money 포착</div>', unsafe_allow_html=True)
    
    with st.expander("ℹ️ 사용 안내 (클릭하여 펼치기)"):
        st.markdown("""
        - **수급점수**: 거래량 회전율 × 등락률 절대값. 단기 자금 유입 강도를 나타냅니다.
        - **추천점수**: 수급(40%) + 거래대금(20%) + RSI 타점(25%) + 이평선 추세(15%) 종합 평가
        - **RSI 해석**: 30 이하 = 과매도(저점 반등 기대), 70 이상 = 과매수(추격 주의)
        """)

    col1, col2 = st.columns(2)
    with col1: min_cap   = st.number_input('최소 시가총액 (억 단위)', value=500, step=100, min_value=1)
    with col2: min_trade = st.number_input('최소 거래대금 (억 단위)', value=10, step=10, min_value=1)

    if 'scan_result' not in st.session_state:
        st.session_state.scan_result = None
        st.session_state.scan_base_date = ''

    if st.button('🎯 유망 종목 포착하기', type="primary"):
        with st.spinner('FDR 하이브리드 엔진 가동 중...'):
            result, base_date = scan_hybrid_flow(min_mktcap=min_cap, min_trading=min_trade)
            st.session_state.scan_result = result
            st.session_state.scan_base_date = base_date

    if st.session_state.scan_result is not None:
        result, base_date = st.session_state.scan_result, st.session_state.scan_base_date
        if result.empty: st.warning("조건을 만족하는 종목이 없습니다.")
        else:
            if base_date != datetime.now().strftime('%Y%m%d'): st.info(f"💡 장 시작 전 또는 공휴일 — **{base_date}** 기준")
            else: st.success(f"✅ {base_date} 실시간 데이터 스캔 완료!")

            top_stocks = result.head(30).copy().reset_index(drop=True)
            trends, rsis = [], []
            current_engine = st.session_state.get('data_engine', '자동 (pykrx 우선)')
            with st.spinner("기술적 지표 계산 중..."):
                for t in top_stocks['티커']:
                    tr, rs = analyze_technical(t, base_date, current_engine)
                    trends.append(tr)
                    rsis.append(rs)
            top_stocks['추세'], top_stocks['RSI'] = trends, rsis
            top_stocks['거래대금_rank'] = top_stocks['거래대금(억)'].rank(pct=True)
            top_stocks['추천점수'] = top_stocks.apply(compute_recommendation_score, axis=1)
            top_stocks.sort_values('추천점수', ascending=False, inplace=True)
            top_stocks.reset_index(drop=True, inplace=True)
            top_stocks.index += 1

            def rank_label(i): return {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, f'{i}위')
            top_stocks.insert(0, '순위', [rank_label(i) for i in top_stocks.index])
            
            st.subheader("📋 종합 추천 순위")
            display_cols = ['순위', '종목명', '현재가', '등락률(%)', '시가총액(억)', '거래대금(억)', '수급점수', '추세', 'RSI', '추천점수']
            st.dataframe(top_stocks[display_cols].set_index('순위'), use_container_width=True, height=400)

            st.markdown("---")
            st.subheader("📊 종목 정밀 차트")
            selected_name = st.selectbox('차트를 확인할 종목 선택', top_stocks['종목명'].tolist(), key='chart_select')
            selected_row = top_stocks[top_stocks['종목명'] == selected_name].iloc[0]
            current_engine = st.session_state.get('data_engine', '자동 (pykrx 우선)')
            show_advanced_candle(selected_row['티커'], selected_name, base_date, current_engine)


# =====================================================================
# [PART 4] 메인 진입점
# =====================================================================

@st.cache_data(ttl=3600)
def check_engine_status():
    status = {"pykrx": False, "naver": False, "pykrx_error": "", "naver_error": ""}
    try:
        from pykrx import stock
        stock.get_market_ohlcv_by_date((datetime.now() - timedelta(days=5)).strftime('%Y%m%d'), datetime.now().strftime('%Y%m%d'), "005930")
        status["pykrx"] = True
    except Exception as e:
        status["pykrx_error"] = str(e) or repr(e)
        
    try:
        fdr.DataReader("005930", (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'))
        status["naver"] = True
    except Exception as e:
        status["naver_error"] = repr(e)
    return status

def main():
    st.markdown('<div class="main-title">AI 통합 주식 분석 대시보드</div>', unsafe_allow_html=True)
    
    # 사이드바에서 데이터 소스 선택 및 상태 표시
    st.sidebar.markdown("### ⚙️ 데이터 소스 설정")
    engine_status = check_engine_status()
    
    pykrx_display = '🟢 정상 작동 중' if engine_status['pykrx'] else '🔴 연결 오류'
    naver_display = '🟢 정상 작동 중' if engine_status['naver'] else '🔴 연결 오류'
    
    st.sidebar.markdown(f"""
    **현재 엔진 상태:**
    - 한국거래소(pykrx): {pykrx_display}
    - Naver & FDR: {naver_display}
    """, unsafe_allow_html=True)
    
    selected_engine = st.sidebar.radio(
        "데이터 수집 엔진 선택", 
        ["자동 (pykrx 우선)", "한국거래소 (pykrx) 강제", "Naver & FDR 강제"]
    )
    st.session_state['data_engine'] = selected_engine
    
    # 메인 화면 안내문 업데이트
    if selected_engine == "한국거래소 (pykrx) 강제":
        st.markdown('<p style="text-align:center; color:#10b981; font-size:0.9rem;">🟢 <b>현재 모드:</b> 한국거래소 (pykrx) 강제 수집</p>', unsafe_allow_html=True)
    elif selected_engine == "Naver & FDR 강제":
        st.markdown('<p style="text-align:center; color:#f59e0b; font-size:0.9rem;">🟡 <b>현재 모드:</b> Naver & FDR 우회 수집 강제</p>', unsafe_allow_html=True)
    else:
        if engine_status['pykrx']:
            st.markdown('<p style="text-align:center; color:#10b981; font-size:0.9rem;">🟢 <b>현재 모드:</b> 자동 (한국거래소 pykrx 우선 사용)</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="text-align:center; color:#f59e0b; font-size:0.9rem;">🟡 <b>현재 모드:</b> 자동 (Naver & FDR 세컨 플랜 작동 중)</p>', unsafe_allow_html=True)
        
    # 탭 구성
    tab1, tab2 = st.tabs(["🧭 마켓 타이밍 & 요약 픽", "🚀 스마트 수급 스캐너 (상세 검색)"])
    
    with tab1:
        render_market_timing()
        
    with tab2:
        render_stock_scanner()

if __name__ == "__main__":
    main()
