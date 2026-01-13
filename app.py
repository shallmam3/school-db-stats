import streamlit as st
import subprocess
import os

# --- 关键修复：云端自动安装 Playwright 浏览器 ---
# 这段代码会检查是否在云端，如果是，就自动下载浏览器
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    # 如果库都没装上，尝试强制安装（通常 requirements.txt 会搞定，这里是兜底）
    subprocess.check_call([os.sys.executable, "-m", "pip", "install", "playwright"])
    from playwright.sync_api import sync_playwright

# 每次启动时确保浏览器已安装
# 注意：这会增加一点启动时间，但在云端是必须的
subprocess.run(["playwright", "install", "chromium"])

# ------------------------------------------------
# 下面是你原本的代码...
from bs4 import BeautifulSoup
import pandas as pd
import time

def get_dynamic_page_content(url):
    """
    使用 Playwright 加载动态网页
    """
    with sync_playwright() as p:
        # 使用 chromium 浏览器
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            status_text = st.empty()
            status_text.text(f"正在模拟浏览器访问: {url} ...")
            
            page.goto(url, timeout=60000) # 增加超时时间到60秒
            
            # 等待网络空闲，表示加载完成
            page.wait_for_load_state("networkidle") 
            
            # 额外等待确保 JS 执行
            time.sleep(3)
            
            content = page.content()
            status_text.empty()
            return content
            
        except Exception as e:
            st.error(f"加载失败: {e}")
            return None
        finally:
            browser.close()

# ... (后面 is_chinese, analyze_html 和 UI 部分保持不变，直接复制你之前的即可)
# 为了方便，我把后面的 UI 部分也简略写在这里，你可以直接保留你之前的
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
        if 2 < len(text) < 50: 
            db_list.append(text)
    db_list = list(set(db_list))
    cn_dbs = [db for db in db_list if is_chinese(db)]
    other_dbs = [db for db in db_list if not is_chinese(db)]
    return cn_dbs, other_dbs

# --- UI ---
st.set_page_config(page_title="动态网页数据库抓取", page_icon="🕵️")
st.title("🕵️ 超星/动态网页抓取助手")

target_url = st.text_input("请输入网址：", value="http://wisdom.chaoxing.com/newwisdom/doordatabase/database.html?pageId=48038&wfwfid=1803&sw=")

if st.button("开始强力抓取"):
    if not target_url:
        st.warning("请先输入网址")
    else:
        with st.status("🚀 正在启动仿真浏览器...", expanded=True) as status:
            html_content = get_dynamic_page_content(target_url)
            if html_content:
                status.write("✅ 页面加载成功！正在解析...")
                cn_list, en_list = analyze_html(html_content)
                status.update(label="分析完成！", state="complete", expanded=False)
                
                col1, col2, col3 = st.columns(3)
                col1.metric("中文数据库", f"{len(cn_list)}")
                col2.metric("外文/其他", f"{len(en_list)}")
                col3.metric("总计", f"{len(cn_list) + len(en_list)}")
                
                tab1, tab2 = st.tabs(["📝 中文库清单", "🌍 外文库清单"])
                with tab1:
                    st.dataframe(pd.DataFrame(cn_list, columns=["名称"]), use_container_width=True)
                with tab2:
                    st.dataframe(pd.DataFrame(en_list, columns=["名称"]), use_container_width=True)