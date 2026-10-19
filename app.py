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




def score_news_signal(title, description=""):
    """ニュース本文のキーワードから仮の需給シグナルを算出。予測モデルではなく一次スクリーニング。"""
    text = f"{title} {description}".lower()
    positive = {
        "生産終了": 4, "販売終了": 3, "絶版": 4, "受注終了": 3,
        "抽選販売": 2, "限定販売": 3, "数量限定": 3, "完売": 2,
        "品薄": 3, "再入荷": 1, "新弾": 2, "新作": 1, "発売決定": 1,
        "大会": 1, "優勝": 1, "高騰": 1, "値上がり": 2,
    }
    negative = {
        "再販決定": 5, "再生産": 4, "追加生産": 4, "受注生産": 4,
        "再入荷予定": 2, "大量入荷": 3, "増産": 4, "価格改定": 1,
    }
    pos_hits = [(k, v) for k, v in positive.items() if k in text]
    neg_hits = [(k, v) for k, v in negative.items() if k in text]
    score = sum(v for _, v in pos_hits) - sum(v for _, v in neg_hits)
    return score, [k for k, _ in pos_hits], [k for k, _ in neg_hits]


def fetch_google_news_rss(query, max_items=20):
    """Google News RSSから公開ニュースを取得。X投稿や成約データではない。"""
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ja&gl=JP&ceid=JP:ja"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 AI-Buppan-Research/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows = []
    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        pub_date = item.findtext("pubDate", default="").strip()
        source = item.findtext("source", default="").strip()
        description = item.findtext("description", default="").strip()
        score, positive_hits, negative_hits = score_news_signal(title, description)
        rows.append({
            "シグナル点": score,
            "見出し": title,
            "媒体": source,
            "公開日時": pub_date,
            "上昇要因キーワード": "、".join(positive_hits) or "該当なし",
            "供給増・下落リスク": "、".join(negative_hits) or "該当なし",
            "URL": link,
        })
    return rows


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
