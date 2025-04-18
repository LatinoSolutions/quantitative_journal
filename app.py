# -----------------------  app.py  -----------------------
import streamlit as st
import pandas as pd, numpy as np
import plotly.express as px, plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import gspread

# ------------------------------------------------------------------
# 1) Configuración inicial
# ------------------------------------------------------------------
st.set_page_config(page_title="Quantitative Journal – Ingreso / KPIs",
                   layout="wide")

scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(
            st.secrets["quantitative_journal"], scopes=scope)
gc  = gspread.authorize(creds)
ws  = gc.open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE"
      ).worksheet("sheet1")

# ---------- Fila‑1 (19 columnas A‑S) ----------
HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios",
    "Post-Analysis","EOD","ErrorCategory","Resolved",
    "LossTradeReviewURL","IdeaMissedURL","IsIdeaOnly"          # <‑‑ NUEVA
]

# ------------------------------------------------------------------
# 2) Utilidades
# ------------------------------------------------------------------
def get_all():
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and "Fecha" in df and "Hora" in df:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")
    return df

def calculate_r(net_usd, acct=60000, rpct=0.25):
    risk = acct*(rpct/100)
    return round(float(net_usd)/risk, 2) if risk else 0

def append_trade(d):
    ws.append_row([d.get(c,"") for c in HEADER])

def update_row(idx, d):                     # idx 0‑based
    sheet_row = idx + 2                     # + header
    ws.update(f"A{sheet_row}:S{sheet_row}",
              [[d.get(c,"") for c in HEADER]])

# ------------------------------------------------------------------
df = get_all()
st.title("Quantitative Journal  ·  Registro & Métricas")

# ================================================================
#  SECCIÓN 1 · Registrar un trade
# ================================================================
with st.expander("➕ Registrar trade", expanded=False):
    c1,c2 = st.columns(2)
    with c1:
        fecha  = st.date_input("Fecha").strftime("%Y-%m-%d")
        hora   = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.text_input("Symbol", value="EURUSD")
        ttype  = st.selectbox("Type", ["Long","Short"])
        volume = st.number_input("Volume (lotes)", 0.0, step=0.01)
        result = st.selectbox("Resultado", ["Win","Loss","BE"])
    with c2:
        gross  = st.number_input("Gross USD (antes comisión)", 0.0, step=0.01)
        screenshot = st.text_input("Screenshot URL")
        comments   = st.text_area("Comentarios")
        post_an    = st.text_area("Post‑Analysis")
        eod_link   = st.text_input("EOD (link Canva)")
        err_cat    = st.text_input("Error Category")
        resolved   = st.checkbox("¿Error Resuelto?", False)
        ltr_urls   = st.text_input("LossTradeReviewURL(s)  (separa con coma)")
        missed_urls= st.text_input("IdeaMissedURL(s)")
        is_idea_only = st.checkbox("¿Sólo idea / Miedito?", value=False)

    # ---- Cálculos USD / BE ----
    commission = volume*4.0
    if result == "BE":
        gross = commission                        # BE ⇒ neto 0
    net_usd = gross - commission
    r_value = calculate_r(net_usd)

    # ---- Si es Miedito, forzamos montos en 0 y resultado "Miedito" ----
    if is_idea_only:
        gross = commission = net_usd = r_value = 0.0
        result = "Miedito"

    if st.button("Agregar Trade"):
        trade = dict(zip(HEADER, [
            fecha,hora,symbol,ttype,volume,result,
            gross,commission,net_usd,r_value,screenshot,comments,post_an,
            eod_link,err_cat,"Yes" if resolved else "No",
            ltr_urls, missed_urls,
            "Yes" if is_idea_only else "No"
        ]))
        append_trade(trade)
        st.success("✔️ Trade agregado")
        df = get_all()

# ================================================================
#  SECCIÓN 2 · KPIs y Visualizaciones
# ================================================================
with st.expander("📊 Métricas / KPIs", expanded=False):
    if df.empty:
        st.info("Aún no hay trades.")
    else:
        # --------‑ filtra sólo trades reales ---------
        df_real = df[df["IsIdeaOnly"] != "Yes"].copy()
        df_real["USD"] = pd.to_numeric(df_real["USD"], errors="coerce")

        total   = len(df_real)
        wins    = (df_real["Win/Loss/BE"]=="Win").sum()
        losses  = (df_real["Win/Loss/BE"]=="Loss").sum()
        be_tr   = (df_real["Win/Loss/BE"]=="BE").sum()
        win_rt  = round(100*wins/total,2) if total else 0
        gross_p = df_real[df_real["USD"]>0]["USD"].sum()
        gross_l = df_real[df_real["USD"]<0]["USD"].sum()
        net_p   = df_real["USD"].sum()
        prof_fac= round(abs(gross_p/gross_l),2) if gross_l else 0
        payoff  = round(df_real[df_real["USD"]>0]["USD"].mean() /
                        abs(df_real[df_real["USD"]<0]["USD"].mean()),2) if losses else 0

        initial_cap  = 60000
        goal_usd     = initial_cap*0.14
        curr_eq      = initial_cap + net_p
        pct_change   = round(100*(curr_eq-initial_cap)/initial_cap,2)
        usd_to_goal  = goal_usd - net_p
        pct_to_goal  = round(100*usd_to_goal/initial_cap,2) if usd_to_goal>0 else 0

        risk_amt = initial_cap*0.0025
        total_R  = round(net_p/risk_amt,2)
        R_to_goal= round(usd_to_goal/risk_amt,2) if usd_to_goal>0 else 0
        trades13 = max(0,int(np.ceil(R_to_goal/3))) if R_to_goal>0 else 0
        trades14 = max(0,int(np.ceil(R_to_goal/4))) if R_to_goal>0 else 0
        trades15 = max(0,int(np.ceil(R_to_goal/5))) if R_to_goal>0 else 0

        # ----- Display -----
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Total Trades", total)
        k2.metric("Win Rate", f"{win_rt}%")
        k3.metric("Profit Factor", prof_fac)
        k4.metric("Payoff ratio", payoff)

        k5,k6,k7,k8 = st.columns(4)
        k5.metric("Net Profit",  f"{round(net_p,2)} USD")
        k6.metric("Equity actual", f"{round(curr_eq,2)} USD", f"{pct_change}%")
        k7.metric("Meta +14 %", f"{round(goal_usd,2)} USD")
        k8.metric("Faltan", f"{round(usd_to_goal,2)} USD", f"{pct_to_goal}%")

        k9,k10,k11,k12 = st.columns(4)
        k9.metric("R acumuladas", total_R)
        k10.metric("R faltantes", R_to_goal)
        k11.metric("Trades 1:3", trades13)
        k12.metric("Trades 1:4 / 1:5", f"{trades14} | {trades15}")

        # Win/Loss/BE pie
        st.plotly_chart(
            px.pie(names=["Win","Loss","BE"],
                   values=[wins,losses,be_tr],
                   title="Distribución Win/Loss/BE"),
            use_container_width=True)

        # Equity curve
        df_sorted = df_real.sort_values("Datetime")
        df_sorted["Equity"] = initial_cap + df_sorted["USD"].cumsum()
        hwm = df_sorted["Equity"].cummax()
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df_sorted["Datetime"], y=df_sorted["Equity"],
                                    mode="lines", name="Equity"))
        fig_eq.add_trace(go.Scatter(x=df_sorted["Datetime"], y=hwm,
                                    mode="lines", name="High‑Water Mark",
                                    line=dict(dash="dash", color="green")))
        fig_eq.update_layout(title="Evolución de Equity", showlegend=True)
        st.plotly_chart(fig_eq, use_container_width=True)

# ================================================================
#  SECCIÓN 3 · Editar / Borrar
# ================================================================
with st.expander("✏️ Editar / Borrar trades", expanded=False):
    if df.empty:
        st.info("No hay trades.")
    else:
        idx = st.number_input("Índice (0‑based)", 0, df.shape[0]-1, step=1)
        sel = df.loc[idx].to_dict()
        st.json(sel)

        # ------- borrar -------
        if st.button("Borrar este trade"):
            df = df.drop(idx).reset_index(drop=True)
            ws.clear(); ws.append_row(HEADER)
            ws.append_rows(df[HEADER].values.tolist())
            st.success("Trade borrado ✔️")
            df = get_all()

        # ------- editar -------
        with st.form("edit_form"):
            st.write("Editar campos:")
            new_vals = {}
            for col in ["Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
                        "Gross_USD","Screenshot","Comentarios","Post-Analysis",
                        "EOD","ErrorCategory","LossTradeReviewURL","IdeaMissedURL"]:
                if col in ["Comentarios","Post-Analysis"]:
                    new_vals[col] = st.text_area(col, sel.get(col,""))
                elif col in ["LossTradeReviewURL","IdeaMissedURL"]:
                    new_vals[col] = st.text_input(col, sel.get(col,""))
                elif col == "Volume":
                    new_vals[col] = st.number_input(col, 0.0, step=0.01,
                                                    value=float(sel.get(col,0)))
                else:
                    new_vals[col] = st.text_input(col, sel.get(col,""))

            res_chk  = st.checkbox("Resolved", value=(sel["Resolved"].lower()=="yes"))
            idea_chk = st.checkbox("¿Sólo idea / Miedito?",
                                   value=(sel["IsIdeaOnly"]=="Yes"))
            submitted = st.form_submit_button("Guardar cambios")

            if submitted:
                vol   = float(new_vals["Volume"])
                gross = float(new_vals["Gross_USD"])
                comm  = vol*4.0
                if new_vals["Win/Loss/BE"] == "BE":
                    gross = comm
                net   = gross - comm
                r_val = calculate_r(net)

                sel.update(new_vals)
                sel["Gross_USD"]  = gross
                sel["Commission"] = comm
                sel["USD"]        = net
                sel["R"]          = r_val
                sel["Resolved"]   = "Yes" if res_chk else "No"
                sel["IsIdeaOnly"] = "Yes" if idea_chk else "No"
                if idea_chk:
                    sel["Win/Loss/BE"] = "Miedito"
                    sel["Gross_USD"] = sel["Commission"] = sel["USD"] = sel["R"] = 0

                update_row(idx, sel)
                st.success("Cambios guardados ✔️")
                df = get_all()

# ================================================================
#  SECCIÓN 4 · Historial
# ================================================================
with st.expander("📜 Historial de trades", expanded=False):
    st.dataframe(df, use_container_width=True)
