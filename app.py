import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

# --- 核心逻辑 ---

def google_search_url(school_name, api_key):
    """
    使用 Serper API (Google) 绕过云端 IP 限制，精准寻找目标网址
    """
    url = "https://google.serper.dev/search"
    
    # 组合更精准的搜索词，提高命中率
    query = f"{school_name} 图书馆 数据库导航 列表"
    
    payload = str({
        "q": query,
        "gl": "cn",
        "hl": "zh-cn"
    }).replace("'", '"')
    
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, json={"q": query, "gl": "cn", "hl": "zh-cn"})
        results = response.json()
        
        # 获取自然搜索结果的第一条
        if 'organic' in results and len(results['organic']) > 0:
            top_link = results['organic'][0]['link']
            print(f"API 找到链接: {top_link}")
            return top_link
        else:
            return None
    except Exception as e:
        st.error(f"API 连接失败: {e}")
        return None

def is_chinese(string):
    """判断是否包含中文"""
    for char in string:
        if '\u4e00' <= char <= '\u9fa5':
            return True
    return False

def analyze_page(url):
    """抓取并分析页面"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')

        # 清理干扰项
        for tag in soup(['header', 'footer', 'nav', 'script', 'style', 'noscript']):
            tag.decompose()
        
        links = soup.find_all('a')
        db_list = []
        
        for link in links:
            text = link.get_text(strip=True)
            # 智能过滤：去掉由于“首页”、“登录”等短词，以及过长的句子
            if 3 < len(text) < 50: 
                db_list.append(text)
        
        # 去重
        db_list = list(set(db_list))
        
        cn_dbs = [db for db in db_list if is_chinese(db)]
        other_dbs = [db for db in db_list if not is_chinese(db)]
                
        return cn_dbs, other_dbs

    except Exception as e:
        st.error(f"无法读取该学校页面: {e}")
        return None, None

# --- UI 界面 ---

st.set_page_config(page_title="高校数据库智能统计", page_icon="🕵️")

st.title("🕵️ 高校数据库全自动统计")
st.markdown("集成 **Google Search API**，自动突破反爬虫限制，寻找数据库列表。")

# 侧边栏输入 Key，避免每次都要输
with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input("2ba768b7f52d792da0b87486b73acfc5d305f4a3", type="password", help="去 serper.dev 免费申请")
    st.markdown("[👉 点击获取免费 Key](https://serper.dev/)")

school_input = st.text_input("请输入学校全称（例如：陕西师范大学）")

if st.button("开始全自动分析"):
    if not api_key:
        st.error("请先在左侧侧边栏填入 API Key！")
    elif not school_input:
        st.warning("请先输入学校名称")
    else:
        # 1. 调用 API 自动搜索
        with st.status("🤖 正在指挥 Google 搜索数据库网址...", expanded=True) as status:
            target_url = google_search_url(school_input, api_key)
            
            if target_url:
                status.write(f"✅ 成功找到地址: {target_url}")
                status.write("⬇️ 正在潜入页面抓取数据...")
                
                # 2. 分析页面
                cn_list, en_list = analyze_page(target_url)
                
                if cn_list is not None:
                    status.update(label="分析完成！", state="complete", expanded=False)
                    
                    # 3. 展示结果
                    st.divider()
                    st.success(f"📊 {school_input} 分析报告")
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("中文数据库", f"{len(cn_list)}")
                    col2.metric("外文/其他", f"{len(en_list)}")
                    col3.metric("总计", f"{len(cn_list) + len(en_list)}")
                    
                    tab1, tab2 = st.tabs(["📝 中文库清单", "🌍 外文库清单"])
                    with tab1:
                        st.dataframe(pd.DataFrame(cn_list, columns=["数据库名称"]), use_container_width=True)
                    with tab2:
                        st.dataframe(pd.DataFrame(en_list, columns=["数据库名称"]), use_container_width=True)
                else:
                    status.update(label="抓取页面失败", state="error")
            else:
                status.update(label="搜索未找到有效结果", state="error")
                st.error("API 返回空结果，可能该学校没有公开的数据库列表页。")