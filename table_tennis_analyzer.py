from pathlib import Path
import os
import streamlit as st
import pandas as pd
import altair as alt
import google.generativeai as genai

# ── Configuration ───────────────────────────────────────────────────────────
st.set_page_config(page_title="TT Analyzer α版", layout="centered", initial_sidebar_state="collapsed")
genai.configure(api_key=st.secrets["gemini"]["api_key"])
IS_STAGING = os.getenv("STAGING", "").lower() in ("1", "true", "yes")

if not IS_STAGING:
    import firebase_admin
    from firebase_admin import credentials, firestore

    SERVICE_ACCOUNT = Path(__file__).with_name("myapp-firebase-adminsdk.json")
    if not firebase_admin._apps:
        if SERVICE_ACCOUNT.exists():
            cred = credentials.Certificate(str(SERVICE_ACCOUNT))
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()  # Cloud Run ADC

    db = firestore.client()
else:
    db = None
    st.sidebar.warning("⚠️ これはステージング環境です。Firestore はオフになっています。")

# ── Firestore State Helpers ─────────────────────────────────────────────────
def _user_logged_in() -> bool:
    try: return bool(st.user and getattr(st.user, "sub", None))
    except: return False

def _fs_doc():
    return db.collection("users").document(st.user.sub)

def _serialize_state() -> dict:
    data = {
        k: v
        for k, v in st.session_state.items()
        if not k.startswith("_") and k not in {"server_radio", "serve_type_radio", "outcome_radio"}
    }
    if "sets" in data:
        data["sets"] = {
            str(i): df.to_dict("records")
            for i, df in enumerate(data["sets"])
        }
    return data

def _deserialize_state(payload: dict):
    if "sets" in payload:
        sets_map = payload.pop("sets")
        payload["sets"] = [
            pd.DataFrame(sets_map[k]) for k in sorted(sets_map, key=lambda x: int(x))
        ]
    st.session_state.update(payload)

def load_state():
    if not IS_STAGING and _user_logged_in():
        snap = _fs_doc().get()
        if snap.exists:
            _deserialize_state(snap.to_dict())

def save_state():
    if not IS_STAGING and _user_logged_in():
        _fs_doc().set(_serialize_state())

def reset_all():
    for k in list(st.session_state.keys()):
        if not k.startswith("_"):
            st.session_state.pop(k, None)
    if not IS_STAGING and _user_logged_in():
        _fs_doc().delete()
    st.toast("データをリセットしました", icon="🗑️")
    st.experimental_rerun()

# ── Authentication UI ───────────────────────────────────────────────────────
if not IS_STAGING:
    st.sidebar.title("ユーザー")
    if _user_logged_in():
        st.sidebar.success(f"ログイン中: {st.user.name}")
        if st.sidebar.button("ログアウト"):
            st.logout()
            st.experimental_rerun()
    else:
        st.sidebar.info("Googleでログインするとデータがクラウド保存されます。")
        if st.sidebar.button("Googleでログイン"):
            st.login()

# ── Session Defaults ─────────────────────────────────────────────────────────
def new_set():
    return pd.DataFrame(columns=["Rally", "Server", "Winner", "ServeType", "Outcome"])

st.session_state.setdefault("sets", [new_set()])
st.session_state.setdefault("current_set", 0)
st.session_state.setdefault("current_server", st.session_state.get("player_name", "選手A"))
st.session_state.setdefault("serve_counter", 0)
st.session_state.setdefault("match_over", False)

# ── Helpers ─────────────────────────────────────────────────────────────────
def ensure_columns():
    cols = ["Rally", "Server", "Winner", "ServeType", "Outcome"]
    st.session_state.sets = [
        df.reindex(columns=cols) for df in st.session_state.sets
    ]

def get_full_df():
    dfs = [
        df.assign(Set=i + 1)
        for i, df in enumerate(st.session_state.sets)
        if not df.empty
    ]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

# 初回ロード
if not st.session_state.get("_loaded", False):
    load_state()
    ensure_columns()
    st.session_state._loaded = True

# ── Player Settings ─────────────────────────────────────────────────────────
st.session_state.setdefault("player_name", "選手A")
st.session_state.setdefault("opponent_name", "対戦相手")
with st.expander("選手設定", expanded=(st.session_state.player_name == "選手A")):
    name_p = st.text_input("自分側（指導選手）", st.session_state.player_name)
    name_o = st.text_input("相手側",     st.session_state.opponent_name)
    if st.button("保存", key="save_names"):
        st.session_state.player_name   = name_p.strip() or "選手A"
        st.session_state.opponent_name = name_o.strip() or "対戦相手"
        st.session_state.current_server = st.session_state.player_name
        st.session_state.serve_counter   = 0
        save_state()
        st.experimental_rerun()

P, O = st.session_state.player_name, st.session_state.opponent_name
players = [P, O]

SERVE_TYPES = [
    "順回転サーブ（横/上/ナックル）", "順回転サーブ（下回転系）",
    "バックハンドサーブ（横/上/ナックル）", "バックハンドサーブ（下回転系）",
    "巻き込みサーブ（横/上/ナックル）", "巻き込みサーブ（下回転系）",
    "しゃがみ込みサーブ（横/上/ナックル）", "しゃがみ込みサーブ（下回転系）",
    "YGサーブ（横/上/ナックル）",     "YGサーブ（下回転系）",
]
OUT_SERVER  = ["サービスエース", "3球目攻撃", "ラリー得点", "サーブミス", "ラリー失点", "その他得点", "その他失点"]
OUT_RECEIVE = ["レシーブエース", "ラリー得点", "レシーブミス", "ラリー失点", "その他得点", "その他失点"]
WIN_SERVER  = {"サービスエース", "3球目攻撃", "ラリー得点", "その他得点"}
WIN_RECEIVE = {"レシーブエース", "ラリー得点", "その他得点"}

# ── Main UI ─────────────────────────────────────────────────────────────────
st.subheader("TT Analyzer α版")

# セット切替
cs, ns = st.columns([1,1])
cs.markdown(f"**現在セット:** {st.session_state.current_set+1}")
if ns.button("新しいセット"):
    st.session_state.sets.append(new_set())
    st.session_state.current_set += 1
    st.session_state.current_server = P
    st.session_state.serve_counter   = 0
    st.session_state.match_over      = False
    save_state()
    st.experimental_rerun()

# ラリー登録
def register_rally():
    srv    = st.session_state.server_radio
    stype  = st.session_state.serve_type_radio
    outcome = st.session_state.outcome_radio
    if outcome == "--": return

    df = st.session_state.sets[st.session_state.current_set]
    winner = (
        P if ((srv == P and outcome in WIN_SERVER) or
              (srv == O and outcome in WIN_RECEIVE))
        else O
    )
    next_id = int(pd.to_numeric(df["Rally"], errors="coerce").max() or 0) + 1
    df.loc[len(df)] = [next_id, srv, winner, stype, outcome]

    # サーブ交代 & ゲーム終了判定
    st.session_state.serve_counter = (st.session_state.serve_counter + 1) % 2
    if st.session_state.serve_counter == 0:
        st.session_state.current_server = O if srv == P else P
    p_pts = (df["Winner"] == P).sum()
    o_pts = (df["Winner"] == O).sum()
    if max(p_pts, o_pts) >= 11 and abs(p_pts - o_pts) >= 2:
        st.session_state.match_over = True

    st.toast(f"ラリー {next_id} 登録", icon="✅")
    save_state()
    st.session_state.outcome_radio = "--"

c1, c2 = st.columns([1,2])
idx = players.index(st.session_state.current_server)
c1.radio("サーバー",     players, index=idx,       key="server_radio")
c2.radio("サーブタイプ", SERVE_TYPES, key="serve_type_radio")
st.radio(
    "結果を選択",
    ["--"] + (OUT_SERVER if st.session_state.server_radio == P else OUT_RECEIVE),
    horizontal=True,
    key="outcome_radio",
    on_change=register_rally
)

# スコアボード
df = st.session_state.sets[st.session_state.current_set]
p_pts, o_pts = (df["Winner"] == P).sum(), (df["Winner"] == O).sum()
st.markdown("##### 現在セットスコア")
if st.session_state.match_over:
    st.success(f"セット終了 {P}:{p_pts} - {O}:{o_pts}")
    a1, a2 = st.columns(2)
    if a1.button("次セット開始"):
        st.experimental_rerun()
    if a2.button("終了"):
        st.session_state.match_over = False

m1, m2, m3 = st.columns(3)
m1.metric(P, p_pts)
m2.metric(O, o_pts)
m3.markdown(f"次サーブ: {st.session_state.current_server}")

# データリセット
if st.button("データをリセット"):
    reset_all()

# セット一覧
rows = [
    {"セット": i+1, P: (df["Winner"]==P).sum(), O: (df["Winner"]==O).sum()}
    for i, df in enumerate(st.session_state.sets)
]
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# チャート
full = get_full_df()
if not full.empty:
    # 得点源／失点源チャート...
    # CSV ダウンロード
    csv = full.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    ts = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d_%H%M")
    st.download_button("📥 CSV ダウンロード", csv, f"TTAnalyzer_{ts}.csv", "text/csv")

    # AI 分析
    if st.button("🤖 データを分析する"):
        prompt = (
            "あなたは卓球コーチです。\n"
            f"{P} のラリー別データです。次セットの戦術アドバイスを5点で箇条書きしてください。\n\n"
            + full.to_csv(index=False)
        )
        model = genai.GenerativeModel("gemini-2.0-flash")
        res = model.generate_content(prompt)
        st.session_state.analysis = res.text

    if st.session_state.get("analysis"):
        st.markdown("##### 📝 AIによる改善ポイント")
        st.write(st.session_state.analysis)

st.caption("© 2025 TT Analyzer α版")
