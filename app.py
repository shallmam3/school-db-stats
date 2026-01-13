import streamlit as st
import subprocess
import os
import json
import requests
import time
from bs4 import BeautifulSoup
import pandas as pd

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

def google_search_lib_url(school_name, api_key):
    """
    第一步：只找图书馆的入口，不需要直接找到列表页
    让 Playwright 去做具体的点击工作
    """
    url = "https://google.serper.dev/search"
    # 搜索策略：优先找图书馆官网，或者直接找数据库页
    queries = [
        f"{school_name} 图书馆 官网",
        f"{school_name} 图书馆 数据库",
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
    """表格提取逻辑 (保持不变，因为这是对的)"""
    db_list = []
    tables = soup.find_all('table')
    
    for table in tables:
        text_content = table.get_text()
        keywords = ["数据库", "资源", "题名", "已购", "订购", "中文", "外文"]
        # 如果表格里没有这些关键词，就跳过
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

def automated_browser_workflow(start_url):
    """
    【真正的自动化核心】
    1. 进入页面
    2. 如果当前页面没有表格，自动寻找“已购资源”、“电子资源”按钮并点击
    3. 提取数据
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36')
        page = context.new_page()
        
        print(f"正在访问: {start_url}")
        try:
            page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2) # 等待渲染
            
            # --- 智能跳转逻辑 ---
            # 检查当前页面有没有目标表格
            initial_content = page.content()
            initial_soup = BeautifulSoup(initial_content, 'html.parser')
            initial_data = extract_from_table(initial_soup)
            
            # 如果当前页面直接就有数据，太好了，直接返回
            if len(initial_data) > 10:
                print("直接在着陆页找到数据")
                browser.close()
                return initial_data

            # 如果没有，开始寻找入口链接并点击
            print("当前页面未发现表格，尝试点击导航...")
            
            # 常见的入口关键词，按优先级排序
            keywords = ["已购资源", "中文数据库", "电子资源", "数据库导航", "所有数据库", "订购资源"]
            
            found_click = False
            for kw in keywords:
                try:
                    # 寻找包含关键词的链接
                    # 使用 Playwright 的定位器，模糊匹配文本
                    link = page.get_by_text(kw, exact=False).first
                    if link.is_visible():
                        print(f"--> 点击跳转: {kw}")
                        link.click(timeout=3000)
                        page.wait_for_load_state("domcontentloaded", timeout=10000)
                        time.sleep(3) # 等待跳转后的表格渲染
                        found_click = True
                        break # 跳过一次后，通常就是目标页了
                except Exception as e:
                    continue # 没找到这个词，找下一个
            
            if not found_click:
                print("未找到明显的跳转链接，尝试在当前页硬解析")

            # --- 最终提取 ---
            final_content = page.content()
            browser.close()
            
            final_soup = BeautifulSoup(final_content, 'html.parser')
            final_data = extract_from_table(final_soup)
            
            # 兜底：如果表格提取还是空的，试着用列表方式提取
            if len(final_data) < 5:
                # 清理干扰项
                for tag in final_soup(['header', 'footer', 'nav', 'script', 'style']):
                    tag.decompose()
                clean_links = []
                for link in final_soup.find_all('a'):
                    txt = link.get_text(strip=True)
                    if 4 < len(txt) < 50:
                        clean_links.append(txt)
                return clean_links

            return final_data

        except Exception as e:
            print(f"Browser Error: {e}")
            browser.close()
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
        "提交", "部门", "版权", "所有", "导航", "服务", "概况"
    ]
    clean_list = []
    for item in raw_list:
        text = item.strip()
        if 2 < len(text) < 60 and not text.isdigit():
            if not any(junk in text for junk in blacklist):
                clean_list.append(text)
    return list(set(clean_list))

# --- 3. UI 界面 (回归简洁) ---
st.set_page_config(page_title="高校数据库自动统计", page_icon="🏫", layout="wide")

st.title("🏫 高校数据库全自动统计")
st.caption("输入校名 -> 自动进入图书馆 -> 自动寻找已购资源 -> 输出统计")

# 简单的输入区
col1, col2 = st.columns([3, 1])
with col1:
    school_input = st.text_input("请输入学校全称", placeholder="例如：西安科技大学", label_visibility="collapsed")
with col2:
    start_btn = st.button("开始自动化分析", type="primary", use_container_width=True)

api_key = get_api_key()

if start_btn:
    if not api_key:
        st.error("请在后台配置 SERPER_API_KEY")
        st.stop()
    
    if not school_input:
        st.warning("请输入学校名称")
        st.stop()

    status = st.status("🚀 正在启动自动化程序...", expanded=True)
    
    # 1. 搜索入口
    status.write(f"🔍 正在搜索 {school_input} 图书馆官网...")
    start_url = google_search_lib_url(school_input, api_key)
    
    if start_url:
        status.write(f"🌐 找到入口: {start_url}")
        status.write("🤖 正在模拟浏览器访问，寻找“已购资源”表格...")
        
        # 2. 自动化浏览 + 智能跳转
        raw_dbs = automated_browser_workflow(start_url)
        
        # 3. 数据清洗
        final_dbs = clean_data(raw_dbs)
        cn_dbs = sorted([d for d in final_dbs if is_chinese(d)])
        en_dbs = sorted([d for d in final_dbs if not is_chinese(d)])
        total = len(cn_dbs) + len(en_dbs)
        
        status.update(label="✅ 完成！", state="complete", expanded=False)
        
        # --- 结果展示 ---
        st.divider()
        st.markdown(f"### 📊 {school_input} 统计结果")
        st.caption(f"数据最终来源页: {start_url}") # 这里的URL可能是跳转前的，主要作参考
        
        if total == 0:
            st.error("⚠️ 未提取到有效数据。")
            st.info("可能有以下原因：\n1. 该学校官网必须校内VPN才能访问。\n2. 网页结构极其特殊，自动化点击未命中。")
        else:
            # 统计卡片
            c1, c2, c3 = st.columns(3)
            c1.metric("📚 总计资源", total)
            c2.metric("🇨🇳 中文数据库", len(cn_dbs))
            c3.metric("🌍 外文数据库", len(en_dbs))
            
            st.divider()
            
            # 双栏列表
            c_left, c_right = st.columns(2)
            with c_left:
                st.subheader(f"中文数据库 ({len(cn_dbs)})")
                if cn_dbs:
                    df = pd.DataFrame(cn_dbs, columns=["名称"])
                    df.index += 1
                    st.dataframe(df, use_container_width=True)
            
            with c_right:
                st.subheader(f"外文数据库 ({len(en_dbs)})")
                if en_dbs:
                    df = pd.DataFrame(en_dbs, columns=["名称"])
                    df.index += 1
                    st.dataframe(df, use_container_width=True)
            
    else:
        status.update(label="❌ 搜索失败", state="error")
        st.error("无法找到该学校图书馆官网，请检查校名是否正确。")