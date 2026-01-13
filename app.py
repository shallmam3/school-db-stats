import streamlit as st
import subprocess
import os

# --- 启动检查与配置 ---
# 确保浏览器内核已下载
if "playwright_installed" not in st.session_state:
    with st.spinner("正在初始化浏览器组件... (首次运行需约1分钟)"):
        subprocess.run(["playwright", "install", "chromium"])
        st.session_state.playwright_installed = True

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import time

# --- 核心逻辑 ---

def get_dynamic_page_content(url):
    """
    使用 Playwright 加载动态网页
    """
    with sync_playwright() as p:
        try:
            # 启动 chromium 浏览器
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            status_text = st.empty()
            status_text.caption(f"🔄 正在模拟访问: {url} ...")
            
            # 访问页面
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # 智能等待：等待页面高度变化或者网络空闲
            # 这里强制等待几秒，让 JS 执行
            time.sleep(5)
            
            # 获取完整渲染后的 HTML
            content = page.content()
            
            status_text.empty()
            browser.close()
            return content
            
        except Exception as e:
            st.error(f"浏览器加载出错: {e}")
            return None

def is_chinese(string):
    for char in string:
        if '\u4e00' <= char <= '\u9fa5':
            return True
    return False

def analyze_html(html_content):
    if not html_content:
        return [], []
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 清理干扰项
    for tag in soup(['header', 'footer', 'nav', 'script', 'style', 'noscript']):
        tag.decompose()
    
    links = soup.find_all('a')
    db_list = []
    
    for link in links:
        text = link.get_text(strip=True)
        if 2 < len(text) < 50: 
            db_list.append(text)
    
    db_list = list(set(db_list))
    
    cn_dbs = [db for db in db_list if is_chinese(db)]
    other_dbs = [db for db in db_list if not is_chinese(db)]
            
    return cn_dbs, other_dbs

# --- UI 界面 ---
st.set_page_config(page_title="动态网页数据库抓取", page_icon="🕵️", layout="centered")

st.markdown("### 🕵️ 超星/动态网页抓取助手")
st.caption("基于 Playwright 仿真浏览器技术")

target_url = st.text_input("目标网址", value="http://wisdom.chaoxing.com/newwisdom/doordatabase/database.html?pageId=48038&wfwfid=1803&sw=")

if st.button("开始强力抓取", type="primary"):
    if not target_url:
        st.warning("请先输入网址")
    else:
        with st.status("🚀 正在启动云端浏览器...", expanded=True) as status:
            
            html_content = get_dynamic_page_content(target_url)
            
            if html_content:
                status.write("✅ 页面加载成功！正在解析数据...")
                cn_list, en_list = analyze_html(html_content)
                status.update(label="分析完成！", state="complete", expanded=False)
                
                # 结果展示
                st.divider()
                m1, m2, m3 = st.columns(3)
                m1.metric("总计", len(cn_list) + len(en_list))
                m2.metric("中文", len(cn_list))
                m3.metric("外文", len(en_list))
                
                tab1, tab2 = st.tabs(["📝 中文库清单", "🌍 外文库清单"])
                with tab1:
                    st.dataframe(pd.DataFrame(cn_list, columns=["名称"]), use_container_width=True, hide_index=True)
                with tab2:
                    st.dataframe(pd.DataFrame(en_list, columns=["名称"]), use_container_width=True, hide_index=True)
            else:
                status.update(label="抓取失败", state="error")