import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json

# --- 核心配置 ---
st.set_page_config(
    page_title="高校数据库统计", 
    page_icon="📱",
    layout="centered" # 手机端使用 centered 布局视觉更聚焦
)

# --- 核心逻辑 ---

def get_api_key():
    """安全地从 Streamlit Secrets 获取 Key"""
    try:
        return st.secrets["SERPER_API_KEY"]
    except FileNotFoundError:
        st.error("❌ 未配置 API Key！请在 Streamlit Cloud 后台 Settings -> Secrets 中添加 SERPER_API_KEY。")
        return None

def google_search_url(school_name, api_key):
    """搜索逻辑"""
    url = "https://google.serper.dev/search"
    queries = [
        f"{school_name} 图书馆 数据库 列表",
        f"{school_name} 图书馆 电子资源 导航",
    ]
    
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json; charset=utf-8'
    }

    for query in queries:
        try:
            payload = json.dumps({
                "q": query, 
                "gl": "cn", 
                "hl": "zh-cn"
            }, ensure_ascii=False).encode('utf-8')

            response = requests.post(url, headers=headers, data=payload, timeout=10)
            if response.status_code == 200:
                results = response.json()
                if 'organic' in results and len(results['organic']) > 0:
                    return results['organic'][0]['link']
        except Exception:
            continue
    return None

def is_chinese(string):
    for char in string:
        if '\u4e00' <= char <= '\u9fa5':
            return True
    return False

def analyze_page(url):
    headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for tag in soup(['header', 'footer', 'nav', 'script', 'style', 'noscript']):
            tag.decompose()
        
        links = soup.find_all('a')
        db_list = []
        for link in links:
            text = link.get_text(strip=True)
            if 3 < len(text) < 50: 
                db_list.append(text)
        
        db_list = list(set(db_list))
        cn_dbs = [db for db in db_list if is_chinese(db)]
        other_dbs = [db for db in db_list if not is_chinese(db)]
        return cn_dbs, other_dbs
    except Exception as e:
        return None, None

# --- 手机端 UI 优化 ---

st.markdown("### 🏫 高校数据库统计")
st.caption("自动搜索并统计图书馆购买的数据库数量")

# 1. 简洁的输入区
col1, col2 = st.columns([3, 1])
with col1:
    school_input = st.text_input("输入校名", placeholder="例如：陕西师范大学", label_visibility="collapsed")
with col2:
    start_btn = st.button("开始", type="primary", use_container_width=True)

# 2. 状态显示区（用较小的字体）
status_container = st.empty()

if start_btn:
    api_key = get_api_key()
    
    if not school_input:
        st.toast("⚠️ 请输入学校名称")
    elif api_key:
        
        # 步骤 A: 搜索
        status_container.info("🔍 正在寻找数据库网页...")
        target_url = google_search_url(school_input, api_key)
        
        if target_url:
            # 步骤 B: 分析
            status_container.success(f"✅ 找到网页，正在分析...")
            cn_list, en_list = analyze_page(target_url)
            
            status_container.empty() # 清空状态栏，展示结果
            
            if cn_list is not None:
                total = len(cn_list) + len(en_list)
                
                # --- 核心结果区 (大字号卡片) ---
                st.divider()
                st.markdown(f"**{school_input}**")
                
                # 使用原生 metric，手机会自动堆叠
                m1, m2, m3 = st.columns(3)
                m1.metric("总计", total)
                m2.metric("中文", len(cn_list))
                m3.metric("外文", len(en_list))
                
                st.divider()
                
                # --- 详情区 (默认折叠，节省手机空间) ---
                with st.expander("📄 查看详细名单 (点击展开)"):
                    st.markdown("**🇨🇳 中文数据库**")
                    st.dataframe(pd.DataFrame(cn_list, columns=["名称"]), hide_index=True, use_container_width=True)
                    
                    st.markdown("**🌍 外文/其他数据库**")
                    st.dataframe(pd.DataFrame(en_list, columns=["名称"]), hide_index=True, use_container_width=True)
                    
                st.caption(f"数据来源: {target_url}")
                
            else:
                st.error("无法读取页面，可能有防火墙拦截。")
        else:
            status_container.warning("未找到该学校的公开数据库列表。")
            # 兜底：允许手动输入
            manual_url = st.text_input("尝试手动粘贴网址：")