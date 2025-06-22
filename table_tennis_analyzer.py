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

# ── Firebase (本番のみ) ────────────────────────────────────────────────────
if not IS_STAGING:
    import firebase_admin
    from firebase_admin import credentials, firestore

    SA_PATH = Path(__file__).with_name("myapp-firebase-adminsdk.json")
    if not firebase_admin._apps:
        if SA_PATH.exists():
            cred = credentials.Certificate(str(SA_PATH))
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()  # ADC
    db = firestore.client()
else:
    db = None
    st.sidebar.warning("⚠️ ステージング環境: Firestore は無効化しています。")

# ── Firestore Helpers ──────────────────────────────────────────────────────
def _user_logged_in() -> bool:
    try:
        return bool(st.user and getattr(st.user, "sub", None))
    except:
        return False

def _fs_doc():
    return db.collection("users").document(st.user.sub)

def _serialize_state():
    payload = {
        k: v
        for k, v in st.session_state.items()
        if not k.startswith("_") and k not in ("server_radio", "serve_type_radio", "outcome_radio")
    }
    if "sets" in payload:
        payload["sets"] = {
            str(i): df.to_dict("records")
            for i, df in enumerate(payload["sets"])
        }
    return payload

def _deserialize_state(doc: dict):
    if "sets" in doc:
        sets_map = doc.pop("sets")
        doc["sets"] = [pd.DataFrame(sets_map[k]) for k in sorted(sets_map, key=int)]
    st.session_state.update(doc)

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
        st.sidebar.info("Googleログインでクラウド保存")
        if st.sidebar.button("ログイン"):
            st.login()

# ── Session Defaults ─────────────────────────────────────────────────────────
def new_set():
    return pd.DataFrame(columns=["Rally", "Server", "Winner", "ServeType", "Outcome"])

st.session_state.setdefault("sets", [new_set()])
st.session_state.setdefault("current_set", 0)
st.session_state.setdefault("current_server", st.session_state.get("player_name", "選手A"))
st.session_state.setdefault("serve_counter", 0)
st.session_state.setdefault("match_over", False)

def ensure_columns():
    cols = ["Rally", "Server", "Winner", "ServeType", "Outcome"]
    st.session_state.sets = [df.reindex(columns=cols) for df in st.session_state.sets]

def get_full_df():
    dfs = [
        df.assign(Set=i + 1)
        for i, df in enumerate(st.session_state.sets)
        if not df.empty
    ]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

if not st.session_state.get("_loaded", False):
    load_state()
    ensure_columns()
    st.session_state._loaded = True

# ── Player Settings ─────────────────────────────────────────────────────────
st.session_state.setdefault("player_name", "選手A")
st.session_state.setdefault("opponent_name", "対戦相手")
with st.expander("選手設定", expanded=(st.session_state.player_name == "選手A")):
    p = st.text_input("自分側", st.session_state.player_name)
    o = st.text_input("相手側", st.session_state.opponent_name)
    if st.button("保存", key="save_names"):
        st.session_state.player_name = p.strip() or "選手A"
        st.session_state.opponent_name = o.strip() or "対戦相手"
        st.session_state.current_server = st.session_state.player_name
        st.session_state.serve_counter = 0
        save_state()
        st.experimental_rerun()

P, O = st.session_state.player_name, st.session_state.opponent_name
players = [P, O]

SERVE_TYPES = [
    "順回転サーブ（横/上）", "順回転サーブ（下回転）",
    "バックハンド（横/上）", "バックハンド（下回転）",
    "巻き込み（横/上）",     "巻き込み（下回転）",
    "しゃがみ込み（横/上）", "しゃがみ込み（下回転）",
    "YG（横/上）",           "YG（下回転）",
]
OUT_S = ["サービスエース","3球目攻撃","ラリー得点","サーブミス","ラリー失点","その他得点","その他失点"]
OUT_R = ["レシーブエース","ラリー得点","レシーブミス","ラリー失点","その他得点","その他失点"]
WIN_S  = {"サービスエース","3球目攻撃","ラリー得点","その他得点"}
WIN_R  = {"レシーブエース","ラリー得点","その他得点"}

# ── Main UI ─────────────────────────────────────────────────────────────────
st.subheader("TT Analyzer α版")

# セット切替
c1, c2 = st.columns([1,1])
c1.markdown(f"**現在セット:** {st.session_state.current_set+1}")
if c2.button("新しいセット"):
    st.session_state.sets.append(new_set())
    st.session_state.current_set += 1
    st.session_state.current_server = P
    st.session_state.serve_counter   = 0
    st.session_state.match_over      = False
    save_state()
    st.experimental_rerun()

# ラリー登録
def register_rally():
    srv     = st.session_state.server_radio
    stype   = st.session_state.serve_type_radio
    outcome = st.session_state.outcome_radio
    if outcome == "--":
        return

    df = st.session_state.sets[st.session_state.current_set]
    # winner 判定
    winner = P if ((srv == P and outcome in WIN_S) or (srv == O and outcome in WIN_R)) else O

    # 次のラリー番号
    rn_max = pd.to_numeric(df["Rally"], errors="coerce").max()
    next_id = int(rn_max) + 1 if pd.notna(rn_max) else 1

    df.loc[len(df)] = [next_id, srv, winner, stype, outcome]

    # サーブ切替・セット終了判定
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

# 入力ウィジェット
srv_idx = players.index(st.session_state.current_server)
st.radio("サーバー", players, index=srv_idx, key="server_radio")
st.radio("サーブタイプ", SERVE_TYPES, key="serve_type_radio")
st.radio(
    "結果",
    ["--"] + (OUT_S if st.session_state.server_radio == P else OUT_R),
    horizontal=True,
    key="outcome_radio",
    on_change=register_rally
)

# スコアボード
df0 = st.session_state.sets[st.session_state.current_set]
p_pts, o_pts = (df0["Winner"]==P).sum(), (df0["Winner"]==O).sum()

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

if st.button("データをリセット"):
    reset_all()

# セット一覧
overview = [
    {"セット": i+1, P:(df["Winner"]==P).sum(), O:(df["Winner"]==O).sum()}
    for i, df in enumerate(st.session_state.sets)
]
st.dataframe(pd.DataFrame(overview), hide_index=True, use_container_width=True)

# チャート & CSV & AI分析
full = get_full_df()
if not full.empty:
    # （チャート部分は省略して必要な箇所を記述してください）
    csv = full.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    ts = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d_%H%M")

    st.download_button("📥 CSVダウンロード", csv, f"TTAnalyzer_{ts}.csv", "text/csv")

    if st.button("🤖 AI分析"):
        prompt = (
            f"あなたは卓球コーチです。{P}のラリー別データです。"
            "次セットの戦術アドバイスを5点で箇条書きしてください。\n\n"
            + full.to_csv(index=False)
        )
        model = genai.GenerativeModel("gemini-2.0-flash")
        res   = model.generate_content(prompt)
        st.session_state.analysis = res.text

    if st.session_state.get("analysis"):
        st.markdown("##### 📝 AIによる改善ポイント")
        st.write(st.session_state.analysis)

st.caption("© 2025 TT Analyzer α版")
