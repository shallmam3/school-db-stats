import streamlit as st
import subprocess
import os
import json
import requests
import re
from bs4 import BeautifulSoup
import pandas as pd

# --- 1. 环境与依赖 ---
# 既然是读文章，不需要笨重的 Playwright 了，普通的 requests 就够了，速度更快
if "playwright_installed" not in st.session_state:
    st.session_state.playwright_installed = True

# --- 2. 核心：主流数据库词典 (你可以随时补充) ---
# 这是我们在文章中“寻找”的目标
COMMON_DBS = {
    "CN": [
        "中国知网", "CNKI", "万方", "维普", "超星", "读秀", "龙源", 
        "人大复印", "CSCD", "CSSCI", "中华医学", "国研网", "EPS数据", 
        "新东方", "银符", "起点考试", "中科", "优阅", "书生之家"
    ],
    "EN": [
        "Web of Science", "WOS", "SCI", "SSCI", "EI", "Engineering Village", 
        "ScienceDirect", "Elsevier", "Springer", "Wiley", "IEEE", "IEL", 
        "Nature", "Science", "ACS", "RSC", "ProQuest", "EBSCO", "JSTOR", 
        "PubMed", "Embase", "Scopus", "Taylor", "Francis", "SAGE", 
        "Emerald", "ACM", "ASCE", "ASME", "LexisNexis", "Westlaw"
    ]
}

def get_api_key():
    try:
        return st.secrets["SERPER_API_KEY"]
    except:
        return None

def google_search_articles(school_name, api_key):
    """
    搜索策略转变：找文章、找指南、找概览
    """
    url = "https://google.serper.dev/search"
    queries = [
        f"{school_name} 图书馆 \"数字资源\" 导览",
        f"{school_name} 图书馆 \"已购数据库\" 一览",
        f"{school_name} 图书馆 新生入馆指南 资源介绍",
        f"site:mp.weixin.qq.com {school_name} 图书馆 数据库" # 专门搜微信推文
    ]
    
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json; charset=utf-8'}

    links = []
    for query in queries:
        try:
            payload = json.dumps({"q": query, "gl": "cn", "hl": "zh-cn"}, ensure_ascii=False).encode('utf-8')
            response = requests.post(url, headers=headers, data=payload, timeout=5)
            if response.status_code == 200:
                results = response.json()
                if 'organic' in results:
                    # 取前3个结果，增加命中率
                    for item in results['organic'][:3]:
                        links.append({
                            "title": item.get('title'),
                            "link": item.get('link'),
                            "snippet": item.get('snippet')
                        })
        except:
            continue
    
    # 去重
    seen = set()
    unique_links = []
    for l in links:
        if l['link'] not in seen:
            unique_links.append(l)
            seen.add(l['link'])
    return unique_links[:5] # 最多分析5篇

def analyze_page_content(url):
    """
    抓取文章内容并进行“词典匹配”
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = resp.apparent_encoding # 自动纠正编码
        text = BeautifulSoup(resp.text, 'html.parser').get_text()
        
        found_cn = set()
        found_en = set()
        
        # 1. 扫描中文库
        for db in COMMON_DBS["CN"]:
            # 简单的不区分大小写匹配
            if db.lower() in text.lower():
                found_cn.add(db)
                
        # 2. 扫描外文库
        for db in COMMON_DBS["EN"]:
            # 单词边界匹配防止误判 (例如搜 EI 不匹配 height)
            if re.search(r'\b' + re.escape(db) + r'\b', text, re.IGNORECASE) or db in text:
                found_en.add(db)
                
        return list(found_cn), list(found_en)
    except Exception as e:
        return [], []

# --- 3. UI 界面 ---
st.set_page_config(page_title="高校资源情报分析", page_icon="🕵️", layout="wide")

st.title("🕵️ 高校数据库资源情报分析")
st.caption("思路：通过搜索公开的“入馆指南”、“资源导览”或“新闻通告”，匹配主流数据库名单。")

with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input("SERPER_API_KEY", value=get_api_key() or "", type="password")
    
school_input = st.text_input("请输入学校全称", placeholder="例如：西安科技大学")
run_btn = st.button("开始侦察", type="primary")

if run_btn:
    if not api_key:
        st.error("请配置 SERPER_API_KEY")
        st.stop()
    if not school_input:
        st.warning("请输入校名")
        st.stop()

    status = st.status("🔍 正在全网搜索相关情报...", expanded=True)
    
    # 1. 搜索文章
    articles = google_search_articles(school_input, api_key)
    
    if not articles:
        status.update(label="❌ 未找到公开情报", state="error")
        st.error("未搜索到相关文章，该学校可能较少公开详细资源列表。")
    else:
        status.write(f"📄 找到 {len(articles)} 篇相关公开文档/文章，开始分析内容...")
        
        all_cn = set()
        all_en = set()
        valid_sources = []
        
        # 2. 逐篇分析
        progress_bar = status.progress(0)
        for i, article in enumerate(articles):
            status.write(f"正在阅读: [{article['title']}]...")
            cn, en = analyze_page_content(article['link'])
            
            if cn or en:
                all_cn.update(cn)
                all_en.update(en)
                valid_sources.append(article)
            
            progress_bar.progress((i + 1) / len(articles))
            
        status.update(label="✅ 分析完成！", state="complete", expanded=False)
        
        # --- 结果展示 ---
        st.divider()
        total = len(all_cn) + len(all_en)
        
        # 顶部 KPI
        c1, c2, c3 = st.columns(3)
        c1.metric("疑似已购资源", total, help="通过关键词匹配到的主流数据库数量")
        c2.metric("中文核心", len(all_cn))
        c3.metric("外文核心", len(all_en))
        
        st.info(f"💡 分析结论：根据公开信息，该校极大概率拥有以下资源。数据来源于对 {len(valid_sources)} 篇公开文章的文本分析。")

        # 详细列表
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🇨🇳 中文资源 (匹配命中)")
            if all_cn:
                # 转换成 DataFrame 显示更好看
                df_cn = pd.DataFrame(sorted(list(all_cn)), columns=["数据库名称"])
                st.dataframe(df_cn, use_container_width=True, hide_index=True)
            else:
                st.text("未检测到常见中文库")
                
        with col2:
            st.subheader("🌍 外文资源 (匹配命中)")
            if all_en:
                df_en = pd.DataFrame(sorted(list(all_en)), columns=["数据库名称"])
                st.dataframe(df_en, use_container_width=True, hide_index=True)
            else:
                st.text("未检测到常见外文库")

        st.divider()
        st.markdown("#### 🔗 证据来源 (点击查看原文)")
        for src in valid_sources:
            st.markdown(f"- [{src['title']}]({src['link']})")
            st.caption(f"摘要: {src['snippet']}")