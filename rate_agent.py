import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. 系統設定與 API 初始化
# ==========================================
st.set_page_config(page_title="Macro Rates Agent v3.3", layout="wide", page_icon="🏦")

# 自定義 CSS
st.markdown("""
    <style>
    .metric-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #2E86C1;}
    .info-box {
        background-color: #e8f4f8; 
        padding: 15px; 
        border-radius: 8px; 
        margin-bottom: 10px;
        border: 1px solid #d1e7dd;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #ffecb5;
    }
    .info-box p, .warning-box p { margin: 5px 0; }
    h1, h2, h3 { font-family: 'Roboto', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.title("🏦 利率狙擊手設定")
    DEFAULT_API_KEY = '3e2d2e27e5126fac34a02e9edaa80c2e' 
    api_key = st.text_input("輸入 FRED API Key", value=DEFAULT_API_KEY, type="password")
    
    st.info("💡 提示：若無 Key，請至 stlouisfed.org 申請免費 API Key。")
    
    # 增加歷史數據長度選項，預設 5 年，可拉長看流動性週期
    years_back = st.slider("歷史數據長度 (年)", 3, 15, 5)
    
    st.divider()
    st.caption("版本: v3.3 Ultimate Fix")
    
    if not api_key:
        st.warning("⚠️ 請輸入 API Key 以啟動系統")
        st.stop()

fred = Fred(api_key=api_key)

# ==========================================
# 2. 數據引擎 (Data Engine) - 強制對齊版
# ==========================================
@st.cache_data(ttl=3600)
def get_rates_data(years):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*years)
    
    # 定義指標
    tickers = {
        # --- 利率與債券 ---
        'DGS10': 'US 10Y Yield',           
        'DGS2': 'US 2Y Yield',             
        'FEDFUNDS': 'Fed Funds Rate',      
        'DFII10': '10Y Real Yield',        
        'T10Y3M': '10Y-3M Spread',         # 衰退指標
        
        # --- 信用與股市 ---
        'BAMLH0A0HYM2': 'High Yield Spread', 
        'NFCI': 'Financial Conditions',      
        'SP500': 'S&P 500',                  
    }
    
    # 1. 先抓一般日更數據
    df = pd.DataFrame()
    for code, name in tickers.items():
        try:
            series = fred.get_series(code, observation_start=start_date)
            series.name = name
            df = df.join(series, how='outer')
        except Exception:
            pass # 暫時忽略錯誤，保持介面運作

    # 2. 特別處理流動性數據 (因為頻率不同，容易出錯)
    # 分開抓取以確保安全
    try:
        # WALCL (Fed Assets) 是週更 (Wednesday)
        fed_assets = fred.get_series('WALCL', observation_start=start_date)
        fed_assets.name = 'Fed Total Assets' # Millions
        
        # TGA & RRP 是日更
        tga = fred.get_series('WTREGEN', observation_start=start_date)
        tga.name = 'TGA Account' # Billions
        
        rrp = fred.get_series('RRPONTSYD', observation_start=start_date)
        rrp.name = 'Reverse Repo' # Billions
        
        # 合併流動性數據到獨立 DataFrame 進行重取樣
        liq_df = pd.DataFrame([fed_assets, tga, rrp]).T
        
        # === 關鍵修復步驟 ===
        # 強制轉為日頻率，並用上週數據填滿 (Forward Fill)
        # 這樣週三的 Fed 數據就會填滿週四、週五...直到下週
        liq_df = liq_df.resample('D').ffill()
        
        # 合併回主 DataFrame
        df = df.join(liq_df, how='outer')
        
    except Exception as e:
        st.error(f"流動性數據抓取失敗: {e}")

    return df

def process_rates_data(df):
    """數據清洗與計算"""
    # 1. 全局填補：確保週末或假日的空值被填補
    df = df.ffill()
    
    # 2. 移除太早期的全空數據
    df = df.dropna(subset=['US 10Y Yield'], how='all')

    # 3. 計算淨流動性 (Net Liquidity) - 單位防呆
    # 公式：Fed Assets (Millions) - TGA (Billions) - RRP (Billions)
    # 目標：全部轉為 Trillions (兆)
    
    if all(x in df.columns for x in ['Fed Total Assets', 'TGA Account', 'Reverse Repo']):
        # 將 Millions 轉 Trillions (/ 1,000,000)
        fed_t = df['Fed Total Assets'] / 1000000
        
        # 將 Billions 轉 Trillions (/ 1,000)
        tga_t = df['TGA Account'] / 1000
        rrp_t = df['Reverse Repo'] / 1000
        
        # 計算
        df['Net Liquidity'] = fed_t - tga_t - rrp_t
    
    # 4. 殖利率曲線
    if 'US 10Y Yield' in df.columns and 'US 2Y Yield' in df.columns:
        df['Curve 10Y-2Y'] = df['US 10Y Yield'] - df['US 2Y Yield']
        
    return df

# ==========================================
# 3. 視覺化模組
# ==========================================
def plot_dual_axis(df, col1, col2, title, name1, name2):
    # 移除空值確保連線
    plot_df = df[[col1, col2]].dropna()
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col1], name=name1, line=dict(color='#1f77b4', width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col2], name=name2, line=dict(color='#ff7f0e', width=2)), secondary_y=True)
    
    fig.update_layout(title=title, height=450, hovermode="x unified", legend=dict(orientation="h", y=1.1))
    fig.update_yaxes(title_text=name1, secondary_y=False)
    fig.update_yaxes(title_text=name2, secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

def plot_area_chart(df, col, title, threshold=0):
    plot_df = df[[col]].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col], fill='tozeroy', mode='lines', line=dict(color='black', width=1)))
    fig.add_hline(y=threshold, line_color="red", line_dash="dash")
    fig.update_layout(title=title, height=350, margin=dict(t=40, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)

def show_edu_card(title, definition, example, signal, strategy):
    with st.expander(f"📖 {title}：深度解讀 (點我展開)"):
        st.markdown(f"""
        <div class="info-box">
            <p><strong>🧐 定義：</strong>{definition}</p>
            <p><strong>🍎 機構觀點：</strong>{example}</p>
            <p><strong>⚡ 關鍵訊號：</strong>{signal}</p>
        </div>
        <div class="warning-box">
            <p><strong>♟️ 操盤策略：</strong>{strategy}</p>
        </div>
        """, unsafe_allow_html=True)

# ==========================================
# 4. 主介面邏輯
# ==========================================
st.title("🦅 Agent 4: 利率狙擊手 (v3.3 Ultimate)")
st.markdown("### 資金成本、流動性水位與資產定價中樞")

try:
    with st.spinner("正在下載數據並進行多週期對齊..."):
        raw_df = get_rates_data(years_back)
        df = process_rates_data(raw_df)
    
    if df.empty:
        st.error("無法取得數據，請檢查 API Key。")
        st.stop()

    latest = df.iloc[-1]
    prev_week = df.iloc[-7] # 一週前
    
    st.markdown(f"**數據最後更新**: {df.index[-1].strftime('%Y-%m-%d')}")
    st.divider()

    # --- 第一區：Gravity Board (地心引力看板) ---
    col1, col2, col3, col4, col5 = st.columns(5)
    
    # 1. 10Y Yield
    if 'US 10Y Yield' in latest:
        d_10y = latest['US 10Y Yield'] - prev_week['US 10Y Yield']
        col1.metric("US 10Y (名目)", f"{latest['US 10Y Yield']:.2f}%", f"{d_10y:.2f}%", delta_color="inverse")
    
    # 2. Real Yield
    if '10Y Real Yield' in latest:
        d_real = latest['10Y Real Yield'] - prev_week['10Y Real Yield']
        col2.metric("Real Yield (實質)", f"{latest['10Y Real Yield']:.2f}%", f"{d_real:.2f}%", delta_color="inverse")
    
    # 3. Net Liquidity (關鍵修復)
    if 'Net Liquidity' in latest and not pd.isna(latest['Net Liquidity']):
        liq_curr = latest['Net Liquidity']
        liq_diff = liq_curr - prev_week['Net Liquidity']
        col3.metric("淨流動性 (兆鎂)", f"${liq_curr:.2f}T", f"{liq_diff:.2f}T")
    else:
        col3.metric("淨流動性", "計算中/資料不足", help="Fed 資產數據可能尚未更新")
    
    # 4. Financial Conditions
    if 'Financial Conditions' in latest:
        fci_curr = latest['Financial Conditions']
        col4.metric("金融狀況 (NFCI)", f"{fci_curr:.2f}", f"{fci_curr - prev_week['Financial Conditions']:.2f}", delta_color="inverse")
    
    # 5. Curve
    if 'Curve 10Y-2Y' in latest:
        col5.metric("殖利率曲線 (10-2)", f"{latest['Curve 10Y-2Y']:.2f}%")

    # --- 第二區：5大深度分析 Tab (完整回歸) ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🌊 流動性引擎", 
        "🏛️ Fed 博弈", 
        "📉 殖利率曲線", 
        "💣 信用壓力", 
        "🧮 估值定價"
    ])

    # Tab 1: 流動性
    with tab1:
        st.subheader("為什麼利率升、股市還漲？")
        st.caption("藍線：淨流動性 (Trillions) | 橘線：S&P 500")
        
        if 'Net Liquidity' in df.columns and 'S&P 500' in df.columns:
            plot_dual_axis(df, 'Net Liquidity', 'S&P 500', "淨流動性 vs S&P 500", "Liquidity ($Trillions)", "S&P 500 Index")
            
        col_liq1, col_liq2 = st.columns(2)
        with col_liq1:
            st.markdown("#### 💧 TGA (政府口袋 - 越低越好)")
            if 'TGA Account' in df.columns:
                st.line_chart(df['TGA Account'])
        with col_liq2:
            st.markdown("#### 🛁 RRP (逆回購 - 蓄水池)")
            if 'Reverse Repo' in df.columns:
                st.line_chart(df['Reverse Repo'])
        
        show_edu_card(
            title="淨流動性 (Net Liquidity)",
            definition="Fed總資產 - TGA - RRP。這代表有多少錢實際在金融體系內流動。",
            example="如果圖表顯示正值且上升 (如 2023 年)，代表即便 Fed 升息，市場依然有錢炒股。",
            signal="**RRP 歸零是最大風險**。如果 RRP 耗盡，財政部發債將直接抽取市場資金，導致流動性危機。",
            strategy="跟著藍線走。如果藍線大跌，就算基本面再好也要減碼。"
        )

    # Tab 2: Fed 博弈
    with tab2:
        st.subheader("市場預期 (2Y) vs 官方利率 (Fed Funds)")
        if 'US 2Y Yield' in df.columns and 'Fed Funds Rate' in df.columns:
            plot_dual_axis(df, 'US 2Y Yield', 'Fed Funds Rate', "市場預期 vs 官方利率", "2Y Yield (%)", "Fed Funds (%)")
            
        show_edu_card(
            title="2年期公債殖利率",
            definition="市場對未來貨幣政策的投票結果。",
            example="綠線 (2Y) 如果跌破橘線 (Fed Funds)，代表市場在逼宮央行降息。",
            signal="**深度倒掛 (2Y << Fed Funds)**：強烈的衰退訊號。",
            strategy="當 2Y 急速下跌時，買入美債通常比買股票安全。"
        )

    # Tab 3: 殖利率曲線
    with tab3:
        st.subheader("衰退指標：10Y - 3M")
        if '10Y-3M Spread' in df.columns:
            plot_area_chart(df, '10Y-3M Spread', "10Y - 3M 利差 (NY Fed 權威指標)", threshold=0)
            
        show_edu_card(
            title="10Y-3M 利差",
            definition="紐約聯儲預測衰退最準確的指標。",
            example="過去 8 次衰退，它全部預測成功，無一例外。",
            signal="**負值 (倒掛)**：衰退警報。**轉正 (解除倒掛)**：通常衰退正式開始。",
            strategy="在倒掛解除的瞬間 (V型反轉)，通常伴隨著股市大跌，應轉向防禦性資產。"
        )

    # Tab 4: 信用壓力
    with tab4:
        st.subheader("高收益債利差 (High Yield Spread)")
        if 'High Yield Spread' in df.columns:
            plot_dual_axis(df, 'High Yield Spread', 'Financial Conditions', "垃圾債利差 vs 金融狀況", "Spread (%)", "NFCI Index")
            
        show_edu_card(
            title="信用利差",
            definition="企業借錢比政府借錢多付的利息。",
            example="利差飆升代表銀行不敢借錢給企業，這會導致違約潮。",
            signal="**> 5.0%**：警戒。**> 8.0%**：危機爆發。",
            strategy="只要利差維持低檔，可以繼續做多股票 (Risk-On)。"
        )

    # Tab 5: 估值定價
    with tab5:
        st.subheader("股權風險溢酬 (ERP) 模擬器")
        
        col_in, col_out = st.columns([1, 2])
        with col_in:
            if 'US 10Y Yield' in latest:
                curr_yield = latest['US 10Y Yield']
                st.markdown(f"當前 10Y 利率: **{curr_yield:.2f}%**")
                pe = st.slider("設定 S&P 500 本益比 (P/E)", 15.0, 40.0, 24.0)
                earnings_yield = (1/pe)*100
                erp = earnings_yield - curr_yield
                st.metric("預估 ERP", f"{erp:.2f}%")
            else:
                erp = 0
        
        with col_out:
            fig_erp = go.Figure(go.Indicator(
                mode = "gauge+number", value = erp,
                title = {'text': "ERP (越高越便宜)"},
                gauge = {'axis': {'range': [-2, 6]}, 
                         'bar': {'color': "black"},
                         'steps': [{'range': [-2, 1], 'color': "#ff4b4b"}, {'range': [1, 3], 'color': "#f7c948"}, {'range': [3, 6], 'color': "#3acf65"}]}
            ))
            fig_erp.update_layout(height=300)
            st.plotly_chart(fig_erp, use_container_width=True)

        show_edu_card(
            title="股權風險溢酬 (ERP)",
            definition="買股票相對於買公債的超額報酬。",
            example="現在 ERP 很低 (<1%)，代表你冒著股票腰斬的風險，卻只比買公債多賺一點點。",
            signal="**ERP < 0.5%**：極度危險 (泡沫)。",
            strategy="ERP 過低時，應降低持股比例，保留現金。"
        )

except Exception as e:
    st.error(f"系統錯誤: {e}")
    st.warning("請檢查 API Key 或網路連線。")