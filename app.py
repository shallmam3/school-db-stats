import streamlit as st
import subprocess
import os
import json
import requests
import time
from bs4 import BeautifulSoup
import pandas as pd
from collections import Counter

# --- 1. 环境初始化 ---
if "playwright_installed" not in st.session_state:
    if not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")):
        with st.spinner("正在初始化云端浏览器..."):
            subprocess.run(["playwright", "install", "chromium"])
    st.session_state.playwright_installed = True

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    st.error("请检查 requirements.txt 是否包含 playwright")
    st.stop()

# --- 2. 核心功能函数 ---

def get_api_key():
    try:
        return st.secrets["SERPER_API_KEY"]
    except:
        return None

def google_search_url(school_name, api_key):
    """搜索入口 URL"""
    url = "https://google.serper.dev/search"
    queries = [
        f"{school_name} 图书馆 \"已购资源\" 列表",
        f"{school_name} 图书馆 数据库导航",
        f"{school_name} 图书馆 电子资源列表 site:edu.cn"
    ]
    
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json; charset=utf-8'}

    for query in queries:
        try:
            payload = json.dumps({"q": query, "gl": "cn", "hl": "zh-cn"}, ensure_ascii=False).encode('utf-8')
            response = requests.post(url, headers=headers, data=payload, timeout=10)
            if response.status_code == 200:
                results = response.json()
                if 'organic' in results and len(results['organic']) > 0:
                    return results['organic'][0]['link']
        except:
            continue
    return None

def extract_from_table(soup):
    """识别表格内容 (兼容西科大左右分栏)"""
    db_list = []
    tables = soup.find_all('table')
    
    for table in tables:
        text_content = table.get_text()
        keywords = ["数据库", "资源", "题名", "已购", "订购", "中文", "外文"]
        if sum(1 for k in keywords if k in text_content) < 2:
            continue
            
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                links = cell.find_all('a')
                for link in links:
                    text = link.get_text(strip=True)
                    if 2 < len(text) < 60:
                        db_list.append(text)
                if not links:
                     text = cell.get_text(strip=True)
                     if 2 < len(text) < 60 and not text.isdigit():
                         db_list.append(text)
    return db_list

def smart_crawl_and_extract(url):
    """Playwright 动态抓取"""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36')
            page = context.new_page()
            
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3) 
            
            # 尝试智能点击“已购资源”
            content = page.content()
            if "已购资源" in content and "中文数据库" not in content:
                try:
                    page.get_by_text("已购资源", exact=False).first.click(timeout=3000)
                    time.sleep(3)
                except:
                    pass

            final_content = page.content()
            browser.close()
            
            soup = BeautifulSoup(final_content, 'html.parser')
            db_list = extract_from_table(soup)
            
            # 兜底策略
            if len(db_list) < 5:
                for tag in soup(['header', 'footer', 'nav', 'script', 'style']):
                    tag.decompose()
                for link in soup.find_all('a'):
                    txt = link.get_text(strip=True)
                    if 3 < len(txt) < 50:
                        db_list.append(txt)

            return db_list
        except Exception as e:
            print(f"Error: {e}")
            return []

def is_chinese(string):
    for char in string:
        if '\u4e00' <= char <= '\u9fa5': return True
    return False

def clean_data(raw_list):
    blacklist = [
        "首页", "登录", "注册", "更多", "查看", "订购", "试用", "简介", "指南", 
        "详细", "访问", "校外", "咨询", "反馈", "点击", "下载", "English",
        "序号", "状态", "类型", "名称", "数据库名称", "操作", "来源", "链接", 
        "提交", "部门", "版权", "所有", "导航"
    ]
    clean_list = []
    for item in raw_list:
        text = item.strip()
        if 2 < len(text) < 60 and not text.isdigit():
            if not any(junk in text for junk in blacklist):
                clean_list.append(text)
    return list(set(clean_list))

# --- 3. UI 界面 ---
st.set_page_config(page_title="高校数据库统计Pro", page_icon="🏫", layout="wide")

st.title("🏫 高校数据库全自动统计 (Pro版)")

with st.sidebar:
    st.header("⚙️ 配置参数")
    api_key = st.text_input("SERPER_API_KEY", value=get_api_key() or "", type="password")
    st.divider()
    school_input = st.text_input("🏫 学校全称", placeholder="例如：西安科技大学")
    st.markdown("**或者**")
    manual_url = st.text_input("🔗 指定目标 URL (精准模式)", placeholder="例如：...wbtreeid=6533")
    st.caption("提示：如果自动搜索不准，请直接在此粘贴目标网址。")
    start_btn = st.button("开始分析", type="primary", use_container_width=True)

if start_btn:
    if not api_key:
        st.error("请配置 SERPER_API_KEY")
        st.stop()
    
    target_url = None
    status = st.status("正在初始化...", expanded=True)
    
    if manual_url:
        target_url = manual_url
        status.write(f"🔗 使用用户指定 URL: {target_url}")
    elif school_input:
        status.write(f"🔍 正在搜索 {school_input}...")
        target_url = google_search_url(school_input, api_key)
        if target_url:
            status.write(f"🌐 自动找到入口: {target_url}")
        else:
            status.update(label="❌ 搜索失败", state="error")
            st.error("未找到相关网页，请尝试手动输入 URL。")
            st.stop()
    else:
        st.warning("请输入学校名称或目标 URL")
        st.stop()

    if target_url:
        status.write("🕵️ 正在启动云端浏览器抓取...")
        raw_dbs = smart_crawl_and_extract(target_url)
        status.write(f"📦 原始提取条目数: {len(raw_dbs)}")
        
        final_dbs = clean_data(raw_dbs)
        cn_dbs = sorted([d for d in final_dbs if is_chinese(d)])
        en_dbs = sorted([d for d in final_dbs if not is_chinese(d)])
        total = len(cn_dbs) + len(en_dbs)
        
        status.update(label="✅ 分析完成！", state="complete", expanded=False)
        
        st.divider()
        st.markdown(f"### 📊 分析报告: {school_input if school_input else '自定义链接'}")
        st.caption(f"数据来源: [{target_url}]({target_url})")
        
        if total == 0:
            st.error("⚠️ 未提取到有效数据，请检查 URL 或网络。")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("📚 总计资源", total)
            c2.metric("🇨🇳 中文数据库", len(cn_dbs))
            c3.metric("🌍 外文数据库", len(en_dbs))
            
            st.divider()
            c_left, c_right = st.columns(2)
            with c_left:
                st.subheader("中文数据库")
                if cn_dbs:
                    df_cn = pd.DataFrame(cn_dbs, columns=["名称"])
                    df_cn.index += 1
                    st.dataframe(df_cn, use_container_width=True)
            with c_right:
                st.subheader("外文数据库")
                if en_dbs:
                    df_en = pd.DataFrame(en_dbs, columns=["名称"])
                    df_en.index += 1
                    st.dataframe(df_en, use_container_width=True)