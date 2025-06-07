"""
卓球試合アナライザー – モバイル版プロトタイプ (v2.2)
====================================================

* **選手名登録** – コーチが担当する選手名と対戦相手名を入力。
* セット制 & 試合保存機能（最大 5 試合）
* アイコンなし、スマホレイアウト

起動:
    streamlit run table_tennis_analyzer.py
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

# ───────────────────────── ユーティリティ ─────────────────────────

def safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

# ───────────────────────── ページ設定 ─────────────────────────

st.set_page_config(page_title="卓球アナライザー", layout="centered", initial_sidebar_state="collapsed")

# ───────────────────────── 選手名の設定 ─────────────────────────

if "player_name" not in st.session_state:
    st.session_state.player_name = "選手A"
if "opponent_name" not in st.session_state:
    st.session_state.opponent_name = "対戦相手"

with st.expander("選手設定", expanded=(st.session_state.player_name == "選手A")):
    p_name = st.text_input("自分側（指導選手）", st.session_state.player_name)
    o_name = st.text_input("相手側", st.session_state.opponent_name)
    if st.button("保存", key="save_names"):
        st.session_state.player_name = p_name.strip() or "選手A"
        st.session_state.opponent_name = o_name.strip() or "対戦相手"
        safe_rerun()

P = st.session_state.player_name
O = st.session_state.opponent_name
players = [P, O]

# ───────────────────────── セッション初期化 ─────────────────────────

if "sets" not in st.session_state:
    st.session_state.sets = [pd.DataFrame(columns=[
        "Rally", "Server", "Winner", "Reason", "Stroke", "Placement", "Notes"
    ])]
    st.session_state.current_set = 0

if "saved_matches" not in st.session_state:
    # list of dict {date, player, opponent, sets}
    st.session_state.saved_matches = []

# ───────────────────────── タイトル & セット操作 ─────────────────────────

st.title("卓球試合アナライザー")

head_c1, head_c2, head_c3 = st.columns([1, 1, 2])
head_c1.markdown(f"**現在のセット:** {st.session_state.current_set + 1}")
if head_c2.button("新しいセット開始"):
    st.session_state.sets.append(pd.DataFrame(columns=st.session_state.sets[0].columns))
    st.session_state.current_set += 1
    safe_rerun()

# ───────────────────────── ラリー入力 ─────────────────────────

current_log = st.session_state.sets[st.session_state.current_set]

with st.form("rally_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    server = c1.selectbox("サーバー", players, index=0)
    winner = c2.selectbox("得点者", players, index=0)

    reasons_default = ["サーブ得点", "レシーブミス", "3球目攻撃", "ラリー失点", "相手ミス"]
    reason = st.selectbox("得点要因", reasons_default + ["その他 (下に入力)"])
    custom_reason = ""
    if reason == "その他 (下に入力)":
        custom_reason = st.text_input("その他の理由を入力", placeholder="例: エッジボール")

    c3, c4 = st.columns(2)
    stroke = c3.selectbox("打球 (任意)", ["", "フォア", "バック", "フリック", "カット", "ロブ"])
    placement = c4.selectbox("コース (任意)", ["", "ショート", "ロング", "ワイド", "ミドル"])

    notes = st.text_input("メモ (任意)")

    if st.form_submit_button("ラリーを追加", use_container_width=True):
        next_rally = int(current_log["Rally"].max()) + 1 if not current_log.empty else 1
        current_log.loc[len(current_log)] = [
            next_rally, server, winner,
            custom_reason if custom_reason else reason,
            stroke, placement, notes,
        ]
        st.toast(f"ラリー {next_rally} を追加しました", icon="✅")
        safe_rerun()

# ───────────────────────── ログ編集 ─────────────────────────

with st.expander("ラリーログを編集／修正 (現在セット)"):
    edited_df = st.data_editor(current_log, num_rows="dynamic", hide_index=True, key="editor")
    st.session_state.sets[st.session_state.current_set] = edited_df

    del_col, _ = st.columns([1, 3])
    if del_col.button("最後のラリーを削除") and not edited_df.empty:
        st.session_state.sets[st.session_state.current_set] = edited_df.iloc[:-1].copy()
        safe_rerun()

# ───────────────────────── スコアボード ─────────────────────────

my_pts = (current_log["Winner"] == P).sum()
opp_pts = (current_log["Winner"] == O).sum()

st.subheader("現在セット スコアボード")
sc1, sc2, sc3 = st.columns(3)
sc1.metric(P, my_pts)
sc2.metric(O, opp_pts)
last_server = current_log.iloc[-1]["Server"] if not current_log.empty else "-"
sc3.markdown(f"サーブ: {last_server}")

# ───────────────────────── セット一覧 ─────────────────────────

st.subheader("セットスコア一覧")
rows = []
for idx, df_set in enumerate(st.session_state.sets, start=1):
    rows.append({
        "セット": idx,
        P: int((df_set["Winner"] == P).sum()),
        O: int((df_set["Winner"] == O).sum()),
    })
score_df = pd.DataFrame(rows)
st.dataframe(score_df, hide_index=True, use_container_width=True)

# ───────────────────────── 試合保存 ─────────────────────────

save_c, _ = st.columns([1, 5])
if save_c.button("試合を保存"):
    if not any(len(df) for df in st.session_state.sets):
        st.warning("試合データがありません")
    else:
        if len(st.session_state.saved_matches) == 5:
            st.session_state.saved_matches.pop(0)
        st.session_state.saved_matches.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "player": P,
            "opponent": O,
            "sets": [df.copy() for df in st.session_state.sets],
        })
        # リセット
        st.session_state.sets = [pd.DataFrame(columns=current_log.columns)]
        st.session_state.current_set = 0
        st.success("保存しました")
        safe_rerun()

if st.session_state.saved_matches:
    st.subheader("保存済み試合")
    for idx, match in enumerate(st.session_state.saved_matches, start=1):
        total_p = sum((df["Winner"] == match["player"]).sum() for df in match["sets"])
        total_o = sum((df["Winner"] == match["opponent"]).sum() for df in match["sets"])
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        c1.markdown(f"{idx}. {match['date']} - {match['player']} vs {match['opponent']}")
        c2.markdown(f"{total_p} - {total_o}")
        if c3.button("閲覧", key=f"view{idx}"):
            st.session_state.player_name = match["player"]
            st.session_state.opponent_name = match["opponent"]
            st.session_state.sets = [df.copy() for df in match["sets"]]
            st.session_state.current_set = 0
            safe_rerun()
        if c4.button("削除", key=f"del{idx}"):
            st.session_state.saved_matches.pop(idx-1)
            safe_rerun()

# ───────────────────────── 円グラフ ─────────────────────────

full_df = pd.concat(st.session_state.sets, ignore_index=True)
if not full_df.empty:
    def counts(flag):
        series = (
            full_df[full_df["Winner"] == flag]["Reason"].fillna("").astype(str).str.strip()
        )
        series = series[series != ""].value_counts()
        if series.empty:
            return pd.DataFrame(columns=["Factor", "Points"])
        df_counts = series.reset_index()
        df_counts.columns = ["Factor", "Points"]
        df_counts["Factor"] = df_counts["Factor"].astype(str)
        df_counts["Points"] = df_counts["Points"].astype(int)
        return df_counts

    win_counts = counts(P)
    lose_counts = counts(O)

    st.subheader("得点源 / 失点源")
    cw, cl = st.columns(2)

    if not win_counts.empty:
        win_chart = (
            alt.Chart(win_counts)
            .mark_arc(innerRadius=40)
            .encode(
                theta="Points:Q",
                color="Factor:N",
                tooltip=["Factor", "Points"],
            )
            .properties(height=250)
        )
        cw.markdown("得点源")
        cw.altair_chart(win_chart, use_container_width=True)

    if not lose_counts.empty:
        lose_chart = (
            alt.Chart(lose_counts)
            .mark_arc(innerRadius=40)
            .encode(
                theta="Points:Q",
                color="Factor:N",
                tooltip=["Factor", "Points"],
            )
            .properties(height=250)
        )
        cl.markdown("失点源")
        cl.altair_chart(lose_chart, use_container_width=True)
