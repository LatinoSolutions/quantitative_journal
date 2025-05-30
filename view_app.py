# -------------- view_app.py  (Galería avanzada) --------------
import streamlit as st, pandas as pd, re
from google.oauth2.service_account import Credentials
import gspread
from streamlit.runtime.media_file_storage import MediaFileStorageError

st.set_page_config("Quantitative Journal – Galería", layout="wide")

# ---------- Conexión a Google Sheets ----------
creds = Credentials.from_service_account_info(
    st.secrets["quantitative_journal"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)
ws = (
    gspread.authorize(creds)
    .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")
    .worksheet("sheet1")
)
df = pd.DataFrame(ws.get_all_records())

# ----- Datetime si no existe -----
if "Datetime" not in df.columns and {"Fecha", "Hora"} <= set(df.columns):
    df["Datetime"] = pd.to_datetime(
        df["Fecha"] + " " + df["Hora"], errors="coerce"
    )

if df.empty:
    st.info("No hay datos."); st.stop()

# ----- Añadimos índice original para referencia -----
df = df.reset_index(names="Idx")

# ---------- Barra lateral ----------
st.sidebar.header("Filtros")

# A) Resultado
result_choice = st.sidebar.radio(
    "Resultado", ["Todos", "Win", "Loss", "BE"], index=0
)

# B) Estado Resolved
state_choice = st.sidebar.radio(
    "Estado", ["Todos", "Solo sin Resolver", "Solo Resueltos"], index=0
)

# C) ErrorCategory checklist con contador
all_cats = sorted([c for c in df["ErrorCategory"].unique() if c])
btn1, btn2 = st.sidebar.columns(2)
if btn1.button("Todo"):
    st.session_state["sel_cats"] = all_cats.copy()
elif btn2.button("Ninguno"):
    st.session_state["sel_cats"] = []
sel_cats = st.sidebar.multiselect(
    "Error Category",
    [f"{c} ({(df['ErrorCategory']==c).sum()})" for c in all_cats],
    default=[
        f"{c} ({(df['ErrorCategory']==c).sum()})"
        for c in st.session_state.get("sel_cats", all_cats)
    ],
)
# quitar el contador para comparar:
sel_cats = [re.sub(r" \(\d+\)$", "", c) for c in sel_cats]

# D) Búsqueda texto
search_txt = st.sidebar.text_input("Buscar (texto libre)")

# E) Tamaño miniatura
size_choice = st.sidebar.radio("Miniatura", ["S", "M", "L"], index=1)
thumb_w = dict(S=120, M=200, L=260)[size_choice]

# ---------- Aplicar filtros ----------
if result_choice != "Todos":
    df = df[df["Win/Loss/BE"] == result_choice]

if state_choice == "Solo sin Resolver":
    df = df[(df["Win/Loss/BE"] == "Loss") & (df["Resolved"] != "Yes")]
elif state_choice == "Solo Resueltos":
    df = df[(df["Win/Loss/BE"] == "Loss") & (df["Resolved"] == "Yes")]

if sel_cats:
    df = df[df["ErrorCategory"].isin(sel_cats)]

if search_txt:
    pattern = re.escape(search_txt.lower())
    df = df[
        df[["Symbol", "Comentarios", "Post-Analysis", "ErrorCategory"]]
        .apply(lambda row: row.astype(str).str.lower().str.contains(pattern).any(), axis=1)
    ]

if df.empty:
    st.warning("No hay tarjetas que cumplan los filtros.")
    st.stop()

# ---------- Paginación ----------
PER_PAGE, N_COLS = 12, 3
total_rows = len(df)
max_page = max(1, (total_rows - 1) // PER_PAGE + 1)
page = st.session_state.get("gallery_page", 1)

nav1, nav2, nav3, nav4, nav5 = st.columns([1,1,2,1,1])
if nav1.button("⏮"):
    page = 1
if nav2.button("◀"):
    page = max(1, page - 1)
if nav4.button("▶"):
    page = min(max_page, page + 1)
if nav5.button("⏭"):
    page = max_page

page = nav3.number_input("Página", 1, max_page, value=page, step=1)
st.session_state["gallery_page"] = page

st.sidebar.write(f"{total_rows} tarjeta(s) · {max_page} página(s)")

sub = df.sort_values("Datetime", ascending=False).iloc[
    (page - 1) * PER_PAGE : page * PER_PAGE
]

# ---------- Helper: imagen segura ----------
def safe_image(url, width=200):
    try:
        st.image(url, width=width)
    except MediaFileStorageError:
        st.write("🖼️ (sin vista previa)")

# ---------- Render tarjeta ----------
def card(row):
    img_url = row["Screenshot"].split(",")[0].strip() if row["Screenshot"] else ""
    caption = (
        f"#{row['Idx']} · {row['Fecha']} · {row['Win/Loss/BE']} · "
        f"{row['USD']:+,.2f} USD · {row['R']:+.2f} R"
    )
    safe_image(img_url, width=thumb_w)
    st.caption(caption)

    with st.expander("Detalle"):
        for col in [
            "Symbol",
            "Type",
            "Volume",
            "ErrorCategory",
            "SecondTradeValid?",
            "Comentarios",
            "Post-Analysis",
            "EOD",
            "Resolved",
        ]:
            st.write(f"**{col}**: {row[col]}")
        if row["Screenshot"]:
            st.markdown(f"[Screenshot]({row['Screenshot']})")
        if row["LossTradeReviewURL"]:
            st.markdown(f"[Review]({row['LossTradeReviewURL']})")

# ---------- Distribución en columnas ----------
cols = st.columns(N_COLS)
for i, (_, r) in enumerate(sub.iterrows()):
    with cols[i % N_COLS]:
        card(r)
