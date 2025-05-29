# -------------- view_app.py  (Galería) --------------
import streamlit as st, pandas as pd
from google.oauth2.service_account import Credentials
import gspread, datetime as dt

st.set_page_config("Quantitative Journal – Galería", layout="wide")

# ---------- conexión ----------
creds = Credentials.from_service_account_info(
    st.secrets["quantitative_journal"],
    scopes=["https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"])
ws = gspread.authorize(creds)\
        .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")\
        .worksheet("sheet1")
df = pd.DataFrame(ws.get_all_records())
if df.empty:
    st.info("No hay datos."); st.stop()

df["Fecha_dt"] = pd.to_datetime(df["Fecha"])

# ---------- Filtros ----------
st.sidebar.header("Filtros")

res_filter = st.sidebar.multiselect(
    "Resultado", ["Win","Loss","BE"], default=["Win","Loss","BE"])

date_sel = st.sidebar.date_input("Rango fechas", [])
if isinstance(date_sel, (list, tuple)) and len(date_sel)==2:
    start, end = date_sel
    df = df[(df["Fecha_dt"]>=pd.to_datetime(start)) &
            (df["Fecha_dt"]<=pd.to_datetime(end))]
else:
    start = end = None  # sin filtro

only_pending = st.sidebar.checkbox("Sólo Loss sin Resolver")

if only_pending:
    df = df[(df["Win/Loss/BE"]=="Loss") & (df["Resolved"]!="Yes")]

df = df[df["Win/Loss/BE"].isin(res_filter)]

st.title("🖼️ Galería de Trades")

# ---------- Tarjetas ----------
PER_PAGE = 20
max_page = max(1, (len(df)-1)//PER_PAGE + 1)
page = st.sidebar.number_input("Página", 1, max_page, step=1)
start_i, end_i = (page-1)*PER_PAGE, (page)*PER_PAGE
sub = df.sort_values("Datetime", ascending=False).iloc[start_i:end_i]

def card(row):
    img = row["LossTradeReviewURL"] if row["LossTradeReviewURL"] else row["Screenshot"]
    caption = (f"{row['Fecha']} | {row['Win/Loss/BE']} | "
               f"{row['USD']:+,.2f} USD | {row['R']:+.2f} R")
    st.image(img, width=260, caption=caption)
    with st.expander("Detalle"):
        for col in ["Symbol","Type","Volume","ErrorCategory","Comentarios",
                    "Post-Analysis","EOD","Resolved"]:
            st.write(f"**{col}**: {row[col]}")
        if row["Screenshot"]:
            st.markdown(f"[Abrir Screenshot]({row['Screenshot']})")
        if row["LossTradeReviewURL"]:
            st.markdown(f"[Abrir Review]({row['LossTradeReviewURL']})")

cols = st.columns(4)
for i, (_, r) in enumerate(sub.iterrows()):
    with cols[i % 4]:
        card(r)
