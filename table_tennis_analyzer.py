'''
TT Analyzer α版 – モバイル高速入力 (v3.4 修正版)
========================================

* 結果選択後、自動リセット
* 11点先取＋2点差でセット終了ダイアログ
* ローカル永続化（`tt_state.pkl`）
* ウィジェットキーを除外して保存・復元
* ドーナツ／勝率バー／ヒートマップ を安定描画
''' 
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import pickle, os
import altair as alt

# ─────────────────── CONFIG ───────────────────
DATA_FILE = "tt_state.pkl"
WIDGET_KEYS = {"save_names", "server_radio", "serve_type_radio", "outcome_radio", "confirm_reset", "cancel_reset"}
RESET_KEYS = [
    "sets", "current_set", "saved_matches", "current_server",
    "serve_counter", "match_over", "outcome_radio", "reset_prompt",
]

# ─────────────────── UTIL ───────────────────
def safe_rerun():
    if hasattr(st, "rerun"): st.rerun()
    else: st.experimental_rerun()

def reset_all():
    for k in RESET_KEYS:
        st.session_state.pop(k, None)
    if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
    st.toast("データをリセットしました", icon="🗑️")
    safe_rerun()

# ───────────────── PERSISTENCE ───────────────────
def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "rb") as f:
                st.session_state.update(pickle.load(f))
        except Exception:
            pass

def save_state():
    data = {k: v for k, v in st.session_state.items()
            if k not in WIDGET_KEYS and not k.startswith("_")}
    with open(DATA_FILE, "wb") as f:
        pickle.dump(data, f)

if not st.session_state.get("_loaded", False):
    load_state()
    st.session_state["_loaded"] = True

# ─────────────── PAGE CONFIG ───────────────
st.set_page_config(page_title="TT Analyzer α版", layout="centered", initial_sidebar_state="collapsed")

# ─────────────── PLAYER NAMES ───────────────
st.session_state.setdefault("player_name", "選手A")
st.session_state.setdefault("opponent_name", "対戦相手")

with st.expander("選手設定", expanded=(st.session_state.player_name == "選手A")):
    ip_p = st.text_input("自分側（指導選手）", st.session_state.player_name)
    ip_o = st.text_input("相手側", st.session_state.opponent_name)
    if st.button("保存", key="save_names"):
        names_changed = (ip_p.strip() or "選手A") != st.session_state.player_name \
                      or (ip_o.strip() or "対戦相手") != st.session_state.opponent_name
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

# ─────────────── SESSION INIT ───────────────
def new_set():
    return pd.DataFrame(columns=["Rally", "Server", "Winner", "ServeType", "Outcome"])

st.session_state.setdefault("sets", [new_set()])
st.session_state.setdefault("current_set", 0)
st.session_state.setdefault("saved_matches", [])
st.session_state.setdefault("current_server", P)
st.session_state.setdefault("serve_counter", 0)
st.session_state.setdefault("match_over", False)

# ─────────────── CONSTANTS ───────────────
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

# ─────────────── HEADER ───────────────
if st.session_state.get("reset_prompt"):
    st.warning("選手名を変更しました。既存データをリセットしますか？")
    cR1, cR2 = st.columns(2)
    if cR1.button("はい、リセット", key="confirm_reset"): reset_all()
    if cR2.button("いいえ、保持", key="cancel_reset"):
        st.session_state.pop("reset_prompt"); save_state(); safe_rerun()

st.title("TT Analyzer α版")
ht1, ht2 = st.columns([1,1])
ht1.markdown(f"**現在セット:** {st.session_state.current_set+1}")
if ht2.button("新しいセット"):    
    st.session_state.sets.append(new_set())
    st.session_state.current_set += 1
    st.session_state.current_server = P
    st.session_state.serve_counter = 0
    st.session_state.match_over = False
    save_state(); safe_rerun()

# ─────────────── INPUT SECTION ───────────────
# コールバックでラリーを登録し、結果選択をリセット

def register_rally():
    selected_server = st.session_state.server_radio
    serve_type = st.session_state.serve_type_radio
    selected_out = st.session_state.outcome_radio
    if selected_out == "--":
        return
    log = st.session_state.sets[st.session_state.current_set]
    P = st.session_state.player_name
    O = st.session_state.opponent_name
    winner = P if ((selected_server == P and selected_out in WIN_SERVER) or (selected_server == O and selected_out in WIN_RECEIVE)) else O
    next_id = (log["Rally"].max() or 0) + 1
    log.loc[len(log)] = [next_id, selected_server, winner, serve_type, selected_out]
    # サーブ交代／カウンター更新
    st.session_state.serve_counter = (st.session_state.serve_counter + 1) % 2
    if st.session_state.serve_counter == 0:
        st.session_state.current_server = O if st.session_state.current_server == P else P
    # セット終了判定
    my, op = (log["Winner"] == P).sum(), (log["Winner"] == O).sum()
    if (my >= 11 or op >= 11) and abs(my - op) >= 2:
        st.session_state.match_over = True
    st.toast(f"ラリー {next_id} 登録", icon="✅")
    save_state()
    # 結果選択をデフォルトに戻す
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

# ─────────────── SCOREBOARD ───────────────
log = st.session_state.sets[st.session_state.current_set]
my_pts, op_pts = (log["Winner"] == P).sum(), (log["Winner"] == O).sum()
st.subheader("現在セット スコア")
s1, s2, s3 = st.columns(3)
s1.metric(P, my_pts);
s2.metric(O, op_pts);
s3.markdown(f"次サーブ: {st.session_state.current_server}")
if st.session_state.match_over:
    st.success(f"セット終了 {P}:{my_pts} - {O}:{op_pts}")
    b1, b2 = st.columns(2)
    if b1.button("次セット開始"):    
        st.session_state.sets.append(new_set())
        st.session_state.current_set += 1
        st.session_state.current_server = P
        st.session_state.serve_counter = 0
        st.session_state.match_over = False
        save_state(); safe_rerun()
    if b2.button("終了"): st.session_state.match_over = False

# ─────────────── RESET BUTTON & SET TABLE ───────────────
if st.button("データをリセット", help="全データをクリアします"): reset_all()
st.subheader("セット一覧")
rows = [{"セット": i+1, P: (df["Winner"] == P).sum(), O: (df["Winner"] == O).sum()} for i, df in enumerate(st.session_state.sets)]
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ─────────────── CHARTS ───────────────
non_empty = [df for df in st.session_state.sets if not df.empty]
if non_empty:
    full_df = pd.concat(non_empty, ignore_index=True)

    # ——— 得点源／失点源 用のデータ準備 ———
    def make_counts(flag):
        sub = full_df[full_df["Winner"] == flag]
        if sub.empty:
            return pd.DataFrame(columns=["Factor", "Points"])
        dfc = sub["Outcome"].value_counts().reset_index()
        dfc.columns = ["Factor", "Points"]
        return dfc

    win_df = make_counts(P)
    lose_df = make_counts(O)

    # ——— 共通ホバーハイライト ———
    highlight = alt.selection_point(
        on="mouseover",
        empty="none",
        fields=["Factor", "ServeType", "Outcome"],
    )

    # ─── 得点源／失点源ドーナツ ───────────────────────
    st.subheader("得点源 / 失点源")
    cw, cl = st.columns(2)
    for (df, title), col in [((win_df, "得点源"), cw), ((lose_df, "失点源"), cl)]:
        chart = (
            alt.Chart(df)
               .mark_arc(innerRadius=50, outerRadius=90, cornerRadius=5, stroke="#333", strokeWidth=1)
               .encode(
                   theta=alt.Theta("Points:Q"),
                   color=alt.Color(
                       "Factor:N",
                       scale=alt.Scale(scheme="category10"),
                       legend=alt.Legend(orient="right", title="要因", direction="vertical")
                   ),
                   opacity=alt.condition(highlight, alt.value(1), alt.value(0.6)),
                   tooltip=[
                       alt.Tooltip("Factor:N", title="要因"),
                       alt.Tooltip("Points:Q", title="得点数"),
                   ],
               )
               .add_params(highlight)
        )
        col.altair_chart(
            chart.properties(width=300, height=300, title=title),
            use_container_width=False
        )

    # ─── ここまでが for ループ ─────────────────────────

    # ─── サーブ別ビュー切り替え ───────────────────────
    st.subheader("サーブ分析（サーバー別ビュー）")
    view = st.radio(
        "対象サーブを選択",
        ["自分サーブ", "相手サーブ"],
        horizontal=True,
        key="serve_view"
    )
    target = P if view == "自分サーブ" else O
    df_view = full_df[full_df["Server"] == target]

    # ——— サーブタイプ別 勝率用データ準備 ———
    tot = df_view.groupby("ServeType").size()
    win = df_view[df_view["Winner"] == P].groupby("ServeType").size()
    wr = (win / tot).fillna(0).reset_index()
    wr.columns = ["ServeType", "WinRate"]

    # ─── サーブタイプ別勝率バー ───────────────────────
    bar = (
        alt.Chart(wr)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            y=alt.Y("ServeType:N", sort="-x", title=None),
            x=alt.X("WinRate:Q", axis=alt.Axis(format=".0%", title="勝率")),
            color=alt.Color("WinRate:Q", scale=alt.Scale(scheme="greens"), legend=None),
            tooltip=[
                alt.Tooltip("ServeType:N", title="サーブ種類"),
                alt.Tooltip("WinRate:Q", title="勝率", format=".1%"),
            ],
            opacity=alt.condition(highlight, alt.value(1), alt.value(0.7)),
        )
        .add_params(highlight)
    )
    st.altair_chart(bar.properties(width=600, height=400), use_container_width=True)

    # ——— サーブタイプ×結果 用データ準備 ———
    pivot = df_view.pivot_table(
        index="ServeType", columns="Outcome", aggfunc="size", fill_value=0
    )
    heat_df = pivot.reset_index().melt(
        id_vars="ServeType", var_name="Outcome", value_name="Count"
    )

    # ─── サーブタイプ × 結果 ヒートマップ ───────────────────────
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
        )
        .add_params(highlight)
    )
    st.altair_chart(heat.properties(width=700, height=500), use_container_width=True)

# ─────────────── FOOTER ───────────────
st.caption("© 2025 TT Analyzer α版")
