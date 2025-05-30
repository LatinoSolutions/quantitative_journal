# -------------- view_app.py --------------
import streamlit as st, pandas as pd, re
from google.oauth2.service_account import Credentials
import gspread
from streamlit.runtime.media_file_storage import MediaFileStorageError

st.set_page_config("Quantitative Journal – Galería", layout="wide")

# ---------- Cargar datos ----------
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

df = df.reset_index(names="Idx")   # índice visible

# ---------- Sidebar filtros ----------
st.sidebar.header("Filtros")

res_choice = st.sidebar.radio("Resultado", ["Todos","Win","Loss","BE"], 0)
state_choice = st.sidebar.radio("Estado",
    ["Todos","Solo sin Resolver","Solo Resueltos"], 0)

all_cats = sorted([c for c in df["ErrorCategory"].unique() if c])
c1, c2 = st.sidebar.columns(2)
if c1.button("Todo"):     st.session_state["sel_cats"] = all_cats.copy()
if c2.button("Ninguno"):  st.session_state["sel_cats"] = []
sel_cats = st.sidebar.multiselect(
    "Error Category",
    [f"{c} ({(df['ErrorCategory']==c).sum()})" for c in all_cats],
    default=[
        f"{c} ({(df['ErrorCategory']==c).sum()})"
        for c in st.session_state.get("sel_cats", all_cats)
    ])
sel_cats = [re.sub(r" \(\d+\)$","",c) for c in sel_cats]

search_txt = st.sidebar.text_input("Buscar (#idx, texto…)")

thumb_size = st.sidebar.radio("Miniatura", ["S","M","L"], 1)
thumb_w = dict(S=120,M=200,L=260)[thumb_size]

# ---------- Aplicar filtros ----------
if res_choice != "Todos":
    df = df[df["Win/Loss/BE"] == res_choice]

if state_choice == "Solo sin Resolver":
    df = df[(df["Win/Loss/BE"]=="Loss") & (df["Resolved"]!="Yes")]
elif state_choice == "Solo Resueltos":
    df = df[(df["Win/Loss/BE"]=="Loss") & (df["Resolved"]=="Yes")]

if sel_cats and len(sel_cats)!=len(all_cats):
    df = df[(df["ErrorCategory"].isin(sel_cats)) | (df["ErrorCategory"]=="")]

if search_txt:
    pat = re.escape(search_txt.lstrip("#").lower())
    df = df[
        df["Idx"].astype(str).str.fullmatch(pat) |
        df[["Symbol","Comentarios","Post-Analysis","ErrorCategory"]]
          .apply(lambda r: r.astype(str).str.lower()
                 .str.contains(pat).any(), axis=1)
    ]

if df.empty:
    st.warning("No hay tarjetas que cumplan los filtros."); st.stop()

# ---------- Paginación ----------
PER_PAGE, N_COLS = 12, 3
total_rows = len(df)
max_page   = max(1,(total_rows-1)//PER_PAGE+1)

# Página por defecto = última (trades más recientes)
page = st.session_state.get("gallery_page", max_page)
page = max(1,min(page,max_page))    # límite

nav1, nav2, nav3, nav4, nav5 = st.columns([1,1,2,1,1])
if nav1.button("⏮"): page = 1
if nav2.button("◀"): page = max(1,page-1)
if nav4.button("▶"): page = min(max_page,page+1)
if nav5.button("⏭"): page = max_page
page = nav3.number_input("Página",1,max_page,value=page,step=1,key="page_in")
st.session_state["gallery_page"]=page

st.sidebar.write(f"{total_rows} tarjeta(s) · {max_page} página(s)")

sub = df.sort_values("Datetime",ascending=False)\
        .iloc[(page-1)*PER_PAGE : page*PER_PAGE]

# ---------- helpers ----------
def safe_image(url,w): 
    try: st.image(url,width=w)
    except MediaFileStorageError: st.write("🖼️")

def card(r):
    img = r["Screenshot"].split(",")[0].strip() if r["Screenshot"] else ""
    caption = (f"#{r['Idx']} · {r['Fecha']} · {r['Win/Loss/BE']} · "
               f"{r['USD']:+,.2f} USD · {r['R']:+.2f} R")
    safe_image(img,thumb_w); st.caption(caption)
    st.markdown(f"**SecondTradeValid?**: {r['SecondTradeValid?']}")

    with st.expander("Detalle"):
        for col in ["Symbol","Type","Volume","ErrorCategory",
                    "SecondTradeValid?","Comentarios","Post-Analysis",
                    "EOD","Resolved"]:
            st.write(f"**{col}**: {r[col]}")
        if r["Screenshot"]:          st.markdown(f"[Screenshot]({r['Screenshot']})")
        if r["LossTradeReviewURL"]:  st.markdown(f"[Review]({r['LossTradeReviewURL']})")

# ---------- render ----------
cols = st.columns(N_COLS)
for i,(_,row) in enumerate(sub.iterrows()):
    with cols[i%N_COLS]: card(row)
