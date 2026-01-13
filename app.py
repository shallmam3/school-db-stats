import streamlit as st
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import time

# --- 核心逻辑 ---

def get_dynamic_page_content(url):
    """
    使用 Playwright 加载动态网页（针对超星/AJAX页面）
    """
    with sync_playwright() as p:
        # 启动一个浏览器（headless=True 表示不显示界面，速度更快）
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print(f"正在加载页面: {url}")
            page.goto(url, timeout=30000) # 30秒超时
            
            # 关键点：等待页面上的特定元素加载出来
            # 我们等待页面上出现看起来像链接或列表的东西
            # 如果你知道具体的 CSS 选择器最好，不知道的话等待网络空闲
            page.wait_for_load_state("networkidle") 
            
            # 为了保险，多等 2 秒让 JS 渲染完
            time.sleep(2)
            
            # 获取渲染后的完整 HTML
            content = page.content()
            return content
            
        except Exception as e:
            st.error(f"Playwright 加载失败: {e}")
            return None
        finally:
            browser.close()

def is_chinese(string):
    for char in string:
        if '\u4e00' <= char <= '\u9fa5':
            return True
    return False

def analyze_html(html_content):
    """解析 HTML 内容"""
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
        # 稍微放宽过滤条件
        if 2 < len(text) < 50: 
            db_list.append(text)
    
    db_list = list(set(db_list))
    
    cn_dbs = [db for db in db_list if is_chinese(db)]
    other_dbs = [db for db in db_list if not is_chinese(db)]
            
    return cn_dbs, other_dbs

# --- UI 界面 ---

st.set_page_config(page_title="动态网页数据库抓取", page_icon="🕵️")

st.title("🕵️ 超星/动态网页抓取助手")
st.markdown("专门解决“浏览器能看到，程序搜不到”的问题。")

target_url = st.text_input("请输入网址：", value="http://wisdom.chaoxing.com/newwisdom/doordatabase/database.html?pageId=48038&wfwfid=1803&sw=")

if st.button("开始强力抓取"):
    if not target_url:
        st.warning("请先输入网址")
    else:
        with st.status("🚀 正在启动仿真浏览器...", expanded=True) as status:
            
            # 1. 获取动态内容
            html_content = get_dynamic_page_content(target_url)
            
            if html_content:
                status.write("✅ 页面加载成功！正在解析数据...")
                
                # 2. 解析
                cn_list, en_list = analyze_html(html_content)
                
                status.update(label="分析完成！", state="complete", expanded=False)
                
                # 3. 展示结果
                st.divider()
                st.success(f"📊 抓取结果统计")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("中文数据库", f"{len(cn_list)}")
                col2.metric("外文/其他", f"{len(en_list)}")
                col3.metric("总计", f"{len(cn_list) + len(en_list)}")
                
                tab1, tab2 = st.tabs(["📝 中文库清单", "🌍 外文库清单"])
                with tab1:
                    st.dataframe(pd.DataFrame(cn_list, columns=["名称"]), use_container_width=True)
                with tab2:
                    st.dataframe(pd.DataFrame(en_list, columns=["名称"]), use_container_width=True)
            else:
                status.update(label="抓取失败", state="error")
                st.error("未能获取页面内容，可能是因为网页有反爬虫验证或加载超时。")