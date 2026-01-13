import streamlit as st
import subprocess
import os
import json
import requests
import time
from bs4 import BeautifulSoup
import pandas as pd

# --- 1. 环境自检与初始化 (Playwright) ---
if "playwright_installed" not in st.session_state:
    # 检查是否安装了浏览器内核
    if not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")):
        with st.spinner("正在初始化云端浏览器组件... (首次运行约需1分钟)"):
            subprocess.run(["playwright", "install", "chromium"])
    st.session_state.playwright_installed = True

# 尝试导入，如果失败则说明requirements.txt没生效，但通常这时已经生效了
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    st.error("严重错误：未找到 playwright 库。请检查 requirements.txt 是否包含 'playwright'")
    st.stop()

# --- 2. 核心功能函数 ---

def get_api_key():
    """从后台读取 API Key"""
    try:
        return st.secrets["SERPER_API_KEY"]
    except Exception:
        # 如果后台没配，允许临时输入（方便调试）
        return None

def google_search_url(school_name, api_key):
    """【大脑】利用 Google 搜索找到目标网址"""
    url = "https://google.serper.dev/search"
    queries = [
        f"{school_name} 图书馆 数据库 列表",
        f"{school_name} 图书馆 试用数据库",
        f"{school_name} library database list"
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
                    # 返回找到的第一个链接
                    found_link = results['organic'][0]['link']
                    return found_link
        except Exception as e:
            print(f"搜索报错: {e}")
            continue
    return None

def get_dynamic_page_content(url):
    """【四肢】利用 Playwright 渲染动态网页"""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            # 伪装成 Mac 电脑上的 Chrome，防止被识别为爬虫
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            # 访问页面
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # 智能等待：强制等待几秒让 JS 飞一会儿
            time.sleep(5)
            
            content = page.content()
            browser.close()
            return content
        except Exception as e:
            print(f"Playwright 抓取失败: {e}")
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
    for tag in soup(['header', 'footer', 'nav', 'script', 'style', 'noscript']):
        tag.decompose()
    
    links = soup.find_all('a')
    db_list = []
    for link in links:
        text = link.get_text(strip=True)
        if 2 < len(text) < 60: 
            db_list.append(text)
    
    db_list = list(set(db_list))
    cn_dbs = [db for db in db_list if is_chinese(db)]
    other_dbs = [db for db in db_list if not is_chinese(db)]
    return cn_dbs, other_dbs

# --- 3. UI 界面 ---

st.set_page_config(page_title="高校数据库自动统计", page_icon="🏫", layout="centered")

st.title("🏫 高校数据库全自动统计")
st.caption("输入校名 -> 自动搜索网址 -> 自动渲染动态页面 -> 自动统计")

# 获取 Key
api_key = get_api_key()

# 输入区
col1, col2 = st.columns([3, 1])
with col1:
    school_input = st.text_input("请输入学校全称", placeholder="例如：陕西师范大学", label_visibility="collapsed")
with col2:
    start_btn = st.button("开始分析", type="primary", use_container_width=True)

# 状态区
status_box = st.status("等待指令...", expanded=False)

if start_btn:
    if not school_input:
        st.toast("请输入校名！")
    elif not api_key:
        st.error("❌ 未检测到 API Key。请在 Streamlit Cloud 后台 Settings -> Secrets 中配置 SERPER_API_KEY。")
    else:
        # 第一步：搜索
        status_box.update(label=f"🔍 正在全网搜索【{school_input}】的数据库列表...", state="running", expanded=True)
        target_url = google_search_url(school_input, api_key)
        
        if target_url:
            status_box.write(f"✅ 找到目标地址: {target_url}")
            
            # 第二步：抓取
            status_box.update(label="🚀 正在启动云端浏览器加载页面 (可能需要十几秒)...", state="running")
            html_content = get_dynamic_page_content(target_url)
            
            if html_content:
                # 第三步：分析
                status_box.write("✅ 页面加载成功，正在解析...")
                cn_list, en_list = analyze_html(html_content)
                status_box.update(label="分析完成！", state="complete", expanded=False)
                
                # 第四步：展示
                total = len(cn_list) + len(en_list)
                st.divider()
                st.markdown(f"### 📊 {school_input}")
                st.caption(f"数据来源: {target_url}")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("总计", total)
                m2.metric("中文数据库", len(cn_list))
                m3.metric("外文数据库", len(en_list))
                
                with st.expander("查看详细清单"):
                    tab1, tab2 = st.tabs(["中文库", "外文库"])
                    with tab1:
                        st.dataframe(pd.DataFrame(cn_list, columns=["名称"]), use_container_width=True, hide_index=True)
                    with tab2:
                        st.dataframe(pd.DataFrame(en_list, columns=["名称"]), use_container_width=True, hide_index=True)
            else:
                status_box.update(label="❌ 浏览器加载页面失败", state="error")
                st.error("网页加载超时或被反爬虫拦截，无法获取内容。")
        else:
            status_box.update(label="❌ 自动搜索失败", state="error")
            st.warning("Google 未能找到该学校明确的数据库列表页面。")
            manual_url = st.text_input("请手动粘贴网址尝试：")