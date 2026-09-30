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
# 設定
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

if search_button:

    if not query:
        st.warning("商品名を入力してください。")
        st.stop()

    # Yahoo API
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

        # =========================
        # 商品データ作成
        # =========================

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
                "仕入れ価格": 0,
                "レビュー数": review_count,
                "商品URL": item.get("url", "")
            })

        df = pd.DataFrame(rows)

        if df.empty:
            st.warning("分析できる商品がありませんでした。")
            st.stop()

        # =========================
        # 仕入れ価格入力
        # =========================

        st.subheader("💰 商品ごとの仕入れ価格")

        st.info(
            "NETSEAなどで確認した仕入れ価格を商品ごとに入力してください。"
        )

        for index in df.index:

            col1, col2, col3 = st.columns([5, 2, 2])

            with col1:
                st.write(
                    f"**{index + 1}. {df.loc[index, '商品名']}**"
                )

                st.caption(
                    f"販売価格：{df.loc[index, '販売価格']:,.0f}円"
                )

            with col2:

                purchase_price = st.number_input(
                    "仕入れ価格",
                    min_value=0,
                    value=0,
                    step=100,
                    key=f"purchase_{index}"
                )

                df.loc[index, "仕入れ価格"] = purchase_price

            with col3:

                if df.loc[index, "商品URL"]:

                    st.link_button(
                        "商品を見る",
                        df.loc[index, "商品URL"]
                    )

        # =========================
        # 分析開始
        # =========================

        analyze_button = st.button(
            "🔥 利益を計算してランキング"
        )

        if analyze_button:

            results = []

            for index, row in df.iterrows():

                price = float(row["販売価格"])

                purchase_price = float(row["仕入れ価格"])

                review_count = int(row["レビュー数"])

                # 仕入れ価格0円の商品は除外
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

            # =========================
            # 結果表示
            # =========================

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
                display_df["販売価格"]
                .round(0)
            )

            display_df["仕入れ価格"] = (
                display_df["仕入れ価格"]
                .round(0)
            )

            display_df["利益"] = (
                display_df["利益"]
                .round(0)
            )

            display_df["利益率"] = (
                display_df["利益率"]
                .round(1)
            )

            display_df["ROI"] = (
                display_df["ROI"]
                .round(1)
            )

            display_df["需要スコア"] = (
                display_df["需要スコア"]
                .round(1)
            )

            display_df["総合スコア"] = (
                display_df["総合スコア"]
                .round(1)
            )

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )

            # =========================
            # 1位の商品
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

    except requests.exceptions.RequestException as e:

        st.error(
            f"Yahoo!ショッピングAPIへの接続に失敗しました: {e}"
        )

    except Exception as e:

        st.error(
            f"エラーが発生しました: {e}"
        )

else:

    st.info(
        "商品名を入力して「商品を検索」を押してください。"
    )

st.divider()

st.caption(
    "※仕入れ価格はNETSEA等で確認した実際の価格を入力してください。"
    "利益は販売手数料と送料を差し引いて計算しています。"
)
