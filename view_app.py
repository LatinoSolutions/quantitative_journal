# -------------- view_app.py  (Galería) --------------
import streamlit as st, pandas as pd
from google.oauth2.service_account import Credentials
import gspread
from streamlit.runtime.media_file_storage import MediaFileStorageError

st.set_page_config("Quantitative Journal – Galería", layout="wide")

# ---------- Conexión ----------
creds = Credentials.from_service_account_info(
    st.secrets["quantitative_journal"],
    scopes=["https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"])
ws = gspread.authorize(creds)\
        .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")\
        .worksheet("sheet1")
df = pd.DataFrame(ws.get_all_records())

if "Datetime" not in df.columns and {"Fecha","Hora"} <= set(df.columns):
    df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")

if df.empty:
    st.info("No hay datos."); st.stop()

# ---------- Filtros barra lateral ----------
st.sidebar.header("Filtros")

# Resultado
result_choice = st.sidebar.radio("Resultado", ["Todos","Win","Loss","BE"], index=0)

# Categoría de error con marcar / desmarcar
all_cats = sorted([c for c in df["ErrorCategory"].unique() if c])
st.sidebar.write("Error Category")
btn_col1, btn_col2 = st.sidebar.columns(2)
if btn_col1.button("Todo"):
    sel_cats = all_cats.copy()
elif btn_col2.button("Ninguno"):
    sel_cats = []
else:
    sel_cats = st.sidebar.multiselect("", all_cats, default=all_cats)

# Estado Resolved
state_choice = st.sidebar.radio(
    "Estado", ["Todos","Solo sin Resolver","Solo Resueltos"], index=0)

# ---------- Aplicar filtros ----------
if result_choice != "Todos":
    df = df[df["Win/Loss/BE"] == result_choice]

if sel_cats:
    df = df[df["ErrorCategory"].isin(sel_cats)]

if state_choice == "Solo sin Resolver":
    df = df[(df["Win/Loss/BE"]=="Loss") & (df["Resolved"]!="Yes")]
elif state_choice == "Solo Resueltos":
    df = df[(df["Win/Loss/BE"]=="Loss") & (df["Resolved"]=="Yes")]

st.title("🖼️ Galería de Trades")

# ---------- Parámetros de visualización ----------
PER_PAGE, N_COLS = 12, 3
max_page = max(1, (len(df)-1)//PER_PAGE + 1)
page = st.sidebar.number_input("Página", 1, max_page, step=1)
st.sidebar.write(f"{len(df)} tarjeta(s) · {max_page} página(s)")

sub = df.sort_values("Datetime", ascending=False).iloc[
        (page-1)*PER_PAGE : page*PER_PAGE]

# ---------- Helper imagen ----------
def safe_image(url, width=200):
    try:
        st.image(url, width=width)
    except MediaFileStorageError:
        st.write("🖼️ (sin vista previa)")

# ---------- Tarjeta ----------
def card(row):
    img_url = row["Screenshot"].split(",")[0].strip() if row["Screenshot"] else ""
    caption = (f"{row['Fecha']} | {row['Win/Loss/BE']} | "
               f"{row['USD']:+,.2f} USD | {row['R']:+.2f} R")
    safe_image(img_url, width=200); st.caption(caption)

    with st.expander("Detalle"):
        for col in ["Symbol","Type","Volume","ErrorCategory",
                    "SecondTradeValid?","Comentarios","Post-Analysis",
                    "EOD","Resolved"]:
            st.write(f"**{col}**: {row[col]}")
        if row["Screenshot"]:
            st.markdown(f"[Screenshot]({row['Screenshot']})")
        if row["LossTradeReviewURL"]:
            st.markdown(f"[Review]({row['LossTradeReviewURL']})")

# ---------- Render ----------
cols = st.columns(N_COLS)
for i, (_, r) in enumerate(sub.iterrows()):
    with cols[i % N_COLS]:
        card(r)
