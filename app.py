import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json

# --- 核心逻辑 ---

def google_search_url(school_name, api_key):
    """
    使用 Serper API (Google) 搜索，强制处理中文编码
    """
    url = "https://google.serper.dev/search"
    
    # 策略：尝试两个不同的搜索词，提高命中率
    queries = [
        f"{school_name} 图书馆 数据库 列表",  # 精准搜索
        f"{school_name} 图书馆 试用数据库",    # 备用搜索
    ]
    
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json; charset=utf-8' # 显式声明 UTF-8
    }

    for query in queries:
        try:
            print(f"正在尝试搜索: {query}")
            # 关键修复：使用 json.dumps 并编码为 utf-8 bytes，防止 latin-1 报错
            payload = json.dumps({
                "q": query,
                "gl": "cn",
                "hl": "zh-cn"
            }, ensure_ascii=False).encode('utf-8')

            response = requests.post(url, headers=headers, data=payload, timeout=10)
            
            if response.status_code == 200:
                results = response.json()
                # 优先找 organic (自然搜索结果)
                if 'organic' in results and len(results['organic']) > 0:
                    top_link = results['organic'][0]['link']
                    return top_link
            else:
                print(f"API 状态码错误: {response.status_code}")
                
        except Exception as e:
            print(f"搜索过程报错: {e}")
            continue # 换下一个词试试
            
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
            # 智能过滤：保留长度适中的链接文本
            if 3 < len(text) < 50: 
                db_list.append(text)
        
        # 去重
        db_list = list(set(db_list))
        
        cn_dbs = [db for db in db_list if is_chinese(db)]
        other_dbs = [db for db in db_list if not is_chinese(db)]
                
        return cn_dbs, other_dbs

    except Exception as e:
        st.error(f"无法读取该学校页面，原因: {e}")
        return None, None

# --- UI 界面 ---

st.set_page_config(page_title="高校数据库智能统计", page_icon="🕵️")

st.title("🕵️ 高校数据库全自动统计")
st.markdown("集成 **Google Search API**，自动寻找数据库列表。")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input("请输入 Serper API Key", type="password")
    st.markdown("[👉 点击获取免费 Key](https://serper.dev/)")
    st.divider()
    st.caption("如果没有 Key，或者自动搜索失败，你依然可以在右侧手动输入网址。")

school_input = st.text_input("请输入学校全称（例如：陕西师范大学）")

# 初始化 session state 用于存储找到的 URL
if 'target_url' not in st.session_state:
    st.session_state.target_url = ""

# 两个按钮逻辑
col_btn1, col_btn2 = st.columns([1, 2])
with col_btn1:
    auto_search = st.button("🚀 开始全自动分析", type="primary")

# --- 主逻辑 ---

# 1. 如果点击了自动搜索
if auto_search:
    if not api_key:
        st.error("请先在左侧侧边栏填入 API Key！")
    elif not school_input:
        st.warning("请先输入学校名称")
    else:
        with st.status("🤖 正在指挥 Google 搜索...", expanded=True) as status:
            found_url = google_search_url(school_input, api_key)
            
            if found_url:
                status.update(label=f"✅ 成功找到地址: {found_url}", state="complete", expanded=False)
                st.session_state.target_url = found_url # 存入缓存
            else:
                status.update(label="⚠️ 自动搜索未命中", state="error", expanded=True)
                st.warning("Google 暂时没找到该学校的数据库列表页，请手动尝试。")

# 2. 始终显示的手动输入框 (作为兜底)
st.divider()
st.markdown("##### 🔗 目标网址确认")
user_url = st.text_input(
    "如果上方自动搜索失败，请手动粘贴该学校【数据库列表】网址：", 
    value=st.session_state.target_url
)

# 3. 如果有网址了，就进行分析
if user_url:
    if st.button("开始抓取数据"):
        with st.spinner(f"正在读取网页: {user_url}"):
            cn_list, en_list = analyze_page(user_url)
            
            if cn_list is not None:
                st.success(f"📊 分析完成！共发现 {len(cn_list) + len(en_list)} 个数据库")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("中文数据库", f"{len(cn_list)}")
                col2.metric("外文/其他", f"{len(en_list)}")
                col3.metric("总计", f"{len(cn_list) + len(en_list)}")
                
                tab1, tab2 = st.tabs(["📝 中文库清单", "🌍 外文库清单"])
                with tab1:
                    st.dataframe(pd.DataFrame(cn_list, columns=["数据库名称"]), use_container_width=True)
                with tab2:
                    st.dataframe(pd.DataFrame(en_list, columns=["数据库名称"]), use_container_width=True)