"""Streamlit 全局样式（豆包风格：浅色、圆角卡片、柔和阴影）。"""
from __future__ import annotations

import streamlit as st

from app.ui_shortcuts import inject_shortcut_guard

DOUBAO_CSS = """
<style>
/* 页面底色 */
.stApp {
  background: linear-gradient(180deg, #f5f7fb 0%, #eef1f8 100%);
}
section.main .block-container {
  padding-top: 3.5rem;
  padding-bottom: 5rem;
  max-width: 1200px;
}
header[data-testid="stHeader"] {
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
}
.app-title-card {
  margin-top: 0.25rem;
  margin-bottom: 1rem;
}
/* 标题区 */
h1 {
  font-weight: 600 !important;
  letter-spacing: -0.02em;
  color: #1f2329 !important;
}
/* 卡片容器 */
.doubao-card {
  background: #ffffff;
  border-radius: 14px;
  padding: 1rem 1.15rem;
  margin-bottom: 0.75rem;
  box-shadow: 0 1px 2px rgba(31, 35, 41, 0.06),
              0 4px 12px rgba(31, 35, 41, 0.04);
  border: 1px solid rgba(31, 35, 41, 0.06);
}
.doubao-card h4 {
  margin: 0 0 0.5rem 0;
  font-size: 0.95rem;
  color: #1f2329;
}
.doubao-muted {
  color: #8f959e;
  font-size: 0.85rem;
}
.doubao-pass {
  color: #2ea043;
  font-weight: 600;
}
.doubao-fail {
  color: #e34d59;
  font-weight: 600;
}
.section-divider {
  border-top: 2px solid #e5e6eb;
  margin: 2rem 0 1rem 0;
  padding-top: 0.25rem;
}
/* 聊天主区域 */
.chat-panel {
  background: #ffffff;
  border-radius: 14px;
  border: 1px solid rgba(31, 35, 41, 0.08);
  padding: 0.25rem 0.5rem 0.5rem;
}
/* Tab 标签 */
.stTabs [data-baseweb="tab-list"] {
  gap: 6px;
  background: transparent;
}
.stTabs [data-baseweb="tab"] {
  background: #ffffff;
  border-radius: 10px 10px 0 0;
  border: 1px solid rgba(31, 35, 41, 0.08);
  padding: 0.4rem 1rem;
  color: #646a73;
}
.stTabs [aria-selected="true"] {
  background: #ffffff !important;
  color: #3370ff !important;
  font-weight: 600;
  border-bottom-color: #ffffff !important;
}
/* 主按钮 */
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #4d7cff 0%, #3370ff 100%);
  border: none;
  border-radius: 10px;
  font-weight: 500;
}
.stButton > button[kind="primary"]:hover {
  background: linear-gradient(135deg, #3d6cef 0%, #2860ef 100%);
}
/* 指标卡片 */
[data-testid="stMetric"] {
  background: #ffffff;
  padding: 0.65rem 1rem;
  border-radius: 12px;
  border: 1px solid rgba(31, 35, 41, 0.06);
  box-shadow: 0 1px 3px rgba(31, 35, 41, 0.04);
}
/* 底部聊天输入 */
[data-testid="stChatInput"] {
  background: #ffffff !important;
  border-top: 1px solid #d0d7de !important;
  box-shadow: 0 -4px 16px rgba(31, 35, 41, 0.08) !important;
  padding: 0.75rem 0 !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] input {
  background: #ffffff !important;
  border: 1px solid #d0d7de !important;
  border-radius: 12px !important;
}
[data-testid="stChatInput"] textarea:focus,
[data-testid="stChatInput"] input:focus {
  border-color: #3370ff !important;
  box-shadow: 0 0 0 2px rgba(51, 112, 255, 0.15) !important;
}
</style>
"""


def inject_doubao_theme() -> None:
    st.markdown(DOUBAO_CSS, unsafe_allow_html=True)
    inject_shortcut_guard()
