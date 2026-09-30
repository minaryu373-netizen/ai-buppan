import streamlit as st
import pandas as pd
import requests

st.set_page_config(
    page_title="AI物販リサーチ",
    page_icon="📦",
    layout="wide"
)

st.title("📦 AI物販リサーチ")
st.write("Yahoo!ショッピングの商品を検索し、商品ごとの仕入れ価格から利益を分析します。")

# =========================
# Session State 初期化
# =========================

if "search_results" not in st.session_state:
    st.session_state.search_results = None

if "purchase_prices" not in st.session_state:
    st.session_state.purchase_prices = {}

if "searched_query" not in st.session_state:
    st.session_state.searched_query = ""

# =========================
# サイドバー設定
# =========================

st.sidebar.header("⚙️ 利益計算設定")

fee_rate = st.sidebar.number_input(
    "販売手数料率（%）",
    min_value=0.0,
    max_value=30.0,
    value=10.0,
    step=0.5
)

shipping = st.sidebar.number_input(
    "送料（円）",
    min_value=0,
    value=500,
    step=100
)

# =========================
# 商品検索
# =========================

st.header("🔎 商品検索")

query = st.text_input(
    "探したい商品",
    placeholder="例：香水、ワイヤレスイヤホン、スマートウォッチ"
)

search_button = st.button("商品を検索")

# =========================
# Yahoo検索
# =========================

if search_button:

    if not query:
        st.warning("商品名を入力してください。")
        st.stop()

    try:
        appid = st.secrets["YAHOO_APP_ID"]
    except Exception:
        st.error("Yahoo!ショッピングAPIのClient IDが設定されていません。")
        st.stop()

    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"

    params = {
        "appid": appid,
        "query": query,
        "results": 50,
        "start": 1,
        "sort": "-score",
        "condition": "new"
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        items = data.get("hits", [])

        if not items:
            st.warning("商品が見つかりませんでした。")
            st.stop()

        rows = []

        for i, item in enumerate(items):

            price = item.get("price")

            if price is None:
                continue

            price = float(price)

            review = item.get("review", {})

            review_count = review.get("count", 0)

           rows.append({
    "商品ID": i,
    "商品名": item.get("name", ""),
    "販売価格": price,
    "レビュー数": review_count,
    "JANコード": item.get("janCode", ""),
    "商品URL": item.get("url", "")
})

        if not rows:
            st.warning("分析できる商品がありませんでした。")
            st.stop()

        # 検索結果を保存
        st.session_state.search_results = pd.DataFrame(rows)

        # 新しい検索なので仕入れ価格をリセット
        st.session_state.purchase_prices = {}

        st.session_state.searched_query = query

    except requests.exceptions.RequestException as e:

        st.error(
            f"Yahoo!ショッピングAPIへの接続に失敗しました: {e}"
        )

    except Exception as e:

        st.error(
            f"エラーが発生しました: {e}"
        )

# =========================
# 検索結果表示
# =========================

if st.session_state.search_results is not None:

    df = st.session_state.search_results

    st.subheader(
        f"🔎 「{st.session_state.searched_query}」の検索結果"
    )

    st.info(
        "NETSEAなどで確認した仕入れ価格を商品ごとに入力してください。"
    )

    # =========================
    # 商品ごとの仕入れ価格
    # =========================

    for index, row in df.iterrows():

        col1, col2, col3 = st.columns([5, 2, 2])

        with col1:

            st.write(
                f"**{index + 1}. {row['商品名']}**"
            )

            st.caption(
                f"販売価格：{row['販売価格']:,.0f}円"
            )

        with col2:

            current_value = st.session_state.purchase_prices.get(
                index,
                0
            )

            purchase_price = st.number_input(
                "仕入れ価格（円）",
                min_value=0,
                value=int(current_value),
                step=100,
                key=f"purchase_price_{index}"
            )

            st.session_state.purchase_prices[index] = purchase_price

        with col3:

            if row["商品URL"]:

                st.link_button(
                    "商品を見る",
                    row["商品URL"]
                )

    # =========================
    # 分析ボタン
    # =========================

    st.divider()

    analyze_button = st.button(
        "🔥 利益を計算してランキング",
        type="primary"
    )

    if analyze_button:

        results = []

        for index, row in df.iterrows():

            price = float(row["販売価格"])

            purchase_price = float(
                st.session_state.purchase_prices.get(
                    index,
                    0
                )
            )

            review_count = int(
                row["レビュー数"]
            )

            # 仕入れ価格未入力はスキップ
            if purchase_price <= 0:
                continue

            # 販売手数料
            fee = price * fee_rate / 100

            # 利益
            profit = (
                price
                - purchase_price
                - fee
                - shipping
            )

            # 利益率
            profit_margin = (
                profit / price * 100
                if price > 0
                else 0
            )

            # ROI
            roi = (
                profit / purchase_price * 100
                if purchase_price > 0
                else 0
            )

            # =========================
            # 需要スコア
            # =========================

            demand_score = min(
                100,
                review_count / 10
            )

            # =========================
            # 利益率スコア
            # =========================

            margin_score = max(
                0,
                min(
                    100,
                    profit_margin * 4
                )
            )

            # =========================
            # ROIスコア
            # =========================

            roi_score = max(
                0,
                min(
                    100,
                    roi
                )
            )

            # =========================
            # 総合スコア
            # =========================

            total_score = (
                margin_score * 0.35
                + roi_score * 0.35
                + demand_score * 0.30
            )

            results.append({

                "商品名": row["商品名"],

                "販売価格": price,

                "仕入れ価格": purchase_price,

                "利益": profit,

                "利益率": profit_margin,

                "ROI": roi,

                "レビュー数": review_count,

                "需要スコア": demand_score,

                "総合スコア": total_score,

                "商品URL": row["商品URL"]

            })

        if not results:

            st.warning(
                "仕入れ価格を1商品以上入力してください。"
            )

            st.stop()

        result_df = pd.DataFrame(results)

        # 総合スコア順
        result_df = result_df.sort_values(
            "総合スコア",
            ascending=False
        ).reset_index(drop=True)

        result_df["順位"] = result_df.index + 1

        # =========================
        # TOP10
        # =========================

        st.subheader("🏆 仕入れ候補 TOP10")

        top10 = result_df.head(10).copy()

        display_df = top10[
            [
                "順位",
                "商品名",
                "販売価格",
                "仕入れ価格",
                "利益",
                "利益率",
                "ROI",
                "レビュー数",
                "需要スコア",
                "総合スコア"
            ]
        ].copy()

        display_df["販売価格"] = (
            display_df["販売価格"].round(0)
        )

        display_df["仕入れ価格"] = (
            display_df["仕入れ価格"].round(0)
        )

        display_df["利益"] = (
            display_df["利益"].round(0)
        )

        display_df["利益率"] = (
            display_df["利益率"].round(1)
        )

        display_df["ROI"] = (
            display_df["ROI"].round(1)
        )

        display_df["需要スコア"] = (
            display_df["需要スコア"].round(1)
        )

        display_df["総合スコア"] = (
            display_df["総合スコア"].round(1)
        )

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

        # =========================
        # 1位
        # =========================

        st.subheader("🥇 1位の商品")

        best = result_df.iloc[0]

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "販売価格",
            f"{best['販売価格']:,.0f}円"
        )

        col2.metric(
            "仕入れ価格",
            f"{best['仕入れ価格']:,.0f}円"
        )

        col3.metric(
            "利益",
            f"{best['利益']:,.0f}円"
        )

        col4.metric(
            "ROI",
            f"{best['ROI']:.1f}%"
        )

        st.write(
            f"### 総合スコア：{best['総合スコア']:.1f}"
        )

        st.write(
            f"利益率：**{best['利益率']:.1f}%**"
        )

        st.write(
            f"レビュー数：**{best['レビュー数']}件**"
        )

        if best["商品URL"]:

            st.link_button(
                "Yahoo!ショッピングで商品を見る",
                best["商品URL"]
            )
# =========================
# 仕入れ先商品との照合
# =========================

st.divider()

st.header("🔗 仕入れ先商品との照合")

st.write(
    "NETSEAなどで見つけた商品の情報を入力すると、"
    "Yahoo!ショッピングの商品との一致度を確認できます。"
)

source_name = st.text_input(
    "仕入れ先の商品名",
    placeholder="例：○○ オードトワレ 50ml"
)

source_price = st.number_input(
    "仕入れ先価格（円）",
    min_value=0,
    value=0,
    step=100
)

if st.button("🔍 商品を照合"):

    if not source_name:
        st.warning("仕入れ先の商品名を入力してください。")
        st.stop()

    if st.session_state.search_results is None:
        st.warning("先にYahoo!ショッピングで商品を検索してください。")
        st.stop()

    yahoo_df = st.session_state.search_results.copy()

    source_words = set(
        source_name.lower().replace("　", " ").split()
    )

    matches = []

    for _, row in yahoo_df.iterrows():

        yahoo_name = str(row["商品名"])

        yahoo_words = set(
            yahoo_name.lower().replace("　", " ").split()
        )

        if source_words and yahoo_words:

            common = source_words & yahoo_words

            match_rate = (
                len(common) / len(source_words) * 100
            )

        else:

            match_rate = 0

        matches.append({

            "Yahoo商品名": yahoo_name,

            "販売価格": row["販売価格"],

            "一致度": match_rate,

            "商品URL": row["商品URL"]

        })

    match_df = pd.DataFrame(matches)

    match_df = match_df.sort_values(
        "一致度",
        ascending=False
    ).head(10)

    st.subheader("🎯 一致候補")

    st.dataframe(
        match_df[
            [
                "Yahoo商品名",
                "販売価格",
                "一致度"
            ]
        ].round(1),
        use_container_width=True,
        hide_index=True
    )

    best_match = match_df.iloc[0]

    st.success(
        f"最も一致度が高い商品：{best_match['Yahoo商品名']}"
    )

    st.write(
        f"一致度：**{best_match['一致度']:.1f}%**"
    )

    if best_match["商品URL"]:

        st.link_button(
            "Yahoo!ショッピングの商品を見る",
            best_match["商品URL"]
        )
        # =========================
# 仕入れ先候補検索
# =========================

st.divider()

st.header("🛒 仕入れ先候補を探す")

st.write(
    "商品名から仕入れ先候補を検索します。"
)

source_search_word = st.text_input(
    "仕入れ先を探したい商品名",
    placeholder="例：ワイヤレスイヤホン"
)

if st.button("🛒 仕入れ先を探す"):

    if not source_search_word:
        st.warning("商品名を入力してください。")
        st.stop()

    st.subheader("🔎 検索候補")

    search_urls = {

        "NETSEA":
            f"https://www.netsea.jp/search/?keyword={source_search_word}",

        "SUPER DELIVERY":
            f"https://www.superdelivery.com/p/do/dpsl/search/?word={source_search_word}",

        "Yahoo!ショッピング":
            f"https://shopping.yahoo.co.jp/search?p={source_search_word}",

        "Amazon":
            f"https://www.amazon.co.jp/s?k={source_search_word}"

    }

    for name, url in search_urls.items():

        st.link_button(
            f"🔎 {name}で検索",
            url
        )
        # =========================
# 仕入れ検索キーワード自動生成
# =========================

st.divider()

st.header("🤖 仕入れ検索キーワード自動生成")

if st.session_state.search_results is not None:

    df = st.session_state.search_results

    product_options = {
        f"{i + 1}. {row['商品名']}": i
        for i, (_, row) in enumerate(df.iterrows())
    }

    selected_product = st.selectbox(
        "Yahoo!の商品を選択",
        list(product_options.keys())
    )

    selected_index = product_options[selected_product]
    selected_row = df.iloc[selected_index]

    product_name = str(selected_row["商品名"])

    # 商品名から検索キーワードを作成
    keywords = product_name.replace(
        "　", " "
    ).split()

    # 短すぎる単語を除外
    keywords = [
        word for word in keywords
        if len(word) >= 2
    ]

    search_keyword = " ".join(
        keywords[:8]
    )

    st.write("### 🔎 自動生成された検索キーワード")

    st.code(search_keyword)

    st.info(
        "このキーワードを仕入れ先検索に使います。"
    )

    st.link_button(
        "🛒 NETSEAで検索",
        f"https://www.netsea.jp/search/?keyword={search_keyword}"
    )

    st.link_button(
        "🛒 SUPER DELIVERYで検索",
        f"https://www.superdelivery.com/p/do/dpsl/search/?word={search_keyword}"
    )

else:

    st.info(
        "先にYahoo!ショッピングで商品を検索してください。"
    )
st.divider()

st.caption(
    "※仕入れ価格はNETSEA等で確認した実際の価格を入力してください。"
    "利益は販売手数料と送料を差し引いて計算しています。"
)
