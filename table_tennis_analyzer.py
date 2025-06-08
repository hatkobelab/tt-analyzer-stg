"""
TT Analyzer α版 – モバイル高速入力 (v3.2.2)
===========================================

* ラジオで結果入力 → 登録後に自動リセット
* 11点先取＋2点差でセット終了
* ローカルファイル (`tt_state.pkl`) に自動保存／復元
* グラフ描画を安定化（型明示 & 列存在チェック）
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import pickle, os

DATA_FILE = "tt_state.pkl"

# ──────────────────── UTIL ────────────────────

def safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

# 全データリセット
RESET_KEYS = [
    "sets", "current_set", "saved_matches", "current_server", 
    "serve_counter", "match_over", "outcome_radio", "reset_prompt",
]

def reset_all():
    for k in RESET_KEYS:
        if k in st.session_state:
            del st.session_state[k]
    # pickle ファイルも削除
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)
    st.toast("データをリセットしました", icon="🗑️")
    safe_rerun()

# ──────────────────── PERSISTENCE ────────────────────

def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "rb") as f:
                st.session_state.update(pickle.load(f))
        except Exception:
            pass

def save_state():
    keys = [
        "player_name", "opponent_name", "sets", "current_set",
        "saved_matches", "current_server", "serve_counter",
    ]
    data = {k: st.session_state.get(k) for k in keys if k in st.session_state}
    with open(DATA_FILE, "wb") as f:
        pickle.dump(data, f)

if not st.session_state.get("_loaded", False):
    load_state()
    st.session_state["_loaded"] = True

# ──────────────────── PAGE CONFIG ────────────────────

st.set_page_config(page_title="TT Analyzer α版", layout="centered", initial_sidebar_state="collapsed")

# ──────────────────── PLAYER NAMES ────────────────────

if "player_name" not in st.session_state:
    st.session_state.player_name = "選手A"
if "opponent_name" not in st.session_state:
    st.session_state.opponent_name = "対戦相手"

with st.expander("選手設定", expanded=(st.session_state.player_name == "選手A")):
    p_name = st.text_input("自分側（指導選手）", st.session_state.player_name)
    o_name = st.text_input("相手側", st.session_state.opponent_name)
    if st.button("保存", key="save_names"):
        names_changed = (p_name.strip() or "選手A") != st.session_state.player_name or (o_name.strip() or "対戦相手") != st.session_state.opponent_name
        st.session_state.player_name = p_name.strip() or "選手A"
        st.session_state.opponent_name = o_name.strip() or "対戦相手"
        if st.session_state.get("current_server") not in {st.session_state.player_name, st.session_state.opponent_name}:
            st.session_state.current_server = st.session_state.player_name
            st.session_state.serve_counter = 0
        if names_changed and any(len(df) for df in st.session_state.get("sets", [])):
            st.session_state.reset_prompt = True
        save_state()
        safe_rerun()

P, O = st.session_state.player_name, st.session_state.opponent_name
players = [P, O]

# ──────────────────── SESSION INIT ────────────────────

def new_set():
    return pd.DataFrame(columns=["Rally", "Server", "Winner", "ServeType", "Outcome"])

if "sets" not in st.session_state:
    st.session_state.sets = [new_set()]
    st.session_state.current_set = 0
if "saved_matches" not in st.session_state:
    st.session_state.saved_matches = []
if "current_server" not in st.session_state:
    st.session_state.current_server = P
if "serve_counter" not in st.session_state:
    st.session_state.serve_counter = 0
if "match_over" not in st.session_state:
    st.session_state.match_over = False

# ──────────────────── CONSTANTS ────────────────────

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

# ──────────────────── HEADER ────────────────────

if st.session_state.get("reset_prompt"):
    st.warning("選手名を変更しました。既存の試合データをリセットしますか？")
    col_r1, col_r2 = st.columns(2)
    if col_r1.button("はい、リセット", key="confirm_reset"):
        reset_all()
    if col_r2.button("いいえ、保持", key="cancel_reset"):
        del st.session_state["reset_prompt"]
        save_state()

st.title("TT Analyzer α版")

c1, c2, _ = st.columns([1,1,1])
c1.markdown(f"**現在セット:** {st.session_state.current_set + 1}")
if c2.button("新しいセット"):
    st.session_state.sets.append(new_set())
    st.session_state.current_set += 1
    st.session_state.current_server = P
    st.session_state.serve_counter = 0
    st.session_state.match_over = False
    save_state(); safe_rerun()

# ──────────────────── INPUT UI ────────────────────

log = st.session_state.sets[st.session_state.current_set]

srv_col, type_col = st.columns([1,2])
idx_default = players.index(st.session_state.current_server) if st.session_state.current_server in players else 0
selected_server = srv_col.radio("サーバー", players, index=idx_default)
if selected_server != st.session_state.current_server:
    st.session_state.current_server = selected_server; st.session_state.serve_counter = 0
serve_type = type_col.radio("サーブタイプ", SERVE_TYPES)

out_opts = OUT_SERVER if selected_server == P else OUT_RECEIVE
selected_outcome = st.radio("結果を選択", ["--"] + out_opts, horizontal=True, key="outcome_radio")

if selected_outcome != "--":
    winner = P if ((selected_server == P and selected_outcome in WIN_SERVER) or (selected_server == O and selected_outcome in WIN_RECEIVE)) else O
    next_id = (log["Rally"].max() or 0) + 1
    log.loc[len(log)] = [next_id, selected_server, winner, serve_type, selected_outcome]

    st.session_state.serve_counter = (st.session_state.serve_counter + 1) % 2
    if st.session_state.serve_counter == 0:
        st.session_state.current_server = O if st.session_state.current_server == P else P

    del st.session_state["outcome_radio"]  # reset radio

    my, op = (log["Winner"] == P).sum(), (log["Winner"] == O).sum()
    if (my >= 11 or op >= 11) and abs(my - op) >= 2:
        st.session_state.match_over = True
    st.toast(f"ラリー {next_id} 登録", icon="✅")
    save_state(); safe_rerun()

# ──────────────────── SCOREBOARD ────────────────────

my_pts, op_pts = (log["Winner"] == P).sum(), (log["Winner"] == O).sum()
st.subheader("現在セット スコア")
sc1, sc2, sc3 = st.columns(3)
sc1.metric(P, my_pts); sc2.metric(O, op_pts); sc3.markdown(f"次サーブ: {st.session_state.current_server}")

if st.session_state.match_over:
    st.success(f"セット終了 {P}:{my_pts} - {O}:{op_pts}")
    b1, b2 = st.columns(2)
    if b1.button("次セット開始"):
        st.session_state.sets.append(new_set()); st.session_state.current_set +=1
        st.session_state.current_server = P; st.session_state.serve_counter = 0; st.session_state.match_over = False
        save_state(); safe_rerun()
    if b2.button("終了"):
        st.session_state.match_over = False

# ──────────────────── SET TABLE ────────────────────

if st.button("データをリセット", help="全試合と進行中データを削除"):
    reset_all()

st.subheader("セット一覧")


rows = [{"セット": i+1, P: (df["Winner"]==P).sum(), O: (df["Winner"]==O).sum()} for i,df in enumerate(st.session_state.sets)]
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ──────────────────── CHARTS ────────────────────

non_empty = [df for df in st.session_state.sets if not df.empty]
if non_empty:
    full_df = pd.concat(non_empty, ignore_index=True)

    # ---------- ドーナツ ----------
    def make_counts(flag):
        sub = full_df[full_df["Winner"] == flag]
        if sub.empty:
            return pd.DataFrame(columns=["Factor", "Points"])
        dfc = sub["Outcome"].value_counts().reset_index()
        dfc.columns = ["Factor", "Points"]
        return dfc

    win_df = make_counts(P)
    lose_df = make_counts(O)

    st.subheader("得点源 / 失点源")
    cw, cl = st.columns(2)
    if not win_df.empty:
        cw.markdown("得点源")
        cw.altair_chart(alt.Chart(win_df).mark_arc(innerRadius=40).encode(theta="Points:Q", color="Factor:N"), use_container_width=True)
    if not lose_df.empty:
        cl.markdown("失点源")
        cl.altair_chart(alt.Chart(lose_df).mark_arc(innerRadius=40).encode(theta="Points:Q", color="Factor:N"), use_container_width=True)

    # ---------- サーブタイプ別勝率 ----------
    if "ServeType" in full_df.columns:
        tot = full_df.groupby("ServeType").size()
        win = full_df[full_df["Winner"] == P].groupby("ServeType").size()
        win_rate_df = (win / tot).fillna(0).reset_index()
        win_rate_df.columns = ["ServeType", "WinRate"]
        if not win_rate_df.empty:
            st.subheader("サーブタイプ別 勝率")
            st.altair_chart(
                alt.Chart(win_rate_df)
                .mark_bar()
                .encode(x=alt.X("WinRate:Q", axis=alt.Axis(format=".0%"), title="勝率"), y=alt.Y("ServeType:N", sort="-x"), tooltip=["ServeType", alt.Tooltip("WinRate:Q", format=".0%")]),
                use_container_width=True,
            )

    # ---------- ヒートマップ ----------
    if {"ServeType", "Outcome"}.issubset(full_df.columns):
        pivot = full_df.pivot_table(index="ServeType", columns="Outcome", aggfunc="size", fill_value=0)
        heat_df = pivot.reset_index().melt(id_vars="ServeType", var_name="Outcome", value_name="Count")
        if not heat_df.empty:
            st.subheader("サーブタイプ × 結果")
            st.altair_chart(
                alt.Chart(heat_df)
                .mark_rect()
                .encode(x="Outcome:N", y="ServeType:N", color=alt.Color("Count:Q", scale=alt.Scale(scheme="blues")), tooltip=["ServeType", "Outcome", "Count"]),
                use_container_width=True,
            )

# ──────────────────── FOOTER ────────────────────

st.caption("© 2025 TT Analyzer α版")
