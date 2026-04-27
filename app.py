import streamlit as st
import sqlite3
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from streamlit.runtime.scriptrunner import get_script_run_ctx

# --- Database Setup ---
DB_NAME = "game_state.db"

@st.cache_resource
def setup_game():
    """Initializes DB and wipes lobby once per server start."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS lobby (
            slot INTEGER PRIMARY KEY,
            session_id TEXT,
            move TEXT,
            status TEXT
        )
    ''')
    # Initialize 2 slots if empty
    c.execute("SELECT COUNT(*) FROM lobby")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO lobby (slot, session_id, move, status) VALUES (1, NULL, NULL, 'empty')")
        c.execute("INSERT INTO lobby (slot, session_id, move, status) VALUES (2, NULL, NULL, 'empty')")
    else:
        # If slots exist, just clear them (this is the startup reset)
        c.execute("UPDATE lobby SET session_id = NULL, move = NULL, status = 'empty'")
    
    conn.commit()
    conn.close()
    return True

def get_lobby():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM lobby ORDER BY slot", conn)
    conn.close()
    # Replace NaN with None (object type ensures it stays None)
    return df.astype(object).where(pd.notnull(df), None)

def claim_slot(slot, session_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # First, check if this session already owns any slot
    c.execute("SELECT slot FROM lobby WHERE session_id = ?", (session_id,))
    existing_slot = c.fetchone()
    
    if existing_slot:
        if existing_slot[0] == slot:
            conn.close()
            return True # Already owns this slot
        else:
            conn.close()
            return False # Owns the OTHER slot, can't claim this one
            
    # If not assigned, check if the target slot is free
    c.execute("SELECT session_id FROM lobby WHERE slot = ?", (slot,))
    current_occupant = c.fetchone()[0]
    
    success = False
    if current_occupant is None or current_occupant == "":
        c.execute("UPDATE lobby SET session_id = ?, status = 'occupied' WHERE slot = ?", (session_id, slot))
        conn.commit()
        success = True
    
    conn.close()
    return success

def submit_move(slot, move):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE lobby SET move = ?, status = 'ready' WHERE slot = ?", (move, slot))
    conn.commit()
    conn.close()

def reset_game():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE lobby SET session_id = NULL, move = NULL, status = 'empty'")
    conn.commit()
    conn.close()

# --- App Logic ---
st.set_page_config(page_title="Multiplayer RPS Arena", page_icon="🪨", layout="centered")

# Custom CSS for Vibe Polish
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stButton>button {
        width: 100%;
        height: 80px;
        font-size: 24px;
        border-radius: 15px;
        transition: transform 0.2s;
    }
    .stButton>button:hover {
        transform: scale(1.05);
    }
    .player-card {
        padding: 20px;
        border-radius: 15px;
        border: 2px solid #333;
        text-align: center;
        background: rgba(255, 255, 255, 0.05);
    }
    .win-banner {
        color: #00ff00;
        font-size: 40px;
        font-weight: bold;
        text-shadow: 0 0 10px #00ff00;
    }
</style>
""", unsafe_allow_html=True)

setup_game()
st_autorefresh(interval=1000, key="datarefresh")

ctx = get_script_run_ctx()
session_id = ctx.session_id if ctx else "unknown"

# --- Bouncer & Role Logic ---
def check_my_role(data, sid):
    if not data.empty:
        if data.iloc[0]['session_id'] == sid: return 1
        if data.iloc[1]['session_id'] == sid: return 2
    return None

# Get role from URL
query_params = st.query_params
requested_role = query_params.get("role", None)

lobby_data = get_lobby()
my_role = check_my_role(lobby_data, session_id)

# If not assigned and a role is requested, try to claim it
if my_role is None and requested_role in ["1", "2"]:
    target_slot = int(requested_role)
    if claim_slot(target_slot, session_id):
        st.success(f"Slot {target_slot} claimed!")
        st.rerun() 
    else:
        st.error(f"⛔ Slot {target_slot} is already taken!")

lobby_data = get_lobby()
# Safe debug print for terminal tracking
p1_id = str(lobby_data.iloc[0]['session_id'])[:5] if lobby_data.iloc[0]['session_id'] else "None"
p2_id = str(lobby_data.iloc[1]['session_id'])[:5] if lobby_data.iloc[1]['session_id'] else "None"
print(f"Lobby State: P1={p1_id} ({lobby_data.iloc[0]['move']}), P2={p2_id} ({lobby_data.iloc[1]['move']})")
p1 = lobby_data.iloc[0]
p2 = lobby_data.iloc[1]
my_role = check_my_role(lobby_data, session_id)

# --- Gameplay Dashboard ---
st.title("🪨 Rock Paper Scissors Arena ✂️")
st.caption(f"My Session: `{session_id[:8]}...` | My Role: `{f'Player {my_role}' if my_role else 'Spectator'}`")

# Arena Dashboard
col1, mid, col2 = st.columns([1, 0.4, 1])

with col1:
    st.markdown(f'<div class="player-card">', unsafe_allow_html=True)
    st.subheader("Player 1")
    if p1['session_id']:
        st.success("🟢 Connected")
        if p1['move']:
            st.info("✅ Move Locked")
        else:
            st.warning("⏳ Thinking...")
    else:
        st.markdown("⚪ Waiting...")
    st.markdown('</div>', unsafe_allow_html=True)

with mid:
    st.markdown("<h1 style='text-align: center; margin-top: 40px;'>VS</h1>", unsafe_allow_html=True)

with col2:
    st.markdown(f'<div class="player-card">', unsafe_allow_html=True)
    st.subheader("Player 2")
    if p2['session_id']:
        st.success("🟢 Connected")
        if p2['move']:
            st.info("✅ Move Locked")
        else:
            st.warning("⏳ Thinking...")
    else:
        st.markdown("⚪ Waiting...")
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# Result Calculation
# BOTH players must be connected AND both must have moves
p1_ready = p1['session_id'] and p1['move']
p2_ready = p2['session_id'] and p2['move']
can_resolve = p1_ready and p2_ready

if can_resolve:
    m1 = p1['move']
    m2 = p2['move']
    
    st.subheader("BATTLE RESULTS!")
    res_col1, res_col2 = st.columns(2)
    res_col1.metric("P1 Move", m1)
    res_col2.metric("P2 Move", m2)
    
    if m1 == m2:
        st.info("🤝 It's a DRAW!")
    elif (m1 == "Rock" and m2 == "Scissors") or \
         (m1 == "Paper" and m2 == "Rock") or \
         (m1 == "Scissors" and m2 == "Paper"):
        st.markdown('<p class="win-banner">🏆 PLAYER 1 WINS!</p>', unsafe_allow_html=True)
        st.balloons()
    else:
        st.markdown('<p class="win-banner">🏆 PLAYER 2 WINS!</p>', unsafe_allow_html=True)
        st.balloons()
else:
    # Handshaking status
    with st.status("Syncing with Database...", expanded=True) as status:
        if not p1['session_id'] or not p2['session_id']:
            st.write("Waiting for both players to join...")
        elif not p1['move'] or not p2['move']:
            st.write("Waiting for moves...")
        status.update(label="Handshaking Active", state="running")

# --- Player View ---
if my_role:
    st.header(f"🎮 YOU ARE PLAYER {my_role}")
    my_data = p1 if my_role == 1 else p2
    
    if not my_data['move']:
        st.write("Pick your move:")
        c1, c2, c3 = st.columns(3)
        if c1.button("🪨 Rock", key="rock_btn"):
            submit_move(my_role, "Rock")
            st.rerun()
        if c2.button("📄 Paper", key="paper_btn"):
            submit_move(my_role, "Paper")
            st.rerun()
        if c3.button("✂️ Scissors", key="scissors_btn"):
            submit_move(my_role, "Scissors")
            st.rerun()
    else:
        st.info(f"You chose **{my_data['move']}**. Waiting for opponent...")

# --- Game Master Reset ---
st.divider()
with st.expander("🛡️ Game Master"):
    if st.button("🚨 NUCLEAR RESET"):
        reset_game()
        st.rerun()

st.caption(f"Session ID: {session_id}")
