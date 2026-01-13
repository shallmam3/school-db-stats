import streamlit as st
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import pandas as pd
import time
import re
from urllib.parse import urlparse

# --- 核心逻辑函数 ---

def search_library_url(school_name):
    """
    利用 DuckDuckGo 搜索学校图书馆数据库列表的 URL
    """
    query = f"{school_name} 图书馆 数据库 列表"
    print(f"正在搜索: {query}")
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            # 返回第一个看起来像链接的结果
            return results[0]['href']
    except Exception as e:
        st.error(f"搜索出错: {e}")
    return None

def is_chinese(string):
    """判断字符串是否含有中文"""
    for char in string:
        if '\u4e00' <= char <= '\u9fa5':
            return True
    return False

def analyze_page(url):
    """
    抓取并智能分析页面内容
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding # 自动修复乱码
        soup = BeautifulSoup(response.text, 'lxml')
        
        # --- 智能解析策略 ---
        # 难点：如何从杂乱的网页中只提取数据库名字？
        # 策略：通常数据库列表在 <li> 或 <tr> 标签下的 <a> 标签中
        # 我们提取页面主要内容区域的链接
        
        # 1. 尝试移除导航栏和页脚（简单的清理）
        for tag in soup(['header', 'footer', 'nav', 'script', 'style']):
            tag.decompose()
            
        # 2. 提取所有链接文本
        links = soup.find_all('a')
        
        db_list = []
        for link in links:
            text = link.get_text(strip=True)
            # 过滤掉无效链接（如“首页”、“联系我们要”、“English”等短词）
            if len(text) > 3 and len(text) < 50: 
                # 这里可以加更复杂的关键词过滤
                db_list.append(text)
        
        # 简单去重
        db_list = list(set(db_list))
        
        cn_dbs = []
        other_dbs = []
        
        for db in db_list:
            if is_chinese(db):
                cn_dbs.append(db)
            else:
                other_dbs.append(db)
                
        return cn_dbs, other_dbs

    except Exception as e:
        return None, None

# --- Streamlit 页面 UI ---

st.set_page_config(page_title="高校数据库统计助手", layout="wide")

st.title("📚 高校图书馆数据库自动统计器")
st.markdown("输入学校名称，程序将尝试自动寻找其图书馆页面并统计数据库数量。")

school_input = st.text_input("请输入学校全称（例如：西安交通大学）", "")

if st.button("开始分析"):
    if not school_input:
        st.warning("请先输入学校名称")
    else:
        with st.status(f"正在处理 {school_input} ...", expanded=True) as status:
            
            # 第一步：搜索 URL
            status.write("🔍 正在搜索图书馆数据库网址...")
            target_url = search_library_url(school_input)
            
            if target_url:
                st.success(f"找到疑似地址: {target_url}")
                
                # 第二步：抓取与分析
                status.write("⬇️ 正在下载并解析页面内容...")
                cn_list, en_list = analyze_page(target_url)
                
                if cn_list is not None:
                    status.update(label="处理完成!", state="complete", expanded=False)
                    
                    # --- 展示结果 ---
                    col1, col2, col3 = st.columns(3)
                    col1.metric("中文数据库 (估算)", f"{len(cn_list)} 个")
                    col2.metric("外文/其他数据库 (估算)", f"{len(en_list)} 个")
                    col3.metric("总计", f"{len(cn_list) + len(en_list)} 个")
                    
                    st.divider()
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("📋 识别到的中文库 (部分)")
                        st.dataframe(cn_list, use_container_width=True)
                    with c2:
                        st.subheader("📋 识别到的外文库 (部分)")
                        st.dataframe(en_list, use_container_width=True)
                        
                else:
                    status.update(label="抓取失败", state="error")
                    st.error("无法访问该网页，可能是需要校内网(VPN)才能访问，或者网页有反爬虫验证。")
            else:
                status.update(label="搜索失败", state="error")
                st.error("未找到该学校的数据库列表页面，请检查校名是否正确。")