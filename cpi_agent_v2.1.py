import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. 系統設定與 API 初始化
# ==========================================
st.set_page_config(page_title="Macro CPI Agent Pro", layout="wide", page_icon="📈")

# 自定義 CSS 美化說明區塊
st.markdown("""
    <style>
    .metric-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b;}
    .info-box {
        background-color: #e8f4f8; 
        padding: 15px; 
        border-radius: 8px; 
        margin-bottom: 10px;
        border: 1px solid #d1e7dd;
    }
    .info-box p { margin: 5px 0; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.title("⚙️ 戰情室設定")
    # 預設 Key (若無則留空)
    DEFAULT_API_KEY = '3e2d2e27e5126fac34a02e9edaa80c2e' 
    api_key = st.text_input("輸入 FRED API Key", value=DEFAULT_API_KEY, type="password")
    
    st.info("💡 提示：若無 Key，請至 stlouisfed.org 申請免費 API Key。")
    
    st.divider()
    st.caption("版本: v2.2 Stable")
    
    if not api_key:
        st.warning("⚠️ 請輸入 API Key 以啟動系統")
        st.stop()

fred = Fred(api_key=api_key)

# ==========================================
# 2. 數據引擎 (Data Engine)
# ==========================================
@st.cache_data(ttl=3600)
def get_macro_data():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*6) # 抓過去 6 年
    
    tickers = {
        # --- Type A: 指數型 (需要算 YoY 的) ---
        'CPIAUCSL': 'CPI (Headline)',         
        'CPILFESL': 'CPI (Core)',             
        'PPIFIS':   'PPI (Final Demand)',     
        'PCEPI':    'PCE (Headline)',         
        'CUSR0000SAD': 'Supercore (Svcs ex Shelter)', 
        'CUSR0000SETA02': 'Used Cars',        
        'CUSR0000SAH1': 'CPI Shelter', 
        'CHNTOT': 'China Import Prices', # 改用美國官方數據 (中國進口價格)
        
        # --- Type B: 百分比/數值型 (直接顯示的) ---
        'STICKCPIM159SFRBATL': 'Sticky CPI', # 159 是 YoY 版本
        'T5YIE': '5Y Breakeven',              
        'DFII10': '10Y Real Yield',           
    }
    
    df = pd.DataFrame()
    for code, name in tickers.items():
        try:
            series = fred.get_series(code, observation_start=start_date)
            df[name] = series
        except Exception as e:
            st.error(f"數據抓取失敗 [{name}]: {e}")
    
    return df

def process_data(df):
    # 定義哪些欄位是指數 (Index)，需要算年增率
    index_cols = [
        'CPI (Headline)', 'CPI (Core)', 'PPI (Final Demand)', 'PCE (Headline)', 
        'Supercore (Svcs ex Shelter)', 'Used Cars', 'CPI Shelter', 'China Import Prices'
    ]
    
    # 定義哪些欄位已經是百分比 (Rate)，直接用
    rate_cols = ['Sticky CPI', '5Y Breakeven', '10Y Real Yield']
    
    df_yoy = pd.DataFrame()
    
    # 處理指數型數據 -> 轉 YoY
    for col in index_cols:
        if col in df.columns:
            df_yoy[col] = df[col].pct_change(12) * 100
            
    # 處理百分比數據 -> 直接複製
    for col in rate_cols:
        if col in df.columns:
            df_yoy[col] = df[col]
            
    # 計算衍生指標：企業利潤剪刀差
    if 'CPI (Headline)' in df_yoy.columns and 'PPI (Final Demand)' in df_yoy.columns:
        df_yoy['Profit Spread'] = df_yoy['CPI (Headline)'] - df_yoy['PPI (Final Demand)']

    return df, df_yoy

# ==========================================
# 3. 視覺化與教育模組 (Visual & Edu Helper)
# ==========================================
def plot_chart(df, cols, title, height=400):
    fig = go.Figure()
    for col in cols:
        if col in df.columns:
            # 重點指標加粗
            width = 3 if "CPI" in col or "Spread" in col else 1.5
            fig.add_trace(go.Scatter(x=df.index, y=df[col], mode='lines', name=col, line=dict(width=width)))
    
    # 畫零軸
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    
    fig.update_layout(
        title=title, 
        xaxis_title="年份", 
        yaxis_title="%", 
        margin=dict(l=20, r=20, t=40, b=20), 
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig, use_container_width=True)

def show_edu_card(title, definition, example, signal):
    """顯示教育小卡"""
    with st.expander(f"📖 {title}：指標解讀與實戰教學 (點我展開)"):
        st.markdown(f"""
        <div class="info-box">
            <p><strong>🧐 定義：</strong>{definition}</p>
            <p><strong>🍎 舉例：</strong>{example}</p>
            <p><strong>⚡ 投資訊號：</strong>{signal}</p>
        </div>
        """, unsafe_allow_html=True)

# ==========================================
# 4. 主介面邏輯
# ==========================================
st.title("🕵️‍♂️ Macro CPI Agent v2.2 (教育增強版)")
st.markdown("### 全方位通膨監測與宏觀分析系統")

try:
    with st.spinner("正在連線至聯準會資料庫 (FRED) 下載最新數據..."):
        raw_df = get_macro_data()
        
    if 'CPI (Headline)' not in raw_df.columns:
        st.error("❌ 嚴重錯誤：無法取得 CPI 數據，請檢查 API Key 或網路連線。")
        st.stop()

    # 確保至少有 CPI 數據才繼續
    raw_df = raw_df.dropna(subset=['CPI (Headline)'])
    _, df_yoy = process_data(raw_df)
    
    # 取得最新一筆數據
    latest = df_yoy.iloc[-1]
    prev = df_yoy.iloc[-2]
    
    st.markdown(f"**數據更新日期**: {df_yoy.index[-1].strftime('%Y-%m-%d')}")
    st.divider()

    # --- 第一區：KPI 戰情看板 ---
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("CPI (Headline)", f"{latest['CPI (Headline)']:.2f}%", f"{latest['CPI (Headline)']-prev['CPI (Headline)']:.2f}%")
    col2.metric("PPI (Final Demand)", f"{latest['PPI (Final Demand)']:.2f}%", f"{latest['PPI (Final Demand)']-prev['PPI (Final Demand)']:.2f}%")
    col3.metric("超級核心 Supercore", f"{latest['Supercore (Svcs ex Shelter)']:.2f}%", f"{latest['Supercore (Svcs ex Shelter)']-prev['Supercore (Svcs ex Shelter)']:.2f}%")
    col4.metric("利潤剪刀差", f"{latest['Profit Spread']:.2f}%", f"{latest['Profit Spread']-prev['Profit Spread']:.2f}%", delta_color="normal")

    # --- 第二區：多維度分析 Tab ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 核心趨勢", 
        "🏗️ 結構拆解", 
        "🏭 全球供應鏈", 
        "🧠 市場預期", 
        "🔮 未來模擬"
    ])

    # Tab 1: 核心趨勢
    with tab1:
        st.subheader("CPI vs PPI：通膨傳導鏈")
        plot_chart(df_yoy, ['CPI (Headline)', 'PPI (Final Demand)'], "消費者物價 vs 生產者物價")
        show_edu_card(
            title="PPI (生產者) vs CPI (消費者)",
            definition="PPI 是工廠出貨價格 (成本)，CPI 是你在超市看到的價格 (售價)。",
            example="麵粉變貴了 (PPI 漲)，麵包店老闆撐了三個月後，決定漲麵包價格 (CPI 漲)。**PPI 通常領先 CPI 約 3 個月。**",
            signal="如果 PPI 突然飆高，小心幾個月後 CPI 也會跟著爆發，股市通常會提前反應利空。"
        )

        st.subheader("企業利潤壓力指標 (剪刀差)")
        # 畫面積圖
        fig_spread = go.Figure()
        fig_spread.add_trace(go.Scatter(x=df_yoy.index, y=df_yoy['Profit Spread'], fill='tozeroy', name='Spread (CPI-PPI)'))
        fig_spread.add_hline(y=0, line_color="red", line_dash="dash")
        fig_spread.update_layout(title="剪刀差 = CPI - PPI", yaxis_title="%", height=350, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_spread, use_container_width=True)
        
        show_edu_card(
            title="剪刀差 (Profit Spread)",
            definition="公式 = CPI (售價) - PPI (成本)。反映企業的好賺程度。",
            example="你賣雞排一份 100 元 (CPI)，雞肉成本 50 元 (PPI)，你賺翻了。如果雞肉漲到 110 元，你還不敢漲價，你就虧錢了。",
            signal="**數值 > 0 (正值擴大)**：利多，買進消費股/製造業。**數值 < 0**：利空，避開低毛利製造業，資金轉向軟體或防禦股。"
        )

    # Tab 2: 結構拆解
    with tab2:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("黏性 vs 核心")
            plot_chart(df_yoy, ['CPI (Core)', 'Sticky CPI'], "Sticky CPI (紅) vs Core CPI (藍)")
            show_edu_card(
                title="黏性通膨 (Sticky CPI)",
                definition="價格一旦漲上去就很難跌下來的項目（如：理髮、醫療、房租）。",
                example="油價可能下個月就崩盤，但你剪頭髮的價格漲到 500 元後，通常不會再降回 300 元。",
                signal="如果 Sticky CPI 居高不下，Fed 就不敢降息。這是**「通膨是否頑固」**的最佳指標。"
            )
        with col_b:
            st.subheader("領先指標：二手車")
            plot_chart(df_yoy, ['Used Cars', 'CPI (Core)'], "二手車 (綠) vs Core CPI (藍)")
            show_edu_card(
                title="二手車指數 (Used Cars)",
                definition="核心商品通膨的「炭絲雀」。",
                example="因為它是批發價，反應比零售快。2021年通膨大爆發，就是從二手車先開始漲的。",
                signal="如果二手車指數開始跳水，通常 **2-3 個月後** 核心商品 CPI 就會跟著下降。"
            )

        st.subheader("魔王關卡：超級核心 (Supercore)")
        plot_chart(df_yoy, ['Supercore (Svcs ex Shelter)'], "服務業扣除房租 (Supercore)")
        show_edu_card(
            title="超級核心 (Supercore)",
            definition="核心服務 - 房租。Fed 主席 Powell 最盯著看的指標，反映「薪資螺旋」。",
            example="修水管的人工費、律師費、醫療費。這最能代表現在勞動力市場有多熱。",
            signal="只要這條線還在往上衝，Fed 就絕對不會降息。**這是判斷 Fed 轉向的關鍵。**"
        )

    # Tab 3: 全球供應鏈 (使用 China Import Prices)
    with tab3:
        st.subheader("輸入性通膨：中國進口價格 (China Import Prices)")
        plot_chart(df_yoy, ['China Import Prices', 'PPI (Final Demand)'], "中國進口價格 (紅) vs 美國 PPI (藍)")
        show_edu_card(
            title="中國進口價格指數 (Import Price from China)",
            definition="衡量美國從中國進口商品的價格變化 (由 BLS 發布)。",
            example="**輸入性通縮**：如果這條線是負的 (例如 -2%)，代表中國工廠為了搶訂單在降價賣給美國，這會直接壓低美國好市多架上的商品價格。",
            signal="**數值 < 0**：強力的通膨降溫劑。**數值 > 0**：小心，廉價商品的時代結束了，通膨可能會反撲。"
        )

        st.subheader("生產者物價細節")
        plot_chart(df_yoy, ['PPI (Final Demand)', 'CPI (Headline)'], "成本端 vs 消費端")

    # Tab 4: 市場預期
    with tab4:
        st.subheader("實質利率 (Real Yield)")
        plot_chart(df_yoy, ['10Y Real Yield'], "10年期實質利率", height=350)
        show_edu_card(
            title="實質利率 (Real Yield)",
            definition="名目公債殖利率 - 通膨預期。這是資金的「真實成本」。",
            example="銀行利率 5%，但通膨 4%，你借錢的真實壓力只有 1%。如果通膨變 0%，你壓力就變 5% 了。",
            signal="**數值 > 2.0%**：資金成本極高，對科技股 (估值高) 是殺手。**數值 < 0%**：資金氾濫，有利資產泡沫。"
        )
        
        st.subheader("市場通膨預期 (Breakeven)")
        plot_chart(df_yoy, ['5Y Breakeven', 'CPI (Headline)'], "市場預期 (綠) vs 實際通膨 (藍)")
        show_edu_card(
            title="平衡通膨率 (Breakeven Rate)",
            definition="債券交易員用真金白銀賭出來的「未來 5 年平均通膨率」。",
            example="如果 CPI 現在是 5%，但 Breakeven 只有 2.3%，代表市場覺得「安啦，這只是暫時的，未來會降回去」。",
            signal="**如果 CPI 漲，但 Breakeven 不漲**：買債券的好機會。**如果兩者一起噴出**：代表市場對央行失去信心，通膨失控。"
        )

    # Tab 5: 未來模擬
    with tab5:
        st.subheader("基期效應模擬器")
        st.markdown("此工具用於預測：**「在不同的月增率假設下，未來的年增率會因為數學公式而如何變化？」**")
        
        assumed_mom = st.slider("假設未來每月月增率 (MoM %)", -0.2, 1.0, 0.2, 0.1) / 100
        months_predict = 6
        
        last_val = raw_df['CPI (Headline)'].iloc[-1]
        # 抓取去年的指數作為基期
        base_vals = raw_df['CPI (Headline)'].iloc[-13:-13+months_predict].values
        
        future_yoy = []
        curr = last_val
        for i in range(months_predict):
            curr = curr * (1 + assumed_mom)
            if i < len(base_vals):
                future_yoy.append((curr / base_vals[i] - 1) * 100)
            else:
                future_yoy.append(np.nan)
                
        future_dates = [df_yoy.index[-1] + pd.DateOffset(months=i+1) for i in range(months_predict)]
        sim_df = pd.DataFrame({'Predicted CPI YoY': future_yoy}, index=future_dates)
        
        fig_sim = go.Figure()
        hist_data = df_yoy['CPI (Headline)'].tail(12)
        fig_sim.add_trace(go.Scatter(x=hist_data.index, y=hist_data, name='History', line=dict(color='gray')))
        fig_sim.add_trace(go.Scatter(x=sim_df.index, y=sim_df['Predicted CPI YoY'], name='Forecast', line=dict(color='red', dash='dot', width=3)))
        
        last_pred = future_yoy[-1] if future_yoy else 0
        fig_sim.update_layout(title=f"模擬結果：若 MoM 維持 {assumed_mom*100:.1f}%，半年後 CPI YoY 將來到 {last_pred:.2f}%")
        st.plotly_chart(fig_sim, use_container_width=True)
        
        show_edu_card(
            title="基期效應 (Base Effect)",
            definition="因為去年的比較基準 (分母) 不同，導致今年的年增率出現數學上的波動。",
            example="去年這個月油價大漲 (基期高)，所以今年就算油價沒跌，算出來的年增率也會大跌。",
            signal="利用這個模擬器，你可以比新聞媒體早 6 個月知道「通膨會不會因為數學公式而自動反彈」，提早佈局。"
        )

except Exception as e:
    st.error(f"發生系統錯誤：{e}")
    st.warning("請檢查：1. API Key 是否正確 2. FRED 伺服器狀態。")