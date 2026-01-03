# cpi_agent.py

import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. 設定與初始化
# ==========================================
st.set_page_config(page_title="Macro CPI Agent", layout="wide")

# ⚠️ 請在這裡填入你的 FRED API Key，或者在側邊欄輸入
DEFAULT_API_KEY = '3e2d2e27e5126fac34a02e9edaa80c2e' 

with st.sidebar:
    st.title("⚙️ 設定")
    api_key = st.text_input("輸入 FRED API Key", value=DEFAULT_API_KEY, type="password")
    if not api_key:
        st.warning("請先輸入 API Key 才能運作")
        st.stop()

fred = Fred(api_key=api_key)

# ==========================================
# 2. 數據引擎 (Data Engine)
# ==========================================
@st.cache_data(ttl=3600) # 快取 1 小時，避免重複呼叫 API
def get_macro_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*5) # 抓過去 5 年
    
    # 定義我們要抓的指標
    tickers = {
        'CPIAUCSL': 'CPI (Headline)',      # 整體 CPI
        'CPILFESL': 'CPI (Core)',          # 核心 CPI
        'PPIFIS': 'PPI (Final Demand)',    # PPI
        'PCEPI': 'PCE (Headline)',         # PCE
        'STICKCPIM159SFRBATL': 'Sticky CPI', # 黏性 CPI (亞特蘭大聯儲)
    }
    
    df = pd.DataFrame()
    for code, name in tickers.items():
        try:
            series = fred.get_series(code, observation_start=start_date)
            df[name] = series
        except Exception as e:
            st.error(f"無法抓取 {name}: {e}")
    
    return df

# 數據處理函數
def process_data(df):
    # 計算年增率 (YoY)
    df_yoy = df.pct_change(12) * 100
    # 計算月增率 (MoM)
    df_mom = df.pct_change(1) * 100

    # 2. 【修正點】針對 "本身已經是百分比" 的數據，還原回原始數值
    # Sticky CPI (STICKCPIM157SFRBATL) 下載下來就是年增率，不用再算
    if 'Sticky CPI' in df.columns:
        df_yoy['Sticky CPI'] = df['Sticky CPI']
        # Sticky CPI 通常沒有提供月增率數據，或者格式不同，建議在 MoM 表中設為 NaN 或忽略
        df_mom['Sticky CPI'] = np.nan 

    # 如果未來你有加入 "10年期公債殖利率" (DGS10)，它也是百分比，也要這樣處理
    if 'US_10Y_Yield' in df.columns:
        df_yoy['US_10Y_Yield'] = df['US_10Y_Yield']

    return df, df_yoy, df_mom


# ==========================================
# 3. 邏輯運算層 (Analysis Layer)
# ==========================================
def calculate_spread(df_yoy):
    # 計算剪刀差：CPI (售價) - PPI (成本)
    spread = df_yoy['CPI (Headline)'] - df_yoy['PPI (Final Demand)']
    return spread

# ==========================================
# 4. 介面呈現層 (UI Layer)
# ==========================================

st.title("🕵️‍♂️ Macro CPI Agent 戰情室")
st.markdown("---")

# 載入數據
try:
    raw_df = get_macro_data()
    raw_df = raw_df.dropna() # 移除空值
    _, df_yoy, df_mom = process_data(raw_df)
    spread = calculate_spread(df_yoy)
    
    # 取得最新一筆數據的日期與數值
    latest_date = df_yoy.index[-1].strftime('%Y-%m-%d')
    st.info(f"數據更新日期: {latest_date}")

    # --- 頂部關鍵指標 (KPI Cards) ---
    col1, col2, col3, col4 = st.columns(4)
    
    latest_cpi = df_yoy['CPI (Headline)'].iloc[-1]
    latest_core = df_yoy['CPI (Core)'].iloc[-1]
    latest_ppi = df_yoy['PPI (Final Demand)'].iloc[-1]
    latest_spread = spread.iloc[-1]

    col1.metric("整體 CPI (YoY)", f"{latest_cpi:.2f}%", delta=f"{latest_cpi - df_yoy['CPI (Headline)'].iloc[-2]:.2f}%")
    col2.metric("核心 CPI (YoY)", f"{latest_core:.2f}%", delta=f"{latest_core - df_yoy['CPI (Core)'].iloc[-2]:.2f}%")
    col3.metric("PPI (YoY)", f"{latest_ppi:.2f}%", delta=f"{latest_ppi - df_yoy['PPI (Final Demand)'].iloc[-2]:.2f}%")
    col4.metric("企業利潤剪刀差", f"{latest_spread:.2f}%", 
                delta_color="normal" if latest_spread > 0 else "inverse",
                help="正值代表 CPI > PPI (利潤擴大)，負值代表成本壓力大")

    # --- 主要圖表區 (Tabs) ---
    tab1, tab2, tab3 = st.tabs(["📊 通膨趨勢", "✂️ 剪刀差分析", "🔮 基期模擬器"])

    with tab1:
        st.subheader("CPI, PPI, PCE 歷史走勢")
        st.line_chart(df_yoy[['CPI (Headline)', 'CPI (Core)', 'PPI (Final Demand)', 'PCE (Headline)']])
        
        st.subheader("黏性 CPI (Sticky) vs 核心 CPI")
        st.write("如果 Sticky CPI (紅線) 持續高於 Core CPI，代表通膨很難降下來。")
        st.line_chart(df_yoy[['CPI (Core)', 'Sticky CPI']])

    with tab2:
        st.subheader("企業利潤壓力指標 (CPI - PPI)")
        st.write("此指標 > 0 表示企業轉嫁成本順利； < 0 表示企業吸收成本，獲利受損。")
        
        # 用 Plotly 畫比較漂亮的面積圖
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=spread.index, y=spread, fill='tozeroy', name='Spread'))
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("未來通膨路徑模擬 (Base Effect Simulator)")
        st.markdown("如果**未來每個月的月增率 (MoM)** 都維持在某個水準，年增率 (YoY) 會怎麼走？")
        
        # 1. 使用者輸入假設
        assumed_mom = st.slider("假設未來每月月增率 (MoM %)", 0.0, 1.0, 0.2, 0.1) / 100
        months_to_predict = 6
        
        # 2. 進行模擬運算
        last_cpi_index = raw_df['CPI (Headline)'].iloc[-1]
        
        # 抓出去年的基期 (Base)
        # 注意：這裡簡化處理，直接抓去年的指數。實務上要精確對齊日期。
        # 簡單作法：取最後 12 個月前的數據往後推
        base_indices = raw_df['CPI (Headline)'].iloc[-13:-13+months_to_predict].values
        
        future_dates = [raw_df.index[-1] + pd.DateOffset(months=i+1) for i in range(months_to_predict)]
        simulated_yoy = []
        
        current_sim_index = last_cpi_index
        for i in range(months_to_predict):
            current_sim_index = current_sim_index * (1 + assumed_mom)
            if i < len(base_indices):
                base = base_indices[i]
                yoy = (current_sim_index / base - 1) * 100
                simulated_yoy.append(yoy)
            else:
                simulated_yoy.append(np.nan)
                
        # 3. 畫圖
        sim_df = pd.DataFrame({'Simulated CPI YoY': simulated_yoy}, index=future_dates)
        
        # 結合歷史數據一起畫
        combined_chart_data = pd.concat([df_yoy[['CPI (Headline)']].tail(12), sim_df])
        st.line_chart(combined_chart_data)
        
        st.write(f"模擬結果：如果每月 MoM 維持 {assumed_mom*100:.1f}%，6個月後 CPI YoY 將來到 **{simulated_yoy[-1]:.2f}%**")

except Exception as e:
    st.error(f"發生錯誤，請檢查 API Key 或網路連線: {e}")