import streamlit as st
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import pandas as pd

# --- 核心逻辑 ---

def search_library_url(school_name):
    """尝试自动搜索，增加重试机制"""
    query = f"{school_name} 图书馆 数据库 列表"
    print(f"正在搜索: {query}")
    try:
        # 尝试搜索，有些云服务器会被屏蔽，导致这里返回空
        results = DDGS().text(query, max_results=3)
        if results:
            return results[0]['href']
    except Exception as e:
        print(f"自动搜索出错: {e}")
    return None

def is_chinese(string):
    """判断是否包含中文"""
    for char in string:
        if '\u4e00' <= char <= '\u9fa5':
            return True
    return False

def analyze_page(url):
    """抓取并分析"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser') # 改回 html.parser 兼容性更好

        # 简单的清理和提取
        for tag in soup(['header', 'footer', 'nav', 'script', 'style']):
            tag.decompose()
        
        links = soup.find_all('a')
        db_list = []
        
        for link in links:
            text = link.get_text(strip=True)
            # 稍微放宽过滤条件
            if len(text) > 2 and len(text) < 60: 
                db_list.append(text)
        
        db_list = list(set(db_list))
        
        cn_dbs = [db for db in db_list if is_chinese(db)]
        other_dbs = [db for db in db_list if not is_chinese(db)]
                
        return cn_dbs, other_dbs

    except Exception as e:
        st.error(f"网页抓取详情报错: {e}")
        return None, None

# --- UI 界面 ---

st.set_page_config(page_title="高校数据库统计助手", page_icon="📚")

st.title("📚 高校图书馆数据库统计")
st.markdown("由于云端服务器IP限制，**自动搜索**可能会失败。如果失败，请手动粘贴网址。")

school_input = st.text_input("请输入学校全称（例如：陕西师范大学）")

if st.button("开始分析"):
    if not school_input:
        st.warning("请先输入学校名称")
    else:
        target_url = None
        
        # 1. 先尝试自动搜索
        with st.status("🔍 正在尝试自动搜索...", expanded=True) as status:
            target_url = search_library_url(school_input)
            
            if target_url:
                status.update(label=f"✅ 已找到地址: {target_url}", state="complete", expanded=False)
            else:
                status.update(label="⚠️ 自动搜索被拦截 (这是正常现象)", state="error", expanded=True)
                st.info("💡 云端服务器访问搜索接口受限。请手动在下方输入网址。")

        # 2. 如果自动搜索失败，显示手动输入框（或者直接使用手动输入的逻辑）
        if not target_url:
            target_url = st.text_input("👇 请手动粘贴该学校【数据库列表页】的网址：", 
                                     placeholder="https://lib.snnu.edu.cn/...")

        # 3. 只要有了 URL (不管是自动搜的还是手填的)，就开始分析
        if target_url:
            st.divider()
            with st.spinner(f"正在读取网页: {target_url}"):
                cn_list, en_list = analyze_page(target_url)
                
                if cn_list is not None:
                    # 展示结果
                    col1, col2, col3 = st.columns(3)
                    col1.metric("中文数据库", f"{len(cn_list)}")
                    col2.metric("外文/其他", f"{len(en_list)}")
                    col3.metric("总计", f"{len(cn_list) + len(en_list)}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.dataframe(pd.DataFrame(cn_list, columns=["中文库名"]), use_container_width=True)
                    with c2:
                        st.dataframe(pd.DataFrame(en_list, columns=["外文库名"]), use_container_width=True)