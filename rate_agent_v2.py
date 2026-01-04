import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="Agent 4: 利率狙擊手 (Final)", layout="wide", page_icon="🦅")

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
    h1, h2, h3 { font-family: 'Roboto', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.title("🦅 利率狙擊手設定")
    DEFAULT_API_KEY = '3e2d2e27e5126fac34a02e9edaa80c2e' 
    api_key = st.text_input("輸入 FRED API Key", value=DEFAULT_API_KEY, type="password")
    
    st.info("💡 提示：若無 Key，請至 stlouisfed.org 申請免費 API Key。")
    
    # 歷史數據長度
    years_back = st.slider("歷史數據長度 (年)", 3, 20, 5)
    
    st.divider()
    st.caption("版本: v3.6 Unit Correction")
    
    if not api_key:
        st.warning("⚠️ 請輸入 API Key 以啟動系統")
        st.stop()

fred = Fred(api_key=api_key)

# ==========================================
# 2. 數據引擎 (Data Engine)
# ==========================================
@st.cache_data(ttl=3600)
def get_rates_data(years):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*years)
    
    tickers = {
        # --- 利率與債券 ---
        'DGS10': 'US 10Y Yield',           
        'DGS2': 'US 2Y Yield',             
        'FEDFUNDS': 'Fed Funds Rate',      
        'DFII10': '10Y Real Yield',        
        'T10Y3M': '10Y-3M Spread',         
        
        # --- 流動性相關 ---
        # WALCL: Millions of Dollars (百萬)
        'WALCL': 'Fed Total Assets',  
        # WTREGEN: Millions of Dollars (百萬) <-- 關鍵修正點
        'WTREGEN': 'TGA Account',     
        # RRPONTSYD: Billions of Dollars (十億)
        'RRPONTSYD': 'Reverse Repo',  
        
        # --- 市場與信用 ---
        'BAMLH0A0HYM2': 'High Yield Spread', 
        'NFCI': 'Financial Conditions',      
        'SP500': 'S&P 500', 
    }
    
    data_frames = []
    for code, name in tickers.items():
        try:
            series = fred.get_series(code, observation_start=start_date)
            series.name = name
            data_frames.append(series)
        except Exception as e:
            print(f"Warning: Failed to fetch {name} ({code})")

    if not data_frames:
        return pd.DataFrame()

    # 暴力合併與填充
    df = pd.concat(data_frames, axis=1)
    df = df.ffill()
    df = df.dropna(subset=['US 10Y Yield'])
    
    return df

def process_rates_data(df):
    # 1. 計算淨流動性 (Net Liquidity)
    req_cols = ['Fed Total Assets', 'TGA Account', 'Reverse Repo']
    
    if all(col in df.columns for col in req_cols):
        # --- 單位統一換算成 "Trillions (兆美元)" ---
        
        # WALCL (Fed Assets) 是 Millions -> 除以 1,000,000
        fed = df['Fed Total Assets'] / 1000000
        
        # TGA Account (WTREGEN) 是 Millions -> 除以 1,000,000 (修正點)
        tga = df['TGA Account'] / 1000000
        
        # RRP (RRPONTSYD) 是 Billions -> 除以 1,000
        rrp = df['Reverse Repo'] / 1000
        
        # 計算公式：Fed資產 - TGA - RRP
        df['Net Liquidity'] = fed - tga - rrp
    else:
        df['Net Liquidity'] = np.nan

    # 2. 殖利率曲線
    if 'US 10Y Yield' in df.columns and 'US 2Y Yield' in df.columns:
        df['Curve 10Y-2Y'] = df['US 10Y Yield'] - df['US 2Y Yield']
        
    return df

# ==========================================
# 3. 視覺化模組
# ==========================================
def plot_dual_axis(df, col1, col2, title, name1, name2):
    plot_df = df[[col1, col2]].dropna()
    
    if plot_df.empty:
        st.warning(f"無足夠數據繪製 {title}")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col1], name=name1, line=dict(color='#1f77b4', width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col2], name=name2, line=dict(color='#ff7f0e', width=2)), secondary_y=True)
    
    fig.update_layout(title=title, height=450, hovermode="x unified", legend=dict(orientation="h", y=1.1))
    fig.update_yaxes(title_text=name1, secondary_y=False)
    fig.update_yaxes(title_text=name2, secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

def plot_area_chart(df, col, title, threshold=0):
    if col not in df.columns: return
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
# 4. 主程式邏輯
# ==========================================
st.title("🦅 Agent 4: 利率狙擊手 (The Yield Sniper)")
st.markdown("### 資金成本、流動性水位與資產定價中樞")

try:
    with st.spinner("正在強制同步聯準會數據並運算流動性模型..."):
        raw_df = get_rates_data(years_back)
        df = process_rates_data(raw_df)
    
    if df.empty:
        st.error("無法取得數據，請檢查 API Key 或網絡連線。")
        st.stop()

    latest = df.iloc[-1]
    prev = df.iloc[-7] 

    # --- 數據診斷與單位驗證 ---
    # 這次算出來應該要是正值，如果是負值，顯示警告
    if latest.get('Net Liquidity', 0) < 0:
        st.error(f"⚠️ 流動性數據異常 (負值: {latest.get('Net Liquidity'):.2f}T)。請檢查下方原始數據單位。")
        st.write("原始數據診斷 (請確認 Fed 與 TGA 是否為 Millions, RRP 為 Billions):")
        st.dataframe(latest[['Fed Total Assets', 'TGA Account', 'Reverse Repo']].to_frame().T)
    
    # --- 第一區：Gravity Board (戰情看板) ---
    col1, col2, col3, col4, col5 = st.columns(5)
    
    if 'US 10Y Yield' in latest:
        d_10y = latest['US 10Y Yield'] - prev['US 10Y Yield']
        col1.metric("US 10Y (名目)", f"{latest['US 10Y Yield']:.2f}%", f"{d_10y:.2f}%", delta_color="inverse")
    
    if '10Y Real Yield' in latest:
        d_real = latest['10Y Real Yield'] - prev['10Y Real Yield']
        col2.metric("Real Yield (實質)", f"{latest['10Y Real Yield']:.2f}%", f"{d_real:.2f}%", delta_color="inverse")
    
    if 'Net Liquidity' in latest:
        liq_curr = latest['Net Liquidity']
        liq_diff = liq_curr - prev['Net Liquidity']
        col3.metric("淨流動性 (兆鎂)", f"${liq_curr:.2f}T", f"{liq_diff:.2f}T")
    
    if 'Financial Conditions' in latest:
        fci_curr = latest['Financial Conditions']
        col4.metric("金融狀況 (NFCI)", f"{fci_curr:.2f}", f"{fci_curr - prev['Financial Conditions']:.2f}", delta_color="inverse")
    
    if 'Curve 10Y-2Y' in latest:
        col5.metric("殖利率曲線 (10-2)", f"{latest['Curve 10Y-2Y']:.2f}%")

    st.divider()

    # --- 第二區：五大深度分析 Tab ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🌊 流動性引擎", 
        "🏛️ Fed 博弈", 
        "📉 殖利率曲線", 
        "💣 信用壓力", 
        "🧮 估值定價"
    ])

    with tab1:
        st.subheader("為什麼利率升、股市還漲？看這張圖。")
        st.caption("藍線：市場真正能用的錢 (淨流動性) | 橘線：S&P 500")
        
        if 'Net Liquidity' in df.columns and 'S&P 500' in df.columns:
            plot_dual_axis(df, 'Net Liquidity', 'S&P 500', "淨流動性 vs S&P 500", "Net Liquidity ($Trillions)", "S&P 500 Index")
        
        col_liq1, col_liq2 = st.columns(2)
        with col_liq1:
            st.markdown("#### 💧 TGA (財政部口袋 - 越低越好)")
            if 'TGA Account' in df.columns: st.line_chart(df['TGA Account'])
        with col_liq2:
            st.markdown("#### 🛁 RRP (逆回購 - 蓄水池)")
            if 'Reverse Repo' in df.columns: st.line_chart(df['Reverse Repo'])
            
        show_edu_card(
            title="淨流動性 (Net Liquidity)",
            definition="公式 = Fed總資產 - TGA - RRP。這是市場真正的「現金水位」。",
            example="如果 Fed 縮表 (資產下降)，但 RRP 裡的錢流出來買國債，這會抵銷縮表的利空，支撐股市。",
            signal="**RRP 歸零是最大的風險。** 若 RRP 耗盡且 Fed 繼續縮表，流動性將枯竭。",
            strategy="只要藍線 (流動性) 趨勢向上，即便升息也不要輕易做空。"
        )

    with tab2:
        st.subheader("市場 vs Fed：誰在說謊？")
        if 'US 2Y Yield' in df.columns and 'Fed Funds Rate' in df.columns:
            plot_dual_axis(df, 'US 2Y Yield', 'Fed Funds Rate', "市場預期 (2Y) vs 官方利率 (Fed Funds)", "US 2Y Yield (%)", "Fed Funds Rate (%)")
        
        show_edu_card(
            title="2年期公債 (US02Y)",
            definition="對聯準會政策最敏感的利率，視為「市場對未來利率的平均預期」。",
            example="若 2Y 殖利率崩跌到 Fed 利率下方，代表市場在賭「經濟快不行了，你馬上就得降息」。",
            signal="**2Y < Fed Rate (深度背離)**：市場押注衰退/降息。",
            strategy="當綠線 (2Y) 急速下穿橘線 (Fed) 時，通常是買入長天期債券的最佳時機。"
        )

    with tab3:
        st.subheader("經濟衰退預警器")
        if '10Y-3M Spread' in df.columns:
            plot_area_chart(df, '10Y-3M Spread', "10Y - 3M 利差 (NY Fed 權威指標)", threshold=0)
        
        show_edu_card(
            title="10Y-3M 利差",
            definition="紐約聯儲預測衰退最準確的指標。短利 > 長利 = 倒掛。",
            example="過去 50 年的每一次衰退前，這條線都會變成負的。",
            signal="**最危險的時刻是「解除倒掛」的瞬間 (V型反轉)**。通常代表衰退已經開始。",
            strategy="倒掛期間 (負值區)：持有現金/短債。解除倒掛瞬間：全速轉進長債，避開股票。"
        )

    with tab4:
        st.subheader("企業會倒閉嗎？")
        if 'High Yield Spread' in df.columns and 'Financial Conditions' in df.columns:
            plot_dual_axis(df, 'High Yield Spread', 'Financial Conditions', "垃圾債利差 vs 金融狀況指數", "HY Spread (%)", "NFCI Index")
        
        show_edu_card(
            title="高收益債利差 (HY Spread)",
            definition="垃圾債利率 - 公債利率。代表借錢給爛公司的額外風險貼水。",
            example="如果利差飆升，代表市場擔心違約潮，股市會大跌。",
            signal="**利差 < 4.0%**：Risk-On (追價)。**利差 > 6.0%**：違約風險急升。",
            strategy="只要這條線平穩，就算利率高，股市也不會大跌。"
        )

    with tab5:
        st.subheader("現在買股票貴不貴？")
        
        col_input, col_result = st.columns([1, 2])
        
        with col_input:
            if 'US 10Y Yield' in latest:
                current_yield = latest['US 10Y Yield']
                st.markdown(f"**當前無風險利率 (10Y):** `{current_yield:.2f}%`")
                pe_ratio = st.slider("設定 S&P 500 當前本益比 (P/E)", 15.0, 40.0, 24.0, 0.5)
                earnings_yield = (1 / pe_ratio) * 100
                erp = earnings_yield - current_yield
                st.markdown("---")
                st.metric("盈餘殖利率 (1/PE)", f"{earnings_yield:.2f}%")
            else:
                erp = 0
            
        with col_result:
            st.markdown(f"### 📊 股權風險溢酬 (ERP): `{erp:.2f}%`")
            if erp < 1.0:
                st.error("🔴 極度昂貴：買股票不如買債券。風險回報極差。")
            elif erp < 3.0:
                st.warning("🟡 偏貴/中性：合理區間，需精選個股。")
            else:
                st.success("🟢 便宜：股票極具吸引力。")
                
            fig_erp = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = erp,
                title = {'text': "Equity Risk Premium (ERP)"},
                gauge = {
                    'axis': {'range': [-2, 6]},
                    'bar': {'color': "black"},
                    'steps': [
                        {'range': [-2, 1], 'color': "#ff4b4b"},
                        {'range': [1, 3], 'color': "#f7c948"},
                        {'range': [3, 6], 'color': "#3acf65"}
                    ],
                    'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 0.5}
                }
            ))
            fig_erp.update_layout(height=250, margin=dict(t=30, b=10))
            st.plotly_chart(fig_erp, use_container_width=True)
            
        show_edu_card(
            title="股權風險溢酬 (ERP)",
            definition="買股票比買公債「多賺」的預期報酬率。公式 = (1/PE) - 10Y利率。",
            example="如果股票預期賺 5%，公債也給 5%，那誰要冒險買股票？ERP 就是 0%，股市必跌。",
            signal="**歷史警戒線：< 0.5%**。",
            strategy="當 ERP 過低，應減碼指數型 ETF，保留現金或尋找 Alpha。"
        )

except Exception as e:
    st.error(f"系統嚴重錯誤: {e}")
    st.warning("請檢查 API Key 或網路連線。")