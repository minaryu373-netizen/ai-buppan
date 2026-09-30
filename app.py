import streamlit as st
import pandas as pd
import requests

st.set_page_config(
    page_title="AI物販リサーチ",
    page_icon="📦",
    layout="wide"
)

st.title("📦 AI物販リサーチ")
st.write("Yahoo!ショッピングの商品データを取得して、利益・ROIを分析します。")

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

purchase_price_input = st.sidebar.number_input(
    "仕入れ価格（円）",
    min_value=0,
    value=0,
    step=100
)

# =========================
# Yahoo! API
# =========================

st.header("🔎 商品検索")

query = st.text_input(
    "探したい商品を入力",
    placeholder="例：ワイヤレスイヤホン"
)

search_button = st.button("商品を検索")

if search_button:

    if not query:
        st.warning("商品名を入力してください。")
        st.stop()

    # StreamlitのSecretsからClient IDを取得
    try:
        appid = st.secrets["YAHOO_APP_ID"]
    except Exception:
        st.error(
            "Yahoo!ショッピングAPIのClient IDが設定されていません。"
        )
        st.info(
            "次の手順でClient IDを設定します。"
        )
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

        for item in items:

            price = item.get("price")

            if price is None:
                continue

            price = float(price)

            # 仮の仕入れ価格
            purchase_price = purchase_price_input

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

            # レビュー数
            review = item.get("review", {})
            review_count = review.get("count", 0)

            # 需要スコア
            demand_score = min(
                100,
                review_count / 10
            )

            # 利益率スコア
            margin_score = max(
                0,
                min(100, profit_margin * 4)
            )

            # ROIスコア
            roi_score = max(
                0,
                min(100, roi)
            )

            # 総合スコア
            total_score = (
                margin_score * 0.35
                + roi_score * 0.35
                + demand_score * 0.30
            )

            rows.append({
                "商品名": item.get("name", ""),
                "販売価格": price,
                "仮仕入価格": purchase_price,
                "利益": profit,
                "利益率": profit_margin,
                "ROI": roi,
                "レビュー数": review_count,
                "需要スコア": demand_score,
                "総合スコア": total_score,
                "商品URL": item.get("url", "")
            })

        df = pd.DataFrame(rows)

        if df.empty:
            st.warning("分析できる商品がありませんでした。")
            st.stop()

        # 総合スコア順
        df = df.sort_values(
            "総合スコア",
            ascending=False
        ).reset_index(drop=True)

        df["順位"] = df.index + 1

        # =========================
        # TOP10
        # =========================

        st.subheader("🏆 仕入れ候補 TOP10")

        top10 = df.head(10).copy()

        display_df = top10[
            [
                "順位",
                "商品名",
                "販売価格",
                "仮仕入価格",
                "利益",
                "利益率",
                "ROI",
                "レビュー数",
                "需要スコア",
                "総合スコア"
            ]
        ].copy()

        display_df["販売価格"] = display_df["販売価格"].round(0)
        display_df["仮仕入価格"] = display_df["仮仕入価格"].round(0)
        display_df["利益"] = display_df["利益"].round(0)
        display_df["利益率"] = display_df["利益率"].round(1)
        display_df["ROI"] = display_df["ROI"].round(1)
        display_df["需要スコア"] = display_df["需要スコア"].round(1)
        display_df["総合スコア"] = display_df["総合スコア"].round(1)

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

        # =========================
        # 詳細
        # =========================

        st.subheader("📊 商品詳細")

        selected = st.selectbox(
            "商品を選択",
            df["商品名"].tolist()
        )

        product = df[
            df["商品名"] == selected
        ].iloc[0]

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "販売価格",
            f"{product['販売価格']:,.0f}円"
        )

        col2.metric(
            "利益",
            f"{product['利益']:,.0f}円"
        )

        col3.metric(
            "利益率",
            f"{product['利益率']:.1f}%"
        )

        col4.metric(
            "ROI",
            f"{product['ROI']:.1f}%"
        )

        st.write(
            f"### 総合スコア：{product['総合スコア']:.1f}"
        )

        if product["商品URL"]:
            st.link_button(
                "Yahoo!ショッピングで商品を見る",
                product["商品URL"]
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
    "※仮仕入価格は販売価格から計算した試算値です。"
    "実際の仕入価格ではありません。"
)
