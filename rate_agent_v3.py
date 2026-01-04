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
st.set_page_config(page_title="Agent 4: 利率狙擊手 (Pro UI)", layout="wide", page_icon="🦅")

st.markdown("""
    <style>
    /* 核心卡片樣式 */
    .metric-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #2E86C1;}
    
    /* 策略說明框 */
    .strategy-box {
        background-color: #fff8e1;
        padding: 20px;
        border-radius: 8px;
        border: 1px solid #ffe082;
        margin-top: 10px;
        margin-bottom: 20px;
    }
    
    /* 文字強調 */
    .highlight-red {color: #d32f2f; font-weight: bold;}
    .highlight-green {color: #388e3c; font-weight: bold;}
    
    h1, h2, h3 { font-family: 'Roboto', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.title("🦅 利率狙擊手設定")
    DEFAULT_API_KEY = '3e2d2e27e5126fac34a02e9edaa80c2e' 
    api_key = st.text_input("輸入 FRED API Key", value=DEFAULT_API_KEY, type="password")
    
    st.info("💡 提示：若無 Key，請至 stlouisfed.org 申請免費 API Key。")
    
    years_back = st.slider("歷史數據長度 (年)", 3, 20, 5)
    
    st.divider()
    st.caption("版本: v6.2 Auto-History Fix")
    
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
        # --- 核心利率 ---
        'DGS10': 'US 10Y Yield',           
        'DGS2': 'US 2Y Yield',             
        'FEDFUNDS': 'Fed Funds Rate',      
        'DFII10': '10Y Real Yield',        
        'T10Y3M': '10Y-3M Spread',         
        'DGS30': 'US 30Y Yield', 

        # --- 流動性相關 ---
        'WALCL': 'Fed Total Assets',  
        'WTREGEN': 'TGA Account',     
        'RRPONTSYD': 'Reverse Repo',  
        
        # --- 危機監控 ---
        'SOFR': 'SOFR Rate',          
        'IORB': 'IORB Rate',          
        'TOTRESNS': 'Bank Reserves',  

        # --- Fed 枷鎖 ---
        'CUSR0000SAD': 'Supercore CPI Index', 
        'T5YIE': '5Y Breakeven',              
        
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
        except Exception:
            pass

    if not data_frames:
        return pd.DataFrame()

    df = pd.concat(data_frames, axis=1)
    df = df.ffill()
    df = df.dropna(subset=['US 10Y Yield'])
    
    return df

def process_rates_data(df):
    # 1. 淨流動性
    req_liq = ['Fed Total Assets', 'TGA Account', 'Reverse Repo']
    if all(col in df.columns for col in req_liq):
        fed = df['Fed Total Assets'] / 1000000 
        tga = df['TGA Account'] / 1000000      
        rrp = df['Reverse Repo'] / 1000        
        df['Net Liquidity'] = fed - tga - rrp
    else:
        df['Net Liquidity'] = np.nan

    # 2. 流動性壓力
    if 'SOFR Rate' in df.columns and 'IORB Rate' in df.columns:
        df['Liquidity Stress'] = df['SOFR Rate'] - df['IORB Rate']
        
    # 3. Supercore YoY
    if 'Supercore CPI Index' in df.columns:
        df['Supercore YoY'] = df['Supercore CPI Index'].pct_change(252) * 100

    # 4. Bank Reserves
    if 'Bank Reserves' in df.columns:
        df['Bank Reserves Trillions'] = df['Bank Reserves'] / 1000

    # 5. Curve
    if 'US 10Y Yield' in df.columns and 'US 2Y Yield' in df.columns:
        df['Curve 10Y-2Y'] = df['US 10Y Yield'] - df['US 2Y Yield']
        
    return df

# ==========================================
# 3. 視覺化模組
# ==========================================
def render_kpi_table(data_list):
    st.markdown("#### 📊 關鍵指標解讀")
    for row in data_list:
        with st.container():
            c1, c2, c3 = st.columns([1.5, 2.5, 4])
            with c1:
                st.markdown(f"#### 🔹 {row['indicator']}")
            with c2:
                st.markdown(f"**🧐 意義：**")
                st.markdown(f"{row['meaning']}")
            with c3:
                st.markdown(f"**💰 投資解讀：**")
                st.markdown(f"{row['view']}", unsafe_allow_html=True)
            st.divider()

def plot_dual_axis(df, col1, col2, title, name1, name2):
    # 這裡的 dropna 會自動裁切掉沒有 SOFR 數據的年份
    plot_df = df[[col1, col2]].dropna()
    if plot_df.empty: return

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col1], name=name1, line=dict(color='#1f77b4', width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col2], name=name2, line=dict(color='#ff7f0e', width=2)), secondary_y=True)
    
    fig.update_layout(title=title, height=400, hovermode="x unified", legend=dict(orientation="h", y=1.1), margin=dict(t=40, b=20, l=20, r=20))
    fig.update_yaxes(title_text=name1, secondary_y=False)
    fig.update_yaxes(title_text=name2, secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

def plot_single_line(df, col, title, color='#1f77b4', hline=None):
    plot_df = df[[col]].dropna()
    if plot_df.empty: return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col], name=col, line=dict(color=color, width=2)))
    if hline is not None:
        fig.add_hline(y=hline, line_color="red", line_dash="dash")
    fig.update_layout(title=title, height=350, hovermode="x unified", margin=dict(t=40, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)

def plot_area_chart(df, col, title, threshold=0):
    if col not in df.columns: return
    plot_df = df[[col]].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col], fill='tozeroy', mode='lines', line=dict(color='black', width=1)))
    fig.add_hline(y=threshold, line_color="red", line_dash="dash")
    fig.update_layout(title=title, height=350, margin=dict(t=40, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)

def show_strategy_card(title, logic, mechanism, signal, conclusion):
    st.markdown(f"""
    <div class="strategy-box">
        <h4 style="margin-top:0;">♟️ {title}</h4>
        <p><strong>🧠 核心邏輯：</strong> {logic}</p>
        <p><strong>⚙️ 運作機制：</strong><br>{mechanism}</p>
        <p><strong>⚡ Agent 訊號：</strong> {signal}</p>
        <p class="highlight-red">📝 結論：{conclusion}</p>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 4. 主程式邏輯
# ==========================================
st.title("🦅 Agent 4: 利率狙擊手 (Pro UI)")
st.markdown("### 資金成本、流動性懸崖與 Fed 政策枷鎖")

try:
    with st.spinner("正在加載全球宏觀數據與戰略模型..."):
        raw_df = get_rates_data(years_back)
        df = process_rates_data(raw_df)
    
    if df.empty:
        st.error("無法取得數據。請檢查 API Key。")
        st.stop()

    latest = df.iloc[-1]
    prev = df.iloc[-7] 

    # --- KPI 看板 ---
    col1, col2, col3, col4, col5 = st.columns(5)
    
    if 'US 10Y Yield' in latest:
        d_10y = latest['US 10Y Yield'] - prev['US 10Y Yield']
        col1.metric("US 10Y (名目)", f"{latest['US 10Y Yield']:.2f}%", f"{d_10y:.2f}%", delta_color="inverse")
    
    if 'Net Liquidity' in latest:
        liq_curr = latest['Net Liquidity']
        col2.metric("淨流動性 (兆鎂)", f"${liq_curr:.2f}T", f"{liq_curr - prev['Net Liquidity']:.2f}T")
    
    if 'Bank Reserves Trillions' in latest:
        res_curr = latest['Bank Reserves Trillions']
        col3.metric("銀行準備金", f"${res_curr:.2f}T", f"{res_curr - prev.get('Bank Reserves Trillions', 0):.2f}T")

    if 'Liquidity Stress' in latest:
        stress_curr = latest['Liquidity Stress']
        col4.metric("SOFR-IORB", f"{stress_curr:.2f}%")

    if 'US 30Y Yield' in latest:
        y30_curr = latest['US 30Y Yield']
        col5.metric("30Y Yield", f"{y30_curr:.2f}%", f"{y30_curr - prev['US 30Y Yield']:.2f}%", delta_color="inverse")

    st.divider()

    # --- 六大功能分頁 ---
    tabs = st.tabs([
        "🌊 流動性引擎", 
        "🚨 危機偵測 (戰略核心)", 
        "🏛️ Fed 博弈", 
        "📉 衰退指標", 
        "💣 信用壓力", 
        "🧮 估值定價"
    ])

    # Tab 1: 流動性引擎
    with tabs[0]:
        st.subheader("為什麼利率升、股市還漲？")
        
        # 1. 核心圖表
        if 'Net Liquidity' in df.columns and 'S&P 500' in df.columns:
            plot_dual_axis(df, 'Net Liquidity', 'S&P 500', "淨流動性 vs S&P 500", "Net Liquidity ($Trillions)", "S&P 500 Index")
        
        c1, c2 = st.columns(2)
        with c1:
            if 'TGA Account' in df.columns: plot_single_line(df, 'TGA Account', "TGA (財政部口袋)")
        with c2:
            if 'Reverse Repo' in df.columns: plot_single_line(df, 'Reverse Repo', "RRP (逆回購 - 備用海綿)")

        render_kpi_table([
            {
                "indicator": "Net Liquidity (淨流動性)",
                "meaning": "Fed總資產 - TGA - RRP。市場真正能用的現金水位。",
                "view": "<b>趨勢追蹤</b>：只要藍線向上，市場就在寬鬆狀態，做多美股。若藍線向下且 RRP 枯竭，現金為王。"
            },
            {
                "indicator": "TGA (財政部帳戶)",
                "meaning": "政府的錢包。數值升高代表政府從市場「抽血」(發債吸金)。",
                "view": "<b>利空指標</b>：TGA 快速上升 = 流動性緊縮。需觀察是否伴隨股市下跌。"
            },
            {
                "indicator": "RRP (逆回購)",
                "meaning": "多餘資金的蓄水池 (海綿)。",
                "view": "<b>緩衝墊</b>：RRP 下降是「好」的 (海綿擠水支撐市場)。但 <span class='highlight-red'>RRP 歸零是極度危險的</span> (沒水了)。"
            }
        ])

    # Tab 2: 危機偵測
    with tabs[1]:
        st.header("🕵️‍♂️ 宏觀末日偵測器")
        
        # Part A: 懸崖
        st.subheader("A. 流動性懸崖 (Liquidity Cliff)")
        c_a1, c_a2 = st.columns(2)
        with c_a1:
            if 'SOFR Rate' in df.columns and 'IORB Rate' in df.columns:
                # 這裡修正為使用全 df，plot_dual_axis 內的 dropna 會自動處理資料起始點
                plot_dual_axis(df, 'SOFR Rate', 'IORB Rate', "水管壓力: SOFR(紅) vs IORB(藍)", "SOFR", "IORB")
                st.caption("註：SOFR 自 2018 年才開始有數據，因此圖表長度較短是正常的。")
        with c_a2:
            if 'Bank Reserves Trillions' in df.columns:
                plot_single_line(df, 'Bank Reserves Trillions', "主油箱: Bank Reserves", hline=3.0)

        render_kpi_table([
            {
                "indicator": "SOFR - IORB",
                "meaning": "市場借貸利率 vs Fed 給的利息。正值代表銀行缺錢。",
                "view": "<b>末日警鐘</b>：若 SOFR > IORB，代表銀行不惜高價搶錢。<span class='highlight-red'>立即清倉，崩盤在即。</span>"
            },
            {
                "indicator": "Bank Reserves (銀行準備金)",
                "meaning": "金融體系的血液總量。",
                "view": "<b>生命線</b>：低於 3.0 兆美元是休克邊緣。Fed 必須緊急介入 (QE)。"
            }
        ])

        st.divider()

        # Part B: 枷鎖
        st.subheader("B. Fed 政策枷鎖 & 債券義勇軍")
        
        c_b1, c_b2, c_b3 = st.columns(3)
        with c_b1:
            if 'Supercore YoY' in df.columns:
                plot_single_line(df.tail(252*3), 'Supercore YoY', "枷鎖1: Supercore", color='red', hline=3.0)
        with c_b2:
            if '5Y Breakeven' in df.columns:
                plot_single_line(df.tail(252*3), '5Y Breakeven', "枷鎖2: 通膨預期", color='orange', hline=2.5)
        with c_b3:
            if 'US 30Y Yield' in df.columns:
                plot_single_line(df.tail(252*3), 'US 30Y Yield', "義勇軍: 30Y Yield", color='black')

        show_strategy_card(
            title="戰略推演：債券義勇軍的反撲 (Bond Vigilantes)",
            logic="市場對 Fed 失去信任，拋售長債抗議。",
            mechanism="正常：QE 印鈔 → 買債 → 殖利率降。<br>失控：QE 印鈔 → 怕貨幣貶值 → 拋售長債 → <b>殖利率飆升</b>。",
            signal="Fed 暗示寬鬆，但 <b>US 30Y 不跌反漲</b>。",
            conclusion="Fed 喪失對長端利率控制權，印鈔無效，匯率與債市面臨崩潰。"
        )

        render_kpi_table([
            {
                "indicator": "Supercore CPI",
                "meaning": "超級核心通膨 (扣除房租服務)。Fed 最在意的通膨數據。",
                "view": "<b>手銬</b>：若 > 3%，Fed 雙手被綁，無法印鈔救市 (即使股市崩盤)。"
            },
            {
                "indicator": "US 30Y Yield",
                "meaning": "30年期公債殖利率。反映對美國財政的長期信心。",
                "view": "<b>信任票</b>：若在經濟轉弱時飆升，代表「債券義勇軍」在攻擊 Fed，股債雙殺。"
            }
        ])

    # Tab 3: Fed 博弈
    with tabs[2]:
        st.subheader("市場預期 (2Y) vs 官方利率 (Fed Funds)")
        if 'US 2Y Yield' in df.columns and 'Fed Funds Rate' in df.columns:
            plot_dual_axis(df, 'US 2Y Yield', 'Fed Funds Rate', "市場預期 vs Fed", "Yield", "Rate")
            
        render_kpi_table([
            {
                "indicator": "US 2Y Yield",
                "meaning": "市場對未來 2 年 Fed 利率的平均預期。",
                "view": "<b>領先指標</b>：若 2Y 急速下穿 Fed Funds Rate (深度倒掛)，代表市場在「逼宮」Fed 降息。買入美債 (TLT)。"
            },
            {
                "indicator": "Fed Funds Rate",
                "meaning": "聯準會控制的官方基準利率。",
                "view": "<b>滯後指標</b>：Fed 通常是最後一個承認經濟衰退並降息的人。"
            }
        ])

    # Tab 4: 衰退指標
    with tabs[3]:
        st.subheader("衰退指標：10Y - 3M")
        if '10Y-3M Spread' in df.columns:
            plot_area_chart(df, '10Y-3M Spread', "10Y - 3M Spread", 0)
            
        render_kpi_table([
            {
                "indicator": "Curve 10Y-3M (利差)",
                "meaning": "長債利率 - 短債利率。正常應為正值。",
                "view": "<b>衰退水晶球</b>：負值 (倒掛) = 警報響起。<span class='highlight-red'>最危險的是「倒掛解除」(V型反轉) 的瞬間</span>，通常伴隨衰退確認與股市補跌。"
            }
        ])

    # Tab 5: 信用壓力
    with tabs[4]:
        st.subheader("高收益債利差 (HY Spread)")
        if 'High Yield Spread' in df.columns and 'Financial Conditions' in df.columns:
            plot_dual_axis(df, 'High Yield Spread', 'Financial Conditions', "Credit Stress", "Spread", "Index")
            
        render_kpi_table([
            {
                "indicator": "High Yield Spread",
                "meaning": "垃圾債利率 - 公債利率。代表企業違約風險。",
                "view": "<b>礦坑金絲雀</b>：< 4% (安心做多)；> 5% (警戒)；> 8% (危機爆發)。股市通常反應比債市慢，聽債市的。"
            },
            {
                "indicator": "NFCI (金融狀況指數)",
                "meaning": "綜合股債匯的資金鬆緊度。負值=寬鬆，正值=緊縮。",
                "view": "<b>資金派對計</b>：若 Fed 升息但 NFCI 還是負的，代表市場根本不怕，股市繼續漲。"
            }
        ])

    # Tab 6: 估值定價
    with tabs[5]:
        st.subheader("股權風險溢酬 (ERP)")
        col_in, col_out = st.columns([1, 2])
        with col_in:
            if 'US 10Y Yield' in latest:
                curr_yield = latest['US 10Y Yield']
                pe = st.slider("S&P 500 P/E Ratio", 15.0, 40.0, 24.0)
                erp = (1/pe)*100 - curr_yield
                st.metric("預估 ERP", f"{erp:.2f}%")
        
        with col_out:
            fig_erp = go.Figure(go.Indicator(
                mode = "gauge+number", value = erp,
                title = {'text': "ERP (Risk Reward)"},
                gauge = {'axis': {'range': [-2, 6]}, 'bar': {'color': "black"},
                         'steps': [{'range': [-2, 1], 'color': "#ff4b4b"}, {'range': [1, 3], 'color': "#f7c948"}, {'range': [3, 6], 'color': "#3acf65"}]}
            ))
            fig_erp.update_layout(height=250)
            st.plotly_chart(fig_erp, use_container_width=True)

        render_kpi_table([
            {
                "indicator": "US 10Y (名目利率)",
                "meaning": "全球資產定價之錨 (無風險利率)。",
                "view": "<b>地心引力</b>：若短時間內急升 (如一週 +0.2%)，科技股 (Nasdaq) 估值必殺。"
            },
            {
                "indicator": "ERP (股權風險溢酬)",
                "meaning": "買股票比買公債多賺的預期報酬。公式: (1/PE) - 10Y。",
                "view": "<b>性價比</b>：< 0.5% (極貴，不如存定存)；> 3.0% (便宜，閉眼買)。"
            }
        ])

except Exception as e:
    st.error(f"系統錯誤: {e}")
    st.warning("請檢查 API Key 或網路連線。")