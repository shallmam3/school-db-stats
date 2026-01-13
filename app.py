import streamlit as st
import subprocess
import os
import json
import requests
import time
import re
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
    # 优化搜索词，直接找“已购资源”
    queries = [
        f"{school_name} 图书馆 已购资源 列表",
        f"{school_name} 图书馆 数据库导航",
        f"{school_name} 图书馆 电子资源"
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
    """
    【核心升级】专门识别“表格”结构 (Target: 红框内的内容)
    只有在表格里的内容才会被提取，彻底屏蔽侧边栏干扰。
    """
    db_list = []
    
    # 找到所有的表格
    tables = soup.find_all('table')
    
    for table in tables:
        # 检查表头，确认是不是数据库列表
        # 只要表格文字里包含这些关键词，就认为是目标表格
        text_content = table.get_text()
        keywords = ["数据库", "资源名称", "题名", "已购", "订购", "中文", "外文"]
        
        # 计算匹配到的关键词数量
        match_count = sum(1 for k in keywords if k in text_content)
        
        # 如果关键词太少，说明这可能只是个排版表格，跳过
        if match_count < 2:
            continue
            
        # --- 提取表格内容 ---
        # 遍历所有行
        rows = table.find_all('tr')
        for row in rows:
            # 遍历所有单元格
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                # 提取链接文本
                links = cell.find_all('a')
                for link in links:
                    text = link.get_text(strip=True)
                    if 2 < len(text) < 60:
                        db_list.append(text)
                
                # 如果没有链接，有时候是纯文本(但较少见，通常数据库都是链接)
                if not links:
                     text = cell.get_text(strip=True)
                     if 2 < len(text) < 60 and not text.isdigit():
                         db_list.append(text)

    return db_list

def smart_crawl_and_extract(url):
    """
    【智能探路者】
    1. 加载页面
    2. 如果当前页面不像列表，尝试点击“已购资源”等按钮跳转
    3. 渲染最终页面并提取
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36')
            page = context.new_page()
            
            # 1. 访问初始页面
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3) # 等待首屏加载
            
            # --- 智能跳转逻辑 (Deep Navigation) ---
            # 检查当前页面是否已经是列表页（有没有“中文数据库”、“已购”等字样）
            content = page.content()
            if "中文数据库" not in content and "已购" not in content:
                # 如果当前页不像列表页，尝试寻找“入口”按钮并点击
                # 模糊匹配链接文字
                potential_links = page.get_by_role("link").all()
                target_keywords = ["已购资源", "数据库导航", "中文数据库", "所有数据库", "订购资源"]
                
                for link in potential_links:
                    try:
                        text = link.text_content()
                        if any(kw in text for kw in target_keywords):
                            print(f"🕵️ 发现潜在入口: {text}，正在跳转...")
                            # 找到入口，点击并等待加载
                            with page.expect_navigation(timeout=15000):
                                link.click()
                            time.sleep(5) # 等待新页面加载
                            break # 只跳一次
                    except:
                        pass

            # 2. 获取最终页面内容
            final_content = page.content()
            browser.close()
            
            # --- 解析阶段 ---
            soup = BeautifulSoup(final_content, 'html.parser')
            
            # 策略 A: 优先尝试从表格(Table)提取 (最精准，对应你的截图)
            db_list = extract_from_table(soup)
            
            # 策略 B: 如果没找到表格，回退到之前的智能区域法 (兜底)
            if len(db_list) < 5:
                # (这里复用之前的逻辑，作为备用)
                # 清理干扰
                for tag in soup(['header', 'footer', 'nav', 'script', 'style', 'iframe', 'form']):
                    tag.decompose()
                
                # 寻找最密集的区域
                all_links = soup.find_all('a')
                parents = []
                for link in all_links:
                    if 2 < len(link.get_text(strip=True)) < 60:
                        parent = link.find_parent(['ul', 'div', 'tbody', 'section'])
                        if parent: parents.append(parent)
                
                if parents:
                    top_parent, count = Counter(parents).most_common(1)[0]
                    if count > 5:
                        for link in top_parent.find_all('a'):
                            db_list.append(link.get_text(strip=True))

            return db_list
            
        except Exception as e:
            print(f"Error: {e}")
            return []

def is_chinese(string):
    for char in string:
        if '\u4e00' <= char <= '\u9fa5': return True
    return False

def clean_data(raw_list):
    """最后一道清洗工序"""
    blacklist = [
        "首页", "登录", "注册", "更多", "查看", "订购", "试用", "简介", "指南", 
        "详细", "访问", "校外", "咨询", "反馈", "点击", "下载", "English",
        "序号", "状态", "类型", "名称", "数据库名称", "操作", "来源" # 表头词也要过滤
    ]
    clean_list = []
    for item in raw_list:
        text = item.strip()
        if 2 < len(text) < 60 and not text.isdigit():
            if not any(junk in text for junk in blacklist):
                clean_list.append(text)
    return list(set(clean_list))

# --- 3. UI 界面 ---
st.set_page_config(page_title="高校数据库统计Pro", page_icon="🏫", layout="centered")
st.title("🏫 高校数据库全自动统计 (Pro版)")
st.caption("智能识别表格结构 | 自动跳转二级页面")

api_key = get_api_key()
school_input = st.text_input("请输入学校全称", placeholder="例如：西安科技大学")
start_btn = st.button("开始深度分析", type="primary")

status = st.status("准备就绪", expanded=False)

if start_btn:
    if not api_key:
        st.error("请配置 SERPER_API_KEY")
    elif not school_input:
        st.warning("请输入校名")
    else:
        status.update(label="🔍 正在寻找数据库入口...", state="running", expanded=True)
        url = google_search_url(school_input, api_key)
        
        if url:
            status.write(f"🌐 初始入口: {url}")
            status.write("🕵️ 正在启动浏览器，尝试寻找表格数据 (包含自动跳转)...")
            
            # 执行智能抓取
            raw_dbs = smart_crawl_and_extract(url)
            
            # 清洗
            final_dbs = clean_data(raw_dbs)
            
            cn_dbs = [d for d in final_dbs if is_chinese(d)]
            en_dbs = [d for d in final_dbs if not is_chinese(d)]
            total = len(cn_dbs) + len(en_dbs)
            
            status.update(label="✅ 分析完成！", state="complete", expanded=False)
            
            st.divider()
            st.markdown(f"### 📊 {school_input} 分析报告")
            st.caption(f"数据来源: {url}")
            
            if total == 0:
                st.error("未提取到有效数据。可能原因：页面需要校内网(VPN)才能看到表格，或者反爬虫非常严格。")
            else:
                m1, m2, m3 = st.columns(3)
                m1.metric("总计", total)
                m2.metric("中文库", len(cn_dbs))
                m3.metric("外文库", len(en_dbs))
                
                with st.expander("📄 查看详细清单 (已剔除侧边栏干扰)", expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.dataframe(pd.DataFrame(cn_dbs, columns=["中文数据库"]), use_container_width=True)
                    with c2:
                        st.dataframe(pd.DataFrame(en_dbs, columns=["外文数据库"]), use_container_width=True)
        else:
            status.update(label="❌ 搜索失败", state="error")
            st.error("未找到相关网页。")