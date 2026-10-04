import time
import pandas as pd
import requests
import streamlit as st

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
                    supplier_id = supplier.get("id")
                    if supplier_id is None or supplier_id in seen_ids:
                        continue
                    seen_ids.add(supplier_id)
                    suppliers.append(supplier)
                    page_added += 1

            if block.get("next_supplier_id") not in (None, "", 0, "0"):
                next_value = block.get("next_supplier_id")

        if not next_value or page_added == 0:
            break
        if str(next_value) == str(next_supplier_id):
            break
        next_supplier_id = next_value

    st.session_state.netsea_suppliers = suppliers
    st.session_state.supplier_last_loaded = time.time()
    return suppliers


def extract_netsea_items(payload):
    items = []
    for block in extract_netsea_blocks(payload):
        data = block.get("data", [])
        if isinstance(data, list):
            items.extend([x for x in data if isinstance(x, dict)])
    return items


def extract_set_rows(item):
    sets = item.get("set", [])
    if isinstance(sets, dict):
        sets = [sets]
    if not isinstance(sets, list):
        sets = []
    return [x for x in sets if isinstance(x, dict)]


def search_netsea_jan(jan_code, suppliers, max_suppliers, delay_sec=0.12):
    """JANを1社ずつNETSEAへ送り、該当商品の仕入れ候補を取得。"""
    token = st.secrets["NETSEA_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://api.netsea.jp/buyer/v1/items"

    found = []
    suppliers_to_scan = suppliers[: int(max_suppliers)]

    for supplier in suppliers_to_scan:
        supplier_id = supplier.get("id")
        if not supplier_id:
            continue

        payload = {
            "supplier_ids": str(supplier_id),
            "jan_code": jan_code,
        }

        # 429などに軽くリトライ
        response = None
        last_error = None
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, data=payload, timeout=30)
                if response.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
                else:
                    raise last_error

        if response is None:
            continue

        for item in extract_netsea_items(response.json()):
            for product_set in extract_set_rows(item):
                price = safe_float(product_set.get("price"))
                if price is None or price <= 0:
                    continue

                found.append({
                    "JANコード": jan_code,
                    "サプライヤー": supplier.get("corp_name", ""),
                    "サプライヤーID": supplier_id,
                    "商品名": item.get("product_name", ""),
                    "仕入れ価格": price,
                    "NETSEA商品URL": item.get("product_url", ""),
                })

        if delay_sec > 0:
            time.sleep(delay_sec)

    return found


def build_profit_row(yahoo_row, source_row, fee_rate, shipping, target_profit):
    selling_price = safe_float(yahoo_row.get("販売価格"), 0) or 0
    source_price = safe_float(source_row.get("仕入れ価格"), 0) or 0
    review_count = int(safe_float(yahoo_row.get("レビュー数"), 0) or 0)
    fee = selling_price * fee_rate / 100
    profit = selling_price - source_price - fee - shipping
    margin = profit / selling_price * 100 if selling_price else 0
    roi = profit / source_price * 100 if source_price else 0

    max_purchase_price = selling_price - fee - shipping - target_profit
    demand_score = min(100, review_count / 10)
    margin_score = max(0, min(100, margin * 4))
    roi_score = max(0, min(100, roi))
    profit_score = max(0, min(100, profit / max(1, target_profit) * 100))

    opportunity_score = (
        profit_score * 0.45
        + roi_score * 0.25
        + margin_score * 0.20
        + demand_score * 0.10
    )

    if profit >= target_profit and roi >= 30 and margin >= 15:
        judgment = "🟢 仕入れ候補"
    elif profit > 0:
        judgment = "🟡 利益あり"
    else:
        judgment = "🔴 見送り"

    return {
        "Yahoo商品名": yahoo_row.get("商品名", ""),
        "JANコード": clean_jan(yahoo_row.get("JANコード")),
        "販売価格": selling_price,
        "レビュー数": review_count,
        "仕入れ価格": source_price,
        "仕入れ上限価格": max_purchase_price,
        "利益": profit,
        "利益率": margin,
        "ROI": roi,
        "総合スコア": opportunity_score,
        "判定": judgment,
        "サプライヤー": source_row.get("サプライヤー", ""),
        "サプライヤーID": source_row.get("サプライヤーID", ""),
        "NETSEA商品名": source_row.get("商品名", ""),
        "NETSEA商品URL": source_row.get("NETSEA商品URL", ""),
        "Yahoo商品URL": yahoo_row.get("商品URL", ""),
    }


def run_profit_scan(yahoo_df, suppliers, product_limit, supplier_limit, fee_rate, shipping, target_profit):
    """利益余地の大きいJANからNETSEAを掘る。"""
    working = yahoo_df.copy()
    working["JANコード"] = working["JANコード"].map(clean_jan)
    working = working[working["JANコード"].ne("")].copy()

    if working.empty:
        return [], []

    # 目標利益を残すために仕入れてよい上限価格を、まずYahoo価格から算出。
    working["販売手数料見込"] = working["販売価格"].astype(float) * fee_rate / 100
    working["仕入れ上限価格"] = (
        working["販売価格"].astype(float)
        - working["販売手数料見込"]
        - shipping
        - target_profit
    )
    working["需要指数"] = working["レビュー数"].astype(float).clip(lower=0).pow(0.5)
    working["探索優先度"] = (
        working["仕入れ上限価格"].clip(lower=0) * 0.75
        + working["需要指数"] * 100 * 0.25
    )

    candidates = (
        working.sort_values(["探索優先度", "レビュー数"], ascending=False)
        .drop_duplicates("JANコード")
        .head(int(product_limit))
        .copy()
    )

    all_found = []
    status_rows = []
    total_jobs = len(candidates) * min(int(supplier_limit), len(suppliers))
    completed = 0

    progress = st.progress(0.0)
    status_text = st.empty()

    try:
        for _, yahoo_row in candidates.iterrows():
            jan = clean_jan(yahoo_row["JANコード"])
            status_text.write(f"🔗 NETSEA照合中：{yahoo_row['商品名']} / JAN {jan}")
            found = []
            error_text = ""

            try:
                found = search_netsea_jan(
                    jan,
                    suppliers,
                    max_suppliers=int(supplier_limit),
                )
            except Exception as exc:
                error_text = str(exc)

            if found:
                for source in found:
                    all_found.append(
                        build_profit_row(
                            yahoo_row,
                            source,
                            fee_rate,
                            shipping,
                            target_profit,
                        )
                    )
                status_rows.append({
                    "商品名": yahoo_row["商品名"],
                    "JANコード": jan,
                    "検索サプライヤー数": min(int(supplier_limit), len(suppliers)),
                    "NETSEA一致": len(found),
                    "状態": "🟢 一致あり",
                    "エラー": error_text,
                })
            else:
                status_rows.append({
                    "商品名": yahoo_row["商品名"],
                    "JANコード": jan,
                    "検索サプライヤー数": min(int(supplier_limit), len(suppliers)),
                    "NETSEA一致": 0,
                    "状態": "🔴 一致なし" if not error_text else "⚠️ エラー",
                    "エラー": error_text,
                })

            completed += min(int(supplier_limit), len(suppliers))
            progress.progress(min(1.0, completed / max(1, total_jobs)))
    finally:
        status_text.empty()
        progress.empty()

    # 同じJANで複数サプライヤーが見つかった場合は、最安仕入れを主候補にする
    all_found.sort(key=lambda x: (x["JANコード"], x["仕入れ価格"]))
    return all_found, status_rows


# ============================================================
# Sidebar
# ============================================================
st.sidebar.header("⚙️ 利益判定設定")

fee_rate = st.sidebar.number_input(
    "販売手数料率（%）",
    min_value=0.0,
    max_value=30.0,
    value=10.0,
    step=0.5,
)

shipping = st.sidebar.number_input(
    "販売時の送料（円）",
    min_value=0,
    value=500,
    step=100,
)

target_profit = st.sidebar.number_input(
    "目標利益（円）",
    min_value=0,
    value=3000,
    step=500,
)

yahoo_result_count = st.sidebar.slider(
    "Yahoo検索件数",
    min_value=10,
    max_value=50,
    value=50,
    step=10,
)

netsea_product_limit = st.sidebar.number_input(
    "NETSEAを掘る商品数",
    min_value=1,
    max_value=50,
    value=10,
    step=1,
    help="販売価格・レビュー数などから探索優先度を付け、上位のJANだけNETSEAを掘ります。",
)

netsea_supplier_limit = st.sidebar.number_input(
    "1JANあたりサプライヤー巡回数",
    min_value=1,
    max_value=500,
    value=100,
    step=10,
    help="JAN指定時はNETSEA API仕様により1社ずつ照合します。",
)

supplier_max_pages = st.sidebar.number_input(
    "サプライヤー一覧の最大ページ数",
    min_value=1,
    max_value=50,
    value=20,
    step=1,
)

# ============================================================
# Supplier Control
# ============================================================
st.sidebar.divider()
st.sidebar.subheader("🏪 NETSEA接続")

if st.sidebar.button("📥 承認済みサプライヤーを取得"):
    try:
        with st.spinner("NETSEAの承認済みサプライヤーを取得中…"):
            suppliers = load_all_netsea_suppliers(
                force=True,
                max_pages=int(supplier_max_pages),
            )
        st.sidebar.success(f"{len(suppliers)}社取得しました。")
    except Exception as exc:
        st.sidebar.error(f"サプライヤー取得エラー: {exc}")

supplier_count = len(st.session_state.netsea_suppliers)
st.sidebar.caption(f"現在保持：{supplier_count}社")


# ============================================================
# Search
# ============================================================
st.header("🔎 販売商品を探す")
query = st.text_input(
    "探したい商品",
    placeholder="例：香水、ワイヤレスイヤホン、ドライヤー、ゲーム周辺機器",
)

search_button = st.button("🚀 利益商品を探す", type="primary")

if search_button:
    if not query.strip():
        st.warning("商品名を入力してください。")
        st.stop()

    try:
        appid = st.secrets["YAHOO_APP_ID"]
        yahoo_url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
        params = {
            "appid": appid,
            "query": query.strip(),
            "results": int(yahoo_result_count),
            "start": 1,
            "sort": "-score",
            "condition": "new",
            "in_stock": True,
        }

        with st.spinner("Yahoo!ショッピングから商品データ取得中…"):
            response = requests.get(yahoo_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

        hits = data.get("hits", [])
        rows = []

        for item in hits:
            price = safe_float(item.get("price"))
            if price is None or price <= 0:
                continue
            review = item.get("review") or {}
            rows.append({
                "商品ID": item.get("index", len(rows)),
                "商品名": item.get("name", ""),
                "販売価格": price,
                "レビュー数": int(safe_float(review.get("count"), 0) or 0),
                "レビュー評価": safe_float(review.get("rate"), 0) or 0,
                "JANコード": clean_jan(item.get("janCode")),
                "在庫": bool(item.get("inStock", True)),
                "ストア名": ((item.get("seller") or {}).get("name")) or "",
                "商品URL": item.get("url", ""),
            })

        if not rows:
            st.warning("分析できる商品が見つかりませんでした。")
            st.stop()

        result_df = pd.DataFrame(rows)
        result_df = result_df.drop_duplicates(subset=["商品URL", "JANコード"], keep="first")
        result_df["商品ID"] = range(len(result_df))

        st.session_state.search_results = result_df
        st.session_state.searched_query = query.strip()
        st.session_state.netsea_auto_results = []
        st.session_state.netsea_scan_status = []

        # 承認済みサプライヤーが未取得なら自動取得
        if not st.session_state.netsea_suppliers:
            with st.spinner("🏪 承認済みサプライヤーを自動取得中…"):
                st.session_state.netsea_suppliers = load_all_netsea_suppliers(
                    force=True,
                    max_pages=int(supplier_max_pages),
                )

        suppliers = st.session_state.netsea_suppliers
        jan_count = result_df["JANコード"].ne("").sum()

        st.success(
            f"Yahoo!商品{len(result_df)}件取得 / JANあり{jan_count}件 / NETSEAサプライヤー{len(suppliers)}社"
        )

        if jan_count > 0 and suppliers:
            with st.spinner("💰 利益余地の大きいJANからNETSEAを自動照合中…"):
                found, statuses = run_profit_scan(
                    result_df,
                    suppliers,
                    product_limit=int(netsea_product_limit),
                    supplier_limit=int(netsea_supplier_limit),
                    fee_rate=fee_rate,
                    shipping=shipping,
                    target_profit=target_profit,
                )
            st.session_state.netsea_auto_results = found
            st.session_state.netsea_scan_status = statuses
        else:
            st.info("JANコード付き商品、またはNETSEAサプライヤーが不足しています。")

    except requests.exceptions.RequestException as exc:
        st.error(f"Yahoo!ショッピングAPIへの接続に失敗しました: {exc}")
    except Exception as exc:
        st.error(f"検索処理でエラーが発生しました: {exc}")


# ============================================================
# Search Results
# ============================================================
if st.session_state.search_results is not None:
    df = st.session_state.search_results

    st.subheader(f"📦 「{st.session_state.searched_query}」の候補")
    st.dataframe(
        df[
            [
                "商品名",
                "販売価格",
                "レビュー数",
                "レビュー評価",
                "JANコード",
                "ストア名",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.caption("※Yahoo!ショッピングのAPIが返すJANコードが空の商品は、NETSEAのJAN照合対象から外れます。")


# ============================================================
# NETSEA Results
# ============================================================
if st.session_state.netsea_scan_status:
    st.divider()
    st.header("🔗 NETSEA照合状況")
    status_df = pd.DataFrame(st.session_state.netsea_scan_status)
    st.dataframe(status_df, use_container_width=True, hide_index=True)

if st.session_state.netsea_auto_results:
    st.divider()
    st.header("💎 利益が出る可能性のある仕入れ候補")

    result_df = pd.DataFrame(st.session_state.netsea_auto_results)

    # JANごとの最安仕入れを主候補にする
    best_df = (
        result_df.sort_values("仕入れ価格")
        .drop_duplicates("JANコード", keep="first")
        .sort_values(["判定", "利益", "ROI"], ascending=[True, False, False])
        .reset_index(drop=True)
    )

    # 判定順を固定
    rank_map = {"🟢 仕入れ候補": 0, "🟡 利益あり": 1, "🔴 見送り": 2}
    best_df["_判定順"] = best_df["判定"].map(rank_map).fillna(9)
    best_df = best_df.sort_values(
        ["_判定順", "利益", "ROI", "総合スコア"],
        ascending=[True, False, False, False],
    ).drop(columns=["_判定順"])
    best_df["順位"] = range(1, len(best_df) + 1)

    display_cols = [
        "順位",
        "判定",
        "Yahoo商品名",
        "販売価格",
        "仕入れ価格",
        "利益",
        "利益率",
        "ROI",
        "レビュー数",
        "総合スコア",
        "サプライヤー",
        "JANコード",
    ]
    display = best_df[display_cols].copy()
    for col in ["販売価格", "仕入れ価格", "利益"]:
        display[col] = display[col].round(0)
    for col in ["利益率", "ROI", "総合スコア"]:
        display[col] = display[col].round(1)

    st.dataframe(display.head(20), use_container_width=True, hide_index=True)

    candidates = best_df[best_df["判定"] == "🟢 仕入れ候補"]
    if not candidates.empty:
        st.success(f"🟢 目標利益{target_profit:,.0f}円・利益率15%・ROI30%以上を満たす候補が{len(candidates)}件あります。")
    else:
        st.warning("今回の検索では、設定した利益条件を満たす商品がありませんでした。条件を下げるより、別ジャンルを探す方が先です。")

    st.subheader("🥇 最優先候補")
    best = best_df.iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("販売価格", f"{best['販売価格']:,.0f}円")
    c2.metric("最安仕入れ", f"{best['仕入れ価格']:,.0f}円")
    c3.metric("予想利益", f"{best['利益']:,.0f}円")
    c4.metric("ROI", f"{best['ROI']:.1f}%")

    st.write(f"**判定：{best['判定']}**")
    st.write(f"仕入れ上限価格（目標利益{target_profit:,.0f}円）：**{best['仕入れ上限価格']:,.0f}円**")
    st.write(f"サプライヤー：**{best['サプライヤー']}**")

    col1, col2 = st.columns(2)
    with col1:
        if best["NETSEA商品URL"]:
            st.link_button("NETSEA商品を見る", best["NETSEA商品URL"])
    with col2:
        if best["Yahoo商品URL"]:
            st.link_button("Yahoo商品を見る", best["Yahoo商品URL"])

# ============================================================
# Manual fallback
# ============================================================
st.divider()
st.header("🛠️ 手動テスト")
st.caption("自動照合が空だったとき、特定JANだけを1社ずつ確認するためのテスト欄です。")

manual_jan = st.text_input("JANコード", key="manual_jan")
manual_limit = st.number_input("検索サプライヤー数", 1, 500, 20, 1, key="manual_limit")

if st.button("🔎 このJANだけNETSEA検索"):
    if not manual_jan.strip():
        st.warning("JANコードを入力してください。")
    else:
        try:
            suppliers = st.session_state.netsea_suppliers
            if not suppliers:
                suppliers = load_all_netsea_suppliers(force=True, max_pages=int(supplier_max_pages))
            with st.spinner("NETSEA検索中…"):
                found = search_netsea_jan(clean_jan(manual_jan), suppliers, int(manual_limit))
            if found:
                st.dataframe(pd.DataFrame(found), use_container_width=True, hide_index=True)
            else:
                st.warning("指定した範囲では一致商品がありませんでした。")
        except Exception as exc:
            st.error(f"NETSEA検索エラー: {exc}")
