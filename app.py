import time
import pandas as pd
import requests
import streamlit as st
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

st.set_page_config(
    page_title="AI物販リサーチ Pro",
    page_icon="💰",
    layout="wide",
)

st.title("💰 AI物販リサーチ Pro")
st.caption("Yahoo!ショッピングの販売情報とNETSEAの取引可能商品をJANで突合し、利益機会を優先順位付けします。")

# ============================================================
# Session State
# ============================================================
DEFAULTS = {
    "search_results": None,
    "searched_query": "",
    "netsea_suppliers": [],
    "netsea_auto_results": [],
    "netsea_scan_status": [],
    "supplier_last_loaded": 0.0,
    "news_radar_rows": [],
    "news_radar_query_used": "",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# Helpers
# ============================================================
def safe_float(value, default=None):
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_jan(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def extract_netsea_blocks(payload):
    blocks = []
    if isinstance(payload, list):
        blocks = [x for x in payload if isinstance(x, dict)]
    elif isinstance(payload, dict):
        blocks = [payload]
    return blocks


def load_all_netsea_suppliers(force=False, max_pages=50):
    """承認済みサプライヤーをページングして取得。"""
    if not force and st.session_state.netsea_suppliers:
        return st.session_state.netsea_suppliers

    token = st.secrets["NETSEA_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://api.netsea.jp/buyer/v1/suppliers"

    suppliers = []
    seen_ids = set()
    next_supplier_id = None

    for _ in range(max_pages):
        params = {}
        if next_supplier_id:
            params["next_supplier_id"] = str(next_supplier_id)

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        blocks = extract_netsea_blocks(response.json())

        page_added = 0
        next_value = None

        for block in blocks:
            data = block.get("data", [])
            if isinstance(data, list):
                for supplier in data:
                    if not isinstance(supplier, dict):
                        continue
