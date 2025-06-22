```python
"""TT Analyzer – mobile input, Firestore/Google login (Prod) or local session (Stg)"""

from __future__ import annotations
from pathlib import Path
import os, streamlit as st, pandas as pd, altair as alt
import google.generativeai as genai

# ── config ────────────────────────────────────────────────────────────
st.set_page_config(page_title="TT Analyzer α版", layout="centered", initial_sidebar_state="collapsed")
IS_STAGING = os.getenv("STAGING", "").lower() in {"1", "true", "yes"}

genai.configure(api_key=st.secrets["gemini"]["api_key"])

if not IS_STAGING:
    # Firebase only in production
    import firebase_admin
    from firebase_admin import credentials, firestore

    SA = Path(__file__).with_name("myapp-firebase-adminsdk.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(SA)) if SA.exists() else None)
    db = firestore.client()
else:
    db = None
    st.sidebar.warning("⚠️ ステージング (Firestore 無効)")

# ── helpers ───────────────────────────────────────────────────────────
WIDGET_KEYS   = {"save_names", "server_radio", "serve_type_radio", "outcome_radio",
                 "confirm_reset", "cancel_reset"}
RESET_KEYS    = ["sets", "current_set", "saved_matches", "current_server",
                 "serve_counter", "match_over", "outcome_radio", "reset_prompt"]
SERVE_TYPES   = [
    "順回転サーブ（横/上/ナックル）", "順回転サーブ（下回転系）",
    "バックハンドサーブ（横/上/ナックル）", "バックハンドサーブ（下回転系）",
    "巻き込みサーブ（横/上/ナックル）", "巻き込みサーブ（下回転系）",
    "しゃがみ込みサーブ（横/上/ナックル）", "しゃがみ込みサーブ（下回転系）",
    "YGサーブ（横/上/ナックル）", "YGサーブ（下回転系）",
]
OUT_SERVER    = ["サービスエース", "3球目攻撃", "ラリー得点", "サーブミス",
                 "ラリー失点", "その他得点", "その他失点"]
OUT_RECEIVE   = ["レシーブエース", "ラリー得点", "レシーブミス", "ラリー失点",
                 "その他得点", "その他失点"]
WIN_SERVER    = {"サービスエース", "3球目攻撃", "ラリー得点", "その他得点"}
WIN_RECEIVE   = {"レシーブエース", "ラリー得点", "その他得点"}

# Firestore wrappers
_user_logged_in = lambda: bool(getattr(st, "user", None) and getattr(st.user, "sub", None))
_fs_doc          = lambda: db.collection("users").document(st.user.sub) if db else None

def _serialize_state() -> dict:
    data = {k: v for k, v in st.session_state.items() if k not in WIDGET_KEYS and not k.startswith("_")}
    if "sets" in data:
        data["sets"] = {str(i): df.to_dict("records") for i, df in enumerate(data["sets"])}
    return data

def _deserialize_state(d: dict):
    if "sets" in d:
        d["sets"] = [pd.DataFrame(v) for _, v in sorted(d["sets"].items(), key=lambda x: int(x[0]))]
    st.session_state.update(d)

# ── Streamlit session bootstrap ───────────────────────────────────────
new_set = lambda: pd.DataFrame(columns=["Rally", "Server", "Winner", "ServeType", "Outcome"])

st.session_state.setdefault("sets", [new_set()])
st.session_state.setdefault("current_set", 0)
st.session_state.setdefault("current_server", "選手A")
st.session_state.setdefault("serve_counter", 0)
st.session_state.setdefault("match_over", False)

# restore
if not st.session_state.get("_loaded"):
    if db and _user_logged_in():
        snap = _fs_doc().get();  _deserialize_state(snap.to_dict()) if snap.exists else None
    st.session_state["_loaded"] = True

# ── sidebar / login ──────────────────────────────────────────────────
st.sidebar.title("ユーザー")
if not _user_logged_in():
    if st.sidebar.button("Googleでログイン"): st.login()
else:
    st.sidebar.success(f"ログイン中: {st.user.name}")
    if st.sidebar.button("ログアウト"): st.logout(); st.rerun()

# ── player names ─────────────────────────────────────────────────────
st.session_state.setdefault("player_name", "選手A")
st.session_state.setdefault("opponent_name", "対戦相手")
with st.expander("選手設定", expanded=st.session_state.player_name == "選手A"):
    p, o = st.text_input("自分側", st.session_state.player_name), st.text_input("相手側", st.session_state.opponent_name)
    if st.button("保存", key="save_names"):
        if {p, o} - {st.session_state.player_name, st.session_state.opponent_name}:
            st.session_state.update(player_name=p or "選手A", opponent_name=o or "対戦相手")
            st.session_state.current_server = st.session_state.player_name
        st.rerun()
P, O = st.session_state.player_name, st.session_state.opponent_name
players = [P, O]

# ── utility funcs ─────────────────────────────────────────────────────

def ensure_cols():
    cols = ["Rally", "Server", "Winner", "ServeType", "Outcome"]
    for i, df in enumerate(st.session_state.sets):
        st.session_state.sets[i] = df.reindex(columns=cols)

def full_df() -> pd.DataFrame:
    return pd.concat([df.assign(Set=i+1) for i, df in enumerate(st.session_state.sets) if not df.empty], ignore_index=True)

ensure_cols()

# ── register rally ────────────────────────────────────────────────────

def register_rally():
    out = st.session_state.outcome_radio
    if out == "--":
        return
    log = st.session_state.sets[st.session_state.current_set]
    next_id = (pd.to_numeric(log.Rally, errors="coerce").max() or 0) + 1
    server  = st.session_state.server_radio
    winner  = P if ((server == P and out in WIN_SERVER) or (server == O and out in WIN_RECEIVE)) else O
    log.loc[len(log)] = [next_id, server, winner, st.session_state.serve_type_radio, out]
    st.session_state.serve_counter = (st.session_state.serve_counter + 1) % 2
    if st.session_state.serve_counter == 0:
        st.session_state.current_server = O if st.session_state.current_server == P else P
    st.session_state.match_over = any(abs((log.Winner == P).sum() - (log.Winner == O).sum()) >= 2 and (log.Winner == x).sum() >= 11 for x in (P, O))
    st.session_state.outcome_radio = "--"
    if db and _user_logged_in(): _fs_doc().set(_serialize_state())

# ── UI (top) ──────────────────────────────────────────────────────────
st.subheader("TT Analyzer α版")

colL, colR = st.columns([1, 1])
colL.metric("現在セット", st.session_state.current_set + 1)
if colR.button("新しいセット"):
    st.session_state.sets.append(new_set()); st.session_state.current_set += 1; st.rerun()

# ── input panel ───────────────────────────────────────────────────────
col1, col2 = st.columns([1, 2])
idx = players.index(st.session_state.current_server)
server_sel = col1.radio("サーバー", players, index=idx, key="server_radio")
if server_sel != st.session_state.current_server:
    st.session_state.current_server, st.session_state.serve_counter = server_sel, 0
serve_t   = col2.radio("サーブタイプ", SERVE_TYPES, key="serve_type_radio")
opts      = OUT_SERVER if server_sel == P else OUT_RECEIVE
st.radio("結果", ["--"] + opts, horizontal=True, key="outcome_radio", on_change=register_rally)

# ── score board ───────────────────────────────────────────────────────
log      = st.session_state.sets[st.session_state.current_set]
my_pts   = (log.Winner == P).sum(); op_pts = (log.Winner == O).sum()
st.metric(P, my_pts, delta=None, delta_color="off")
st.metric(O, op_pts, delta=None, delta_color="off")

if st.session_state.match_over:
    st.success(f"セット終了 {P}:{my_pts} - {O}:{op_pts}")

# ── charts & download ────────────────────────────────────────────────
if (df_all := full_df()).empty:
    st.info("データを入力するとチャートが表示されます")
else:
    win_df  = df_all[df_all.Winner == P].Outcome.value_counts().rename_axis("Factor").reset_index(name="Points")
    lose_df = df_all[df_all.Winner == O].Outcome.value_counts().rename_axis("Factor").reset_index(name="Points")

    def donut(df: pd.DataFrame, title: str):
        return (
            alt.Chart(df).mark_arc(innerRadius=50).encode(
                theta="Points:Q", color="Factor:N", tooltip=["Factor", "Points"], opacity=alt.value(0.85)
            ).properties(width=280, height=240, title=title)
        )

    c1, c2 = st.columns(2)
    c1.altair_chart(donut(win_df, "得点源"), use_container_width=True)
    c2.altair_chart(donut(lose_df, "失点源"), use_container_width=True)

    # serve win rate bar
    sel_server = st.radio("対象サーブ", ("自分サーブ", "相手サーブ"), horizontal=True, key="sv")
    target     = P if sel_server == "自分サーブ" else O
    sv_df      = df_all[df_all.Server == target]
    wr = (sv_df[sv_df.Winner == P].groupby("ServeType").size() / sv_df.groupby("ServeType").size()).fillna(0)
    st.altair_chart(
        alt.Chart(wr.reset_index(name="WinRate")).mark_bar().encode(y="ServeType:N", x=alt.X("WinRate:Q", axis=alt.Axis(format=".0%")), color="WinRate:Q"),
        use_container_width=True,
    )

    # download
    st.download_button("CSVダウンロード", df_all.to_csv(index=False, encoding="utf-8-sig"), file_name="TTAnalyzer.csv", mime="text/csv")

    # AI analysis
    if st.button("🤖 データを分析"):
        with st.spinner("Gemini 分析中…"):
            prompt = (
                f"あなたは卓球コーチです。次のCSVは{P}の試合データです。改善ポイントを5つ日本語で箇条書きしてください。\n\n" + df_all.to_csv(index=False)
            )
            st.session_state.analysis_result = genai.GenerativeModel("gemini-2.0-flash").generate_content(prompt).text

    if (res := st.session_state.get("analysis_result")):
        st.markdown("#### 📝 Gemini 提案")
        st.write(res)

st.caption("© 2025 TT Analyzer")
```
