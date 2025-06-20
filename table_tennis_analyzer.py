"""
TT Analyzer α版 – モバイル高速入力 (Firebase対応・Googleログイン)
---------------------------------------
・Google認証＋Firestore保存でマルチユーザー化
・未ログイン時はセッションのみ(ブラウザ閉じると消える)
"""

from pathlib import Path
import streamlit as st
import pandas as pd
import altair as alt
import google.generativeai as genai
genai.configure(api_key=st.secrets["gemini"]["api_key"])
import firebase_admin
from firebase_admin import credentials, firestore

# --- Firebase 初期化 ---
SERVICE_ACCOUNT = Path(__file__).with_name("myapp-firebase-adminsdk.json")

if not firebase_admin._apps:
    if SERVICE_ACCOUNT.exists():
        cred = credentials.Certificate(str(SERVICE_ACCOUNT))
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()   # Cloud Run は ADC

db = firestore.client()

# --- 定数 ---
WIDGET_KEYS = {"save_names", "server_radio", "serve_type_radio", "outcome_radio", "confirm_reset", "cancel_reset"}
RESET_KEYS = ["sets", "current_set", "saved_matches", "current_server", "serve_counter", "match_over", "outcome_radio", "reset_prompt"]

# --- Firestore関係 ---
def _user_logged_in() -> bool:
    try:
        return bool(st.user and getattr(st.user, "sub", None))
    except Exception:
        return False

def _fs_doc():
    return db.collection("users").document(st.user.sub)

def _serialize_state() -> dict:
    data = {k: v for k, v in st.session_state.items() if k not in WIDGET_KEYS and not k.startswith("_")}
    if "sets" in data:
        data["sets"] = {str(idx): df.to_dict("records") for idx, df in enumerate(data["sets"])}
    return data

def _deserialize_state(data: dict):
    if "sets" in data:
        sets_map = data.pop("sets")
        data["sets"] = [pd.DataFrame(sets_map[key]) for key in sorted(sets_map, key=lambda x: int(x))]
    st.session_state.update(data)

def load_state():
    if _user_logged_in():
        snap = _fs_doc().get()
        if snap.exists:
            try:
                _deserialize_state(snap.to_dict())
            except Exception:
                pass

def save_state():
    if _user_logged_in():
        _fs_doc().set(_serialize_state())

def safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        safe_rerun()

def reset_all():
    for k in RESET_KEYS:
        st.session_state.pop(k, None)
    if _user_logged_in():
        _fs_doc().delete()
    st.toast("データをリセットしました", icon="🗑️")
    safe_rerun()

# --- 認証UI ---
st.set_page_config(page_title="TT Analyzer α版", layout="centered", initial_sidebar_state="collapsed")
st.sidebar.title("ユーザー")
if not _user_logged_in():
    st.sidebar.info("Googleでログインするとデータがクラウド保存されます。")
    if st.sidebar.button("Googleでログイン"):
        st.login()
else:
    st.sidebar.success(f"ログイン中: {st.user.name}")
    if st.sidebar.button("ログアウト"):
        st.logout()
        safe_rerun()

# --- セッション初期化 ---
def new_set():
    return pd.DataFrame(columns=["Rally", "Server", "Winner", "ServeType", "Outcome"])
st.session_state.setdefault("sets", [new_set()])
st.session_state.setdefault("current_set", 0)
st.session_state.setdefault("saved_matches", [])
st.session_state.setdefault("current_server", st.session_state.get("player_name", "選手A"))
st.session_state.setdefault("serve_counter", 0)
st.session_state.setdefault("match_over", False)

# --- Firestore復元後に必ず呼ぶ関数を追加 ---
def ensure_columns():
    """すべてのセットDFに必須列を追加（復元で欠ける場合用）"""
    cols = ["Rally", "Server", "Winner", "ServeType", "Outcome"]
    for i, df in enumerate(st.session_state.sets):
        st.session_state.sets[i] = df.reindex(columns=cols)

# ─────── ここから全データ取得ヘルパ ───────
def get_full_df():
    dfs = [
        df.assign(Set=i+1)
        for i, df in enumerate(st.session_state.sets)
        if not df.empty
    ]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
# ──────────────────────────────────────────

# --- 初回のみstate読み込み ---
if not st.session_state.get("_loaded", False):
    load_state()
    ensure_columns()
    st.session_state["_loaded"] = True

# --- プレイヤー名 ---
st.session_state.setdefault("player_name", "選手A")
st.session_state.setdefault("opponent_name", "対戦相手")
with st.expander("選手設定", expanded=(st.session_state.player_name == "選手A")):
    ip_p = st.text_input("自分側（指導選手）", st.session_state.player_name)
    ip_o = st.text_input("相手側", st.session_state.opponent_name)
    if st.button("保存", key="save_names"):
        names_changed = (ip_p.strip() or "選手A") != st.session_state.player_name or (ip_o.strip() or "対戦相手") != st.session_state.opponent_name
        st.session_state.player_name = ip_p.strip() or "選手A"
        st.session_state.opponent_name = ip_o.strip() or "対戦相手"
        if st.session_state.get("current_server") not in {st.session_state.player_name, st.session_state.opponent_name}:
            st.session_state.current_server = st.session_state.player_name
            st.session_state.serve_counter = 0
        if names_changed and any(len(df) for df in st.session_state.get("sets", [])):
            st.session_state.reset_prompt = True
        save_state(); safe_rerun()

P, O = st.session_state.player_name, st.session_state.opponent_name
players = [P, O]

SERVE_TYPES = [
    "順回転サーブ（横/上/ナックル）", "順回転サーブ（下回転系）",
    "バックハンドサーブ（横/上/ナックル）", "バックハンドサーブ（下回転系）",
    "巻き込みサーブ（横/上/ナックル）", "巻き込みサーブ（下回転系）",
    "しゃがみ込みサーブ（横/上/ナックル）", "しゃがみ込みサーブ（下回転系）",
    "YGサーブ（横/上/ナックル）", "YGサーブ（下回転系）",
]
OUT_SERVER = ["サービスエース", "3球目攻撃", "ラリー得点", "サーブミス", "ラリー失点", "その他得点", "その他失点"]
OUT_RECEIVE = ["レシーブエース", "ラリー得点", "レシーブミス", "ラリー失点", "その他得点", "その他失点"]
WIN_SERVER = {"サービスエース", "3球目攻撃", "ラリー得点", "その他得点"}
WIN_RECEIVE = {"レシーブエース", "ラリー得点", "その他得点"}

# --- セット切替・リセット ---
if st.session_state.get("reset_prompt"):
    st.warning("選手名を変更しました。既存データをリセットしますか？")
    cR1, cR2 = st.columns(2)
    if cR1.button("はい、リセット", key="confirm_reset"): reset_all()
    if cR2.button("いいえ、保持", key="cancel_reset"):
        st.session_state.pop("reset_prompt"); save_state(); safe_rerun()

st.subheader("TT Analyzer α版")
ht1, ht2 = st.columns([1,1])
ht1.markdown(f"**現在セット:** {st.session_state.current_set+1}")
if ht2.button("新しいセット"):
    st.session_state.sets.append(new_set())
    st.session_state.current_set += 1
    st.session_state.current_server = P
    st.session_state.serve_counter = 0
    st.session_state.match_over = False
    save_state(); safe_rerun()

# --- 入力セクション ---
def register_rally():
    selected_server = st.session_state.server_radio
    serve_type      = st.session_state.serve_type_radio
    selected_out    = st.session_state.outcome_radio
    if selected_out == "--":
        return

    log = st.session_state.sets[st.session_state.current_set]
    P, O = st.session_state.player_name, st.session_state.opponent_name
    winner = (
        P
        if ((selected_server == P and selected_out in WIN_SERVER) 
             or (selected_server == O and selected_out in WIN_RECEIVE))
        else O
    )

    # Rally列を数値化して最大IDを算出
    ids    = pd.to_numeric(log["Rally"], errors="coerce")
    max_id = int(ids.max()) if (not ids.empty and not pd.isna(ids.max())) else 0
    next_id = max_id + 1

    log.loc[len(log)] = [next_id, selected_server, winner, serve_type, selected_out]
    st.session_state.serve_counter = (st.session_state.serve_counter + 1) % 2
    if st.session_state.serve_counter == 0:
        st.session_state.current_server = O if st.session_state.current_server == P else P
    my, op = (log["Winner"] == P).sum(), (log["Winner"] == O).sum()
    if (my >= 11 or op >= 11) and abs(my - op) >= 2:
        st.session_state.match_over = True
    st.toast(f"ラリー {next_id} 登録", icon="✅")
    save_state()
    st.session_state.outcome_radio = "--"

col_srv, col_type = st.columns([1,2])
idx_def = players.index(st.session_state.current_server) if st.session_state.current_server in players else 0
selected_server = col_srv.radio("サーバー", players, index=idx_def, key="server_radio")
if selected_server != st.session_state.current_server:
    st.session_state.current_server = selected_server
    st.session_state.serve_counter = 0
serve_type = col_type.radio("サーブタイプ", SERVE_TYPES, key="serve_type_radio")
out_opts = OUT_SERVER if selected_server == P else OUT_RECEIVE
st.radio("結果を選択", ["--"] + out_opts, horizontal=True, key="outcome_radio", on_change=register_rally)

# --- スコアボード ---
log = st.session_state.sets[st.session_state.current_set]
my_pts = (log["Winner"] == P).sum()
op_pts = (log["Winner"] == O).sum()
st.markdown("##### 現在セットスコア")
if st.session_state.match_over:
    st.success(f"セット終了 {P}:{my_pts} - {O}:{op_pts}")
    c1, c2 = st.columns(2)
    if c1.button("次セット開始"):
        st.session_state.sets.append(new_set())
        st.session_state.current_set += 1
        st.session_state.current_server = P
        st.session_state.serve_counter = 0
        st.session_state.match_over = False
        save_state(); safe_rerun()
    if c2.button("終了"):
        st.session_state.match_over = False

s1, s2, s3 = st.columns(3)
s1.metric(P, my_pts)
s2.metric(O, op_pts)
s3.markdown(f"次サーブ: {st.session_state.current_server}")

# --- リセット＆セット一覧 ---
if st.button("データをリセット", help="全データをクリアします"): reset_all()
st.markdown("##### セット一覧")
rows = [{"セット": i+1, P: (df["Winner"] == P).sum(), O: (df["Winner"] == O).sum()} for i, df in enumerate(st.session_state.sets)]
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ① フルデータ取得ヘルパー（どこか上部で１回定義）
def get_full_df():
    dfs = [
        df.assign(Set=i+1)
        for i, df in enumerate(st.session_state.sets)
        if not df.empty
    ]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

# --- チャート ---
non_empty = [df for df in st.session_state.sets if not df.empty]
if non_empty:
    full_df = pd.concat(non_empty, ignore_index=True)
    def make_counts(flag):
        sub = full_df[full_df["Winner"] == flag]
        if sub.empty:
            return pd.DataFrame(columns=["Factor", "Points"])
        dfc = sub["Outcome"].value_counts().reset_index()
        dfc.columns = ["Factor", "Points"]
        return dfc

    win_df = make_counts(P)
    lose_df = make_counts(O)
    highlight = alt.selection_point(on="mouseover", empty="none", fields=["Factor", "ServeType", "Outcome"])

    st.markdown("##### 得点源 / 失点源")
    cw, cl = st.columns(2)
    for (df, title), col in [((win_df, "得点源"), cw), ((lose_df, "失点源"), cl)]:
        chart = (
            alt.Chart(df)
            .mark_arc(innerRadius=50, outerRadius=90, cornerRadius=5, stroke="#333", strokeWidth=1)
            .encode(
                theta=alt.Theta("Points:Q"),
                color=alt.Color("Factor:N", scale=alt.Scale(scheme="category10"),
                                legend=alt.Legend(orient="right", title="要因", direction="vertical", offset=10)),
                opacity=alt.condition(highlight, alt.value(1), alt.value(0.6)),
                tooltip=[alt.Tooltip("Factor:N", title="要因"), alt.Tooltip("Points:Q", title="得点数")],
            ).add_params(highlight).properties(width=350, height=300)
        )
        col.altair_chart(chart, use_container_width=False)

    st.markdown("##### サーブ分析（サーバー別ビュー）")
    view = st.radio("対象サーブを選択", ["自分サーブ", "相手サーブ"], horizontal=True, key="serve_view")
    target = P if view == "自分サーブ" else O
    df_view = full_df[full_df["Server"] == target]
    tot = df_view.groupby("ServeType").size()
    win = df_view[df_view["Winner"] == P].groupby("ServeType").size()
    wr = (win / tot).fillna(0).reset_index()
    wr.columns = ["ServeType", "WinRate"]
    bar = (
        alt.Chart(wr)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            y=alt.Y("ServeType:N", sort="-x", title=None),
            x=alt.X("WinRate:Q", axis=alt.Axis(format=".0%", title="勝率")),
            color=alt.Color("WinRate:Q", scale=alt.Scale(scheme="greens"), legend=None),
            tooltip=[alt.Tooltip("ServeType:N", title="サーブ種類"), alt.Tooltip("WinRate:Q", title="勝率", format=".1%")],
            opacity=alt.condition(highlight, alt.value(1), alt.value(0.7)),
        ).add_params(highlight)
    )
    st.altair_chart(bar.properties(width=600, height=400), use_container_width=True)
    pivot = df_view.pivot_table(index="ServeType", columns="Outcome", aggfunc="size", fill_value=0)
    heat_df = pivot.reset_index().melt(id_vars="ServeType", var_name="Outcome", value_name="Count")
    heat = (
        alt.Chart(heat_df)
        .mark_rect(stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("Outcome:N", title="結果"),
            y=alt.Y("ServeType:N", title="サーブ種類"),
            color=alt.Color("Count:Q", scale=alt.Scale(scheme="lightmulti"), legend=alt.Legend(title="件数")),
            opacity=alt.condition(highlight, alt.value(1), alt.value(0.6)),
            tooltip=[
                alt.Tooltip("ServeType:N", title="サーブ種類"),
                alt.Tooltip("Outcome:N", title="結果"),
                alt.Tooltip("Count:Q", title="件数"),
            ],
        ).add_params(highlight)
    )
    st.altair_chart(heat.properties(width=700, height=500), use_container_width=True)

    # ─── CSVダウンロードボタン ───────────
    df_all = get_full_df()
    if not df_all.empty:
        csv_str   = df_all.to_csv(index=False, encoding="utf-8-sig")
        csv_bytes = csv_str.encode("utf-8-sig")
        
        ts = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d_%H%M")
        fname = f"TTAnalyzer_{ts}.csv"

        st.download_button(
            label="分析データをCSVでダウンロード",
            data=csv_bytes,
            file_name=fname,
            mime="text/csv",
            help="全セット結合＋Set列付きのCSVを出力します"
        )

     # ─── ここからAI分析ボタン ───────────
    if st.button("🤖 データを分析する"):
        with st.spinner("AIで分析中…"):
            prompt = (
                "卓球のラリー別データです。"
                f"{st.session_state.player_name}の改善ポイントを箇条書きにしてください。\n\n"
                "データ:\n" + df_all.to_csv(index=False)
            )
            chat = genai.chat.create(
                model="models/chat-bison-001",
                prompt=[{"author":"user","content":prompt}],
            )
            st.session_state.analysis_result = chat.last.response

    if st.session_state.get("analysis_result"):
        st.markdown("##### 📝 AIによる改善ポイント")
        st.write(st.session_state.analysis_result)
     # ─────────────────────────────────────────

st.caption("© 2025 TT Analyzer α版")
