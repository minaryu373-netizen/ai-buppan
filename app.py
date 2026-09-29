import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="AI物販リサーチ",
    page_icon="📦",
    layout="wide"
)

st.title("📦 AI物販リサーチシステム")
st.write("商品データから利益・ROI・需要を計算して、仕入れ候補をランキングします。")

# -------------------------
# 商品データ
# -------------------------
products = [
    {"商品名": "ワイヤレスイヤホン", "販売価格": 5980, "仕入価格": 2800, "需要": 85},
    {"商品名": "スマートウォッチ", "販売価格": 8980, "仕入価格": 5200, "需要": 78},
    {"商品名": "モバイルバッテリー", "販売価格": 3980, "仕入価格": 1800, "需要": 88},
    {"商品名": "Bluetoothスピーカー", "販売価格": 4980, "仕入価格": 2500, "需要": 80},
    {"商品名": "LEDデスクライト", "販売価格": 3280, "仕入価格": 1400, "需要": 75},
    {"商品名": "USBハブ", "販売価格": 2980, "仕入価格": 1200, "需要": 82},
    {"商品名": "スマホスタンド", "販売価格": 1980, "仕入価格": 700, "需要": 90},
    {"商品名": "PC冷却スタンド", "販売価格": 4480, "仕入価格": 2100, "需要": 73},
    {"商品名": "ワイヤレスマウス", "販売価格": 3980, "仕入価格": 1900, "需要": 86},
    {"商品名": "キーボード", "販売価格": 6980, "仕入価格": 3500, "需要": 79},
    {"商品名": "USB-Cケーブル", "販売価格": 1980, "仕入価格": 600, "需要": 92},
    {"商品名": "タブレットスタンド", "販売価格": 2980, "仕入価格": 1100, "需要": 84},
    {"商品名": "Webカメラ", "販売価格": 5980, "仕入価格": 3000, "需要": 77},
    {"商品名": "スマホリング", "販売価格": 1480, "仕入価格": 400, "需要": 89},
    {"商品名": "電動歯ブラシ", "販売価格": 4980, "仕入価格": 2600, "需要": 76},
]

df = pd.DataFrame(products)

# -------------------------
# 手数料・送料設定
# -------------------------
st.sidebar.header("⚙️ 設定")

fee_rate = st.sidebar.slider(
    "販売手数料率（%）",
    min_value=0.0,
    max_value=20.0,
    value=10.0,
    step=0.5
)

shipping = st.sidebar.number_input(
    "送料（円）",
    min_value=0,
    value=500,
    step=100
)

# -------------------------
# 利益計算
# -------------------------
df["販売手数料"] = df["販売価格"] * fee_rate / 100

df["利益"] = (
    df["販売価格"]
    - df["仕入価格"]
    - df["販売手数料"]
    - shipping
)

df["利益率"] = (
    df["利益"] / df["販売価格"] * 100
)

df["ROI"] = (
    df["利益"] / df["仕入価格"] * 100
)

# -------------------------
# スコア計算
# -------------------------

# 利益率スコア
df["利益率スコア"] = df["利益率"].clip(0, 100)

# ROIスコア
df["ROIスコア"] = df["ROI"].clip(0, 100)

# 需要スコア
df["需要スコア"] = df["需要"]

# 総合スコア
df["総合スコア"] = (
    df["利益率スコア"] * 0.35
    + df["ROIスコア"] * 0.30
    + df["需要スコア"] * 0.35
)

# ランキング
df = df.sort_values(
    "総合スコア",
    ascending=False
).reset_index(drop=True)

df["順位"] = df.index + 1

# -------------------------
# TOP10
# -------------------------

st.header("🏆 仕入れ候補 TOP10")

top10 = df.head(10)

display_df = top10[
    [
        "順位",
        "商品名",
        "販売価格",
        "仕入価格",
        "利益",
        "利益率",
        "ROI",
        "需要スコア",
        "総合スコア"
    ]
].copy()

display_df["利益率"] = display_df["利益率"].round(1)
display_df["ROI"] = display_df["ROI"].round(1)
display_df["総合スコア"] = display_df["総合スコア"].round(1)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True
)

# -------------------------
# 商品検索
# -------------------------

st.header("🔎 商品検索")

keyword = st.text_input(
    "商品名を入力してください"
)

if keyword:
    result = df[
        df["商品名"].str.contains(
            keyword,
            case=False,
            na=False
        )
    ]

    if len(result) > 0:
        st.dataframe(
            result[
                [
                    "商品名",
                    "販売価格",
                    "仕入価格",
                    "利益",
                    "利益率",
                    "ROI",
                    "需要スコア",
                    "総合スコア"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("該当する商品がありません。")

# -------------------------
# 詳細分析
# -------------------------

st.header("📊 商品詳細")

selected_product = st.selectbox(
    "商品を選択",
    df["商品名"].tolist()
)

product = df[
    df["商品名"] == selected_product
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
    f"### 総合スコア：{product['総合スコア']:.1f} / 100"
)

st.progress(
    min(max(float(product["総合スコア"]) / 100, 0), 1)
)

st.info(
    "※現在の商品データはテスト用です。"
    "実際の市場データではありません。"
)

st.caption(
    "AI物販リサーチシステム / Prototype"
)
