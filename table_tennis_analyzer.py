# tt_analyzer_app.py
from __future__ import annotations

import os
from pathlib import Path
from enum import Enum, auto
from typing import Any

import pandas as pd
import streamlit as st
import altair as alt
import google.generativeai as genai

# ── 基本設定 ─────────────────────────────────────────────────────────
st.set_page_config(page_title="TT Analyzer α版",
                   layout="centered",
                   initial_sidebar_state="collapsed")

IS_STAGING = os.getenv("STAGING", "").lower() in ("1", "true", "yes")
genai.configure(api_key=st.secrets["gemini"]["api_key"])

if not IS_STAGING:
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = Path(__file__).with_name("myapp-firebase-adminsdk.json")
    if not firebase_admin._apps:
        if cred_path.exists():
            firebase_admin.initialize_app(credentials.Certificate(str(cred_path)))
        else:                        # Cloud Run / ADC
            firebase_admin.initialize_app()

    DB = firestore.client()
else:
    DB = None
    st.sidebar.warning("⚠️  STAGING: Firestore disabled")

# ── 定数 ──────────────────────────────────────────────────────────────
class ServeType(str, Enum):
    """サーブ種類"""
    FWD_FLAT  = "順回転サーブ（横/上/ナックル）"
    FWD_BACK  = "順回転サーブ（下回転系）"
    BH_FLAT   = "バックハンドサーブ（横/上/ナックル）"
    BH_BACK   = "バックハンドサーブ（下回転系）"
    HOOK_FLAT = "巻き込みサーブ（横/上/ナックル）"
    HOOK_BACK = "巻き込みサーブ（下回転系）"
    CROUCH_FLAT = "しゃがみ込みサーブ（横/上/ナックル）"
    CROUCH_BACK = "しゃがみ込みサーブ（下回転系）"
    YG_FLAT   = "YGサーブ（横/上/ナックル）"
    YG_BACK   = "YGサーブ（下回転系）"

class Outcome(str, Enum):
    """ラリー結果（自サーブ基準）"""
    SV_ACE   = "サービスエース"
    THIRD    = "3球目攻撃"
    RALLY_P  = "ラリー得点"
    SV_MISS  = "サーブミス"
    RALLY_L  = "ラリー失点"
    ETC_P    = "その他得点"
    ETC_L    = "その他失点"
    RC_ACE   = "レシーブエース"
    RC_MISS  = "レシーブミス"

WIN_SERVER  = {Outcome.SV_ACE, Outcome.THIRD, Outcome.RALLY_P, Outcome.ETC_P}
WIN_RECEIVE = {Outcome.RC_ACE, Outcome.RALLY_P, Outcome.ETC_P}

WIDGET_KEYS = {"save_names", "server_radio", "srv_type_radio",
               "outcome_radio", "confirm_reset", "cancel_reset"}
RESET_KEYS  = ["sets", "current_set", "current_server",
               "serve_counter", "match_over", "analysis_result"]

# ── Firestore util ──────────────────────────────────────────────────
def logged_in() -> bool:
    return bool(st.user and getattr(st.user, "sub", None))

def user_doc():
    return DB.collection("users").document(st.user.sub)

def _serialize_state() -> dict[str, Any]:
    data = {k: v for k, v in st.session_state.items()
            if k not in WIDGET_KEYS and not k.startswith("_")}
    if "sets" in data:
        data["sets"] = {str(i): df.to_dict("records")
                        for i, df in enumerate(data["sets"])}
    return data

def _deserialize_state(data: dict[str, Any]):
    if "sets" in data:
        data["sets"] = [pd.DataFrame(v) for _, v in sorted(data["sets"].items(),
                                                           key=lambda t: int(t[0]))]
    st.session_state.update(data)

def load_state():
    if not IS_STAGING and logged_in():
        snap = user_doc().get()
        if snap.exists:
            try:
                _deserialize_state(snap.to_dict())
            except Exception:
                pass

def save_state():
    if not IS_STAGING and logged_in():
        user_doc().set(_serialize_state(), merge=True)

def safe_rerun():
    """Streamlit rerun helper without無限再帰"""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

def reset_all():
    for k in RESET_KEYS:
        st.session_state.pop(k, None)
    if logged_in():
        user_doc().delete()
    st.toast("データをリセットしました", icon="🗑️")
    safe_rerun()

# ── セッション初期化 ─────────────────────────────────────────────────
def new_set() -> pd.DataFrame:
    return pd.DataFrame(columns=["Rally", "Server", "Winner",
                                 "ServeType", "Outcome"])

def ensure_columns():
    cols = ["Rally", "Server", "Winner", "ServeType", "Outcome"]
    for i, df in enumerate(st.session_state["sets"]):
        st.session_state["sets"][i] = df.reindex(columns=cols)

if not st.session_state.get("_loaded", False):
    st.session_state.setdefault("sets", [new_set()])
    st.session_state |= {
        "current_set":      0,
        "current_server":   "選手A",
        "serve_counter":    0,
        "match_over":       False,
        "player_name":      "選手A",
        "opponent_name":    "対戦相手",
    }
    load_state()
    ensure_columns()
    st.session_state["_loaded"] = True

P, O = st.session_state.player_name, st.session_state.opponent_name

# ── UI: 認証 ─────────────────────────────────────────────────────────
st.sidebar.title("ユーザー")
if not logged_in():
    st.sidebar.info("Googleでログインするとクラウド保存できます")
    if st.sidebar.button("Googleでログイン"):
        st.login()
else:
    st.sidebar.success(f"ログイン中: {st.user.name}")
    if st.sidebar.button("ログアウト"):
        st.logout(); safe_rerun()

# ── UI: プレイヤー設定 ───────────────────────────────────────────────
with st.expander("選手設定", expanded=(P == "選手A")):
    ip_p = st.text_input("自分側", P)
    ip_o = st.text_input("相手側", O)
    if st.button("保存", key="save_names"):
        st.session_state.player_name  = ip_p.strip() or "選手A"
        st.session_state.opponent_name = ip_o.strip() or "対戦相手"
        if st.session_state.current_server not in (P, O):
            st.session_state.current_server = st.session_state.player_name
        save_state(); safe_rerun()

P, O = st.session_state.player_name, st.session_state.opponent_name
players = [P, O]

# ── Helper ──────────────────────────────────────────────────────────
def full_df() -> pd.DataFrame:
    dfs = [df.assign(Set=i+1)
           for i, df in enumerate(st.session_state["sets"]) if not df.empty]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

# ── UI: 試合入力 ─────────────────────────────────────────────────────
st.subheader("TT Analyzer α版")

if st.button("新しいセット"):
    st.session_state["sets"].append(new_set())
    st.session_state.current_set += 1
    st.session_state.current_server, st.session_state.serve_counter = P, 0
    save_state(); safe_rerun()

log = st.session_state["sets"][st.session_state.current_set]

with st.form(key="rally_form", clear_on_submit=True):
    col_srv, col_type = st.columns([1, 2])
    srv_sel = col_srv.radio("サーバー", players,
                            index=players.index(st.session_state.current_server),
                            key="server_radio")
    if srv_sel != st.session_state.current_server:
        st.session_state.current_server, st.session_state.serve_counter = srv_sel, 0

    srv_type = col_type.radio("サーブタイプ",
                              [s.value for s in ServeType],
                              key="srv_type_radio")

    out_opts = (Outcome if srv_sel == P else
                [Outcome.RC_ACE, Outcome.RALLY_P, Outcome.RC_MISS,
                 Outcome.RALLY_L, Outcome.ETC_P, Outcome.ETC_L])
    outcome = st.radio("結果", [o.value for o in out_opts],
                       key="outcome_radio")

    submitted = st.form_submit_button("登録")
    if submitted:
        ids = pd.to_numeric(log["Rally"], errors="coerce")
        next_id = int(ids.max()) + 1 if ids.notna().any() else 1

        win = (P if ((srv_sel == P and Outcome(outcome) in WIN_SERVER) or
                     (srv_sel == O and Outcome(outcome) in WIN_RECEIVE)) else O)

        log.loc[len(log)] = [next_id, srv_sel, win, srv_type, outcome]

        st.session_state.serve_counter = (st.session_state.serve_counter + 1) % 2
        if st.session_state.serve_counter == 0:
            st.session_state.current_server = O if srv_sel == P else P

        p_pts, o_pts = (log["Winner"] == P).sum(), (log["Winner"] == O).sum()
        if (max(p_pts, o_pts) >= 11) and abs(p_pts - o_pts) >= 2:
            st.session_state.match_over = True

        st.toast(f"ラリー {next_id} 登録", icon="✅")
        save_state()
        safe_rerun()         # 画面クリア

# ── UI: スコアボード ────────────────────────────────────────────────
p_pts, o_pts = (log["Winner"] == P).sum(), (log["Winner"] == O).sum()
st.markdown("##### 現在セットスコア")
if st.session_state.match_over:
    st.success(f"セット終了 {P}:{p_pts} - {O}:{o_pts}")
    col1, col2 = st.columns(2)
    if col1.button("次セット"):
        st.session_state.match_over = False
        st.session_state["sets"].append(new_set())
        st.session_state.current_set += 1
        st.session_state.current_server, st.session_state.serve_counter = P, 0
        save_state(); safe_rerun()
    if col2.button("試合終了"):
        st.session_state.match_over = False

c1, c2, c3 = st.columns(3)
c1.metric(P, p_pts); c2.metric(O, o_pts)
c3.markdown(f"次サーブ: {st.session_state.current_server}")

# ── UI: リセット & セット一覧 ──────────────────────────────────────
if st.button("データをリセット", help="全データを削除します"): reset_all()

sets_view = [{"セット": i+1, P: (df["Winner"] == P).sum(),
              O: (df["Winner"] == O).sum()}
             for i, df in enumerate(st.session_state["sets"])]
st.dataframe(pd.DataFrame(sets_view), hide_index=True, use_container_width=True)

# ── チャート & Gemini 分析 ──────────────────────────────────────────
if (df_all := full_df()).empty:
    st.stop()

def _factor_counts(flag: str) -> pd.DataFrame:
    sub = df_all[df_all["Winner"] == flag]
    if sub.empty:
        return pd.DataFrame(columns=["Factor", "Points"])
    vc = sub["Outcome"].value_counts().reset_index()
    vc.columns = ["Factor", "Points"]
    return vc

win_df, lose_df = _factor_counts(P), _factor_counts(O)
highlight = alt.selection_point(on="mouseover", fields=["Factor"], empty="none")

st.markdown("##### 得点源 / 失点源")
for title, df in (("得点源", win_df), ("失点源", lose_df)):
    st.altair_chart(
        alt.Chart(df).mark_arc(innerRadius=50).encode(
            theta="Points:Q",
            color=alt.Color("Factor:N", legend=None),
            opacity=alt.condition(highlight, alt.value(1), alt.value(0.6)),
            tooltip=["Factor:N", "Points:Q"]
        ).add_params(highlight).properties(width=320, height=280),
        use_container_width=False,
    )

st.markdown("##### サーブ別勝率")
view = st.radio("対象", ["自分サーブ", "相手サーブ"], horizontal=True)
tgt = P if view == "自分サーブ" else O
df_srv = df_all[df_all["Server"] == tgt]
tot = df_srv.groupby("ServeType").size()
win = df_srv[df_srv["Winner"] == P].groupby("ServeType").size()
wr  = (win / tot).fillna(0).reset_index(name="WinRate")

st.altair_chart(
    alt.Chart(wr).mark_bar(cornerRadiusTopLeft=4,
                           cornerRadiusTopRight=4).encode(
        y=alt.Y("ServeType:N", sort="-x", title=None),
        x=alt.X("WinRate:Q", axis=alt.Axis(format=".0%", title="勝率")),
        color="WinRate:Q",
        tooltip=["ServeType:N", alt.Tooltip("WinRate:Q", format=".1%")],
        opacity=alt.condition(highlight, alt.value(1), alt.value(0.7)),
    ).add_params(highlight).properties(width=600, height=400),
    use_container_width=True,
)

# ── CSV 出力 ────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

ts = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M")
st.download_button("CSVダウンロード", data=_csv_bytes(df_all),
                   file_name=f"TTAnalyzer_{ts}.csv",
                   mime="text/csv")

# ── Gemini AI 分析 ─────────────────────────────────────────────────
if st.button("🤖 AI分析"):
    with st.spinner("分析中..."):
        prompt = (
            "あなたは卓球コーチです。以下は試合データCSVです。\n"
            "次セットの戦術アドバイスを箇条書き5つで提案してください。\n\n"
            + df_all.to_csv(index=False)
        )
        model = genai.GenerativeModel("gemini-2.0-flash")
        st.session_state.analysis_result = model.generate_content(prompt).text
        save_state(); safe_rerun()

if ar := st.session_state.get("analysis_result"):
    st.markdown("##### 📝 AI改善ポイント")
    st.write(ar)

st.caption("© 2025 TT Analyzer α版")
