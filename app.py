# ------------------------  app.py  ------------------------
import streamlit as st, pandas as pd, numpy as np
import plotly.express as px, plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import gspread, math

# ---------------------------------------------------------
st.set_page_config("Quantitative Journal – Ingreso / KPIs", layout="wide")

creds = Credentials.from_service_account_info(
            st.secrets["quantitative_journal"],
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"])
ws = gspread.authorize(creds)\
        .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")\
        .worksheet("sheet1")

# ----- Header (20 col A‑T) -----
HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios",
    "Post-Analysis","EOD","ErrorCategory","Resolved",
    "LossTradeReviewURL","IdeaMissedURL","IsIdeaOnly","BEOutcome"
]

# ---------- helpers ----------
def get_all():
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")
    return df

def calc_r(usd, cap=60000, pct=0.25):      # 0.25 % riesgo
    risk_amt = cap*(pct/100)
    return round(float(usd)/risk_amt, 2) if risk_amt else 0

def update_row(idx, d):
    ws.update(f"A{idx+2}:T{idx+2}", [[d.get(c,"") for c in HEADER]])

# ---------- BE auto‑fix ----------
def fix_be_rows(df):
    changed = False
    for i,row in df.iterrows():
        if row["Win/Loss/BE"]=="BE" and float(row["USD"])==0:
            comm = float(row["Commission"]) or float(row["Volume"])*4.0
            df.at[i,"Gross_USD"]  = 0
            df.at[i,"Commission"] = comm
            df.at[i,"USD"]        = -comm
            df.at[i,"R"]          = calc_r(-comm)
            changed = True
    if changed:
        ws.clear(); ws.append_row(HEADER)
        ws.append_rows(df[HEADER].values.tolist())
    return df

# ---------------------------------------------------------
df = get_all()
df = fix_be_rows(df)            # corregir BE antiguos si es necesario
st.title("Quantitative Journal · Registro & Métricas")

# ========================================================
# 1) Registrar trade
# ========================================================
with st.expander("➕ Registrar trade", expanded=False):
    c1,c2 = st.columns(2)
    with c1:
        fecha  = st.date_input("Fecha").strftime("%Y-%m-%d")
        hora   = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.text_input("Symbol","EURUSD")
        ttype  = st.selectbox("Type",["Long","Short"])
        vol    = st.number_input("Volume (lotes)",0.0,step=0.01)
        result = st.selectbox("Resultado",["Win","Loss","BE"])
    with c2:
        gross  = st.number_input("Gross USD (antes comisión)",0.0,step=0.01)
        screenshot = st.text_input("Screenshot URL")
        comments   = st.text_area("Comentarios")
        post_an    = st.text_area("Post‑Analysis")
        eod_link   = st.text_input("EOD (link Canva)")
        err_cat    = st.text_input("Error Category")
        resolved   = st.checkbox("¿Error Resuelto?",False)
        ltr_urls   = st.text_input("LossTradeReviewURL(s)")
        missed_urls= st.text_input("IdeaMissedURL(s)")
        idea_only  = st.checkbox("¿Sólo idea / Miedito?",False)

    comm   = vol*4.0
    if result=="BE":
        gross = 0
    net_usd = gross - comm
    r_val   = calc_r(net_usd)

    if idea_only:
        result="Miedito"; gross=comm=net_usd=r_val=0

    if st.button("Agregar Trade"):
        trade = dict(zip(HEADER, [
            fecha,hora,symbol,ttype,vol,result,
            gross,comm,net_usd,r_val,screenshot,comments,post_an,
            eod_link,err_cat,"Yes" if resolved else "No",
            ltr_urls, missed_urls,"Yes" if idea_only else "No",""
        ]))
        ws.append_row([trade[c] for c in HEADER])
        st.success("Trade agregado ✔️")
        df = get_all()

# ========================================================
# 2) KPIs (ignoran Miedito)
# ========================================================
with st.expander("📊 Métricas / KPIs", expanded=False):
    if df.empty:
        st.info("Sin datos.")
    else:
        df_real = df[df["IsIdeaOnly"]!="Yes"].copy()
        df_real["USD"] = pd.to_numeric(df_real["USD"], errors="coerce")

        total=wins=losses=be_tr=0
        if not df_real.empty:
            total  = len(df_real)
            wins   = (df_real["Win/Loss/BE"]=="Win").sum()
            losses = (df_real["Win/Loss/BE"]=="Loss").sum()
            be_tr  = (df_real["Win/Loss/BE"]=="BE").sum()

        win_rt = round(100*wins/total,2) if total else 0
        gross_p = df_real[df_real["USD"]>0]["USD"].sum()
        gross_l = df_real[df_real["USD"]<0]["USD"].sum()
        net_p   = df_real["USD"].sum()
        pf      = round(abs(gross_p/gross_l),2) if gross_l else 0
        payoff  = round(df_real[df_real["USD"]>0]["USD"].mean() /
                        abs(df_real[df_real["USD"]<0]["USD"].mean()),2) if losses else 0

        initial = 60000
        eq      = initial + net_p
        pct_eq  = round(100*(eq-initial)/initial,2)

        # --- objetivos fase 1 & 2 ---
        goal1 = initial*1.08          # +8 %
        goal2 = initial*1.13          # +13 %
        usd_to_1 = max(0, goal1 - eq)
        usd_to_2 = max(0, goal2 - eq)
        pct_to_1 = round(100*usd_to_1/initial,2) if usd_to_1>0 else 0
        pct_to_2 = round(100*usd_to_2/initial,2) if usd_to_2>0 else 0

        # --- draw‑down -10 % ---
        dd_limit = initial*0.90
        dist_dd  = eq - dd_limit
        trades_left = math.ceil(dist_dd / (eq*0.0025)) if dist_dd>0 else 0

        # --- R stats ---
        risk_amt = initial*0.0025
        total_R  = round(net_p/risk_amt,2)
        R_to_1   = round(usd_to_1/risk_amt,2) if usd_to_1>0 else 0
        R_to_2   = round(usd_to_2/risk_amt,2) if usd_to_2>0 else 0

        # --- BE Outcome counts ---
        be_saved  = ((df_real["Win/Loss/BE"]=="BE") &
                     (df_real["BEOutcome"]=="SavedCapital")).sum()
        be_missed = ((df_real["Win/Loss/BE"]=="BE") &
                     (df_real["BEOutcome"]=="MissedOpportunity")).sum()

        # --- Display KPIs ---
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Total Trades", total)
        k2.metric("Win Rate", f"{win_rt}%")
        k3.metric("Profit Factor", pf)
        k4.metric("Payoff ratio", payoff)

        k5,k6,k7,k8 = st.columns(4)
        k5.metric("Net Profit", f"{round(net_p,2)} USD")
        k6.metric("Equity", f"{round(eq,2)} USD", f"{pct_eq}%")
        k7.metric("Dist. DD ‑10 %", f"{round(dist_dd,2)} USD",
                  f"{round(100*dist_dd/initial,2)} %")
        k8.metric("Trades p/ quemar cuenta", trades_left)

        k9,k10,k11,k12 = st.columns(4)
        k9.metric("Fase 1 +8 %", f"{round(usd_to_1,2)} USD", f"{pct_to_1}%")
        k10.metric("Fase 2 +13 %", f"{round(usd_to_2,2)} USD", f"{pct_to_2}%")
        k11.metric("R acumuladas", total_R)
        k12.metric("R faltantes F1|F2", f"{R_to_1} | {R_to_2}")

        st.write(f"**BE Saved:** {be_saved}   |   **BE Missed:** {be_missed}")

        st.plotly_chart(px.pie(names=["Win","Loss","BE"],
                               values=[wins,losses,be_tr],
                               title="Distribución Win/Loss/BE"),
                        use_container_width=True)

        df_real = df_real.sort_values("Datetime")
        df_real["Equity"] = initial + df_real["USD"].cumsum()
        hwm = df_real["Equity"].cummax()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_real["Datetime"],y=df_real["Equity"],
                                 mode="lines",name="Equity"))
        fig.add_trace(go.Scatter(x=df_real["Datetime"],y=hwm,
                                 mode="lines",name="High‑Water Mark",
                                 line=dict(dash="dash",color="green")))
        fig.update_layout(title="Evolución de Equity",showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

# ========================================================
# 3) Editar / Borrar (sección intacta con BEOutcome y Miedito)
# ========================================================
with st.expander("✏️ Editar / Borrar trades", expanded=False):
    if df.empty:
        st.info("No hay trades.")
    else:
        idx = st.number_input("Índice (0‑based)", 0, df.shape[0]-1, step=1)
        sel = df.loc[idx].to_dict()
        st.json(sel)

        if st.button("Borrar este trade"):
            df = df.drop(idx).reset_index(drop=True)
            ws.clear(); ws.append_row(HEADER)
            ws.append_rows(df[HEADER].values.tolist())
            st.success("Trade borrado ✔️")
            df = get_all()

        with st.form("edit"):
            edits={}
            for col in ["Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
                        "Gross_USD","Screenshot","Comentarios","Post-Analysis",
                        "EOD","ErrorCategory","LossTradeReviewURL","IdeaMissedURL"]:
                if col in ["Comentarios","Post-Analysis"]:
                    edits[col]=st.text_area(col, sel.get(col,""))
                elif col in ["LossTradeReviewURL","IdeaMissedURL"]:
                    edits[col]=st.text_input(col, sel.get(col,""))
                elif col=="Volume":
                    edits[col]=st.number_input(col,0.0,step=0.01,
                                               value=float(sel.get(col,0)))
                else:
                    edits[col]=st.text_input(col, sel.get(col,""))
            res_chk  = st.checkbox("Resolved", sel["Resolved"].lower()=="yes")
            idea_chk = st.checkbox("¿Sólo idea / Miedito?", sel["IsIdeaOnly"]=="Yes")
            be_out = sel.get("BEOutcome","")
            if sel["Win/Loss/BE"]=="BE":
                be_out = st.selectbox("BE Outcome",["","SavedCapital",
                                                     "MissedOpportunity"],
                                      index=["","SavedCapital",
                                             "MissedOpportunity"].index(be_out))
            submit = st.form_submit_button("Guardar")
            if submit:
                vol = float(edits["Volume"])
                gross = float(edits["Gross_USD"])
                comm  = vol*4.0
                if edits["Win/Loss/BE"]=="BE":
                    gross=0
                net = gross - comm
                r_val = calc_r(net)

                sel.update(edits)
                sel["Gross_USD"],sel["Commission"],sel["USD"],sel["R"] = gross,comm,net,r_val
                sel["Resolved"]   = "Yes" if res_chk else "No"
                sel["IsIdeaOnly"] = "Yes" if idea_chk else "No"
                sel["BEOutcome"]  = be_out
                if idea_chk:
                    sel["Win/Loss/BE"]="Miedito"
                    sel["Gross_USD"]=sel["Commission"]=sel["USD"]=sel["R"]=0

                update_row(idx, sel)
                st.success("Cambios guardados ✔️")
                df = get_all()

# ========================================================
# 4) Historial
# ========================================================
with st.expander("📜 Historial", expanded=False):
    st.dataframe(df, use_container_width=True)
