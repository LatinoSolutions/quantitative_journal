# ------------------ app.py  (Ingreso + KPIs) ------------------
import streamlit as st, pandas as pd, numpy as np, math
import plotly.express as px, plotly.graph_objects as go
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

# ---------- Configuración y conexión ----------
st.set_page_config("Quantitative Journal – Ingreso / KPIs", layout="wide")

creds = Credentials.from_service_account_info(
            st.secrets["quantitative_journal"],
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"])
ws = gspread.authorize(creds) \
        .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE") \
        .worksheet("sheet1")

HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Ticket","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios",
    "Post-Analysis","EOD","ErrorCategory","Resolved",
    "LossTradeReviewURL","IdeaMissedURL","IsIdeaOnly","BEOutcome"
]

first_row = ws.row_values(1)
if first_row != HEADER:
    ws.update('A1', [HEADER])
    st.toast("Cabecera alineada ✔️", icon="📑")

# ---------- Helpers ----------
def true_commission(volume: float) -> float:
    return round(volume * 4.0, 2)

def calc_r(net_usd: float, acct: float = 60000, risk_pct: float = 0.25) -> float:
    risk = acct * (risk_pct / 100)
    return round(net_usd / risk, 2) if risk else 0

def get_all() -> pd.DataFrame:
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and "Fecha" in df and "Hora" in df:
        df["Datetime"] = pd.to_datetime(df["Fecha"] + " " + df["Hora"], errors="coerce")
    return df

def update_row(idx, d):
    ws.update(f"A{idx+2}:U{idx+2}", [[d.get(c,"") for c in HEADER]])

df = get_all()
initial_cap = 60000

st.title("Quantitative Journal  ·  Registro & Métricas")

# ======================================================
# 1 · Registrar un trade
# ======================================================
with st.expander("➕ Registrar trade", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        fecha  = st.date_input("Fecha").strftime("%Y-%m-%d")
        hora   = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.text_input("Symbol", value="EURUSD")
        ttype  = st.selectbox("Type", ["Long", "Short"])
        volume = st.number_input("Volume (lotes)", 0.0, step=0.01)
        result = st.selectbox("Resultado", ["Win", "Loss", "BE"])
    with c2:
        gross      = st.number_input("Gross USD (antes comisión, ±)", 0.0, step=0.01)
        screenshot = st.text_input("Screenshot URL")
        comments   = st.text_area("Comentarios")
        post_an    = st.text_area("Post-Analysis")
        eod_link   = st.text_input("EOD (link Canva)")
        err_cat    = st.text_input("Error Category")
        resolved   = st.checkbox("¿Error Resuelto?", False)
        ltr_urls   = st.text_input("LossTradeReviewURL(s) (coma)")
        missed_url = st.text_input("IdeaMissedURL(s) (coma)")

    commission = true_commission(volume)
    if result in ("Loss", "BE") and gross > 0:
        gross = -abs(gross)

    if result == "BE":
        net_usd = -commission
        gross   = 0.0
    else:
        net_usd = gross - commission

    r_value = calc_r(net_usd)

    if st.button("Agregar Trade"):
        trade = {
            "Fecha": fecha, "Hora": hora, "Symbol": symbol, "Type": ttype,
            "Volume": volume, "Ticket": "",
            "Win/Loss/BE": result, "Gross_USD": gross,
            "Commission": commission, "USD": net_usd, "R": r_value,
            "Screenshot": screenshot, "Comentarios": comments,
            "Post-Analysis": post_an, "EOD": eod_link,
            "ErrorCategory": err_cat,
            "Resolved": "Yes" if resolved else "No",
            "LossTradeReviewURL": ltr_urls, "IdeaMissedURL": missed_url,
            "IsIdeaOnly": "", "BEOutcome": ""
        }
        ws.append_row([trade.get(c,"") for c in HEADER])
        st.success("✔️ Trade agregado")
        df = get_all()

# ======================================================
# 2 · KPI panel
# ======================================================
with st.expander("📊 Métricas / KPIs", expanded=False):
    if df.empty:
        st.info("Aún no hay trades.")
    else:
        # Excluir ajustes fantasma
        df_real = df[df["Win/Loss/BE"] != "Adj"].copy()
        df_real["USD"] = pd.to_numeric(df_real["USD"], errors="coerce")
        total   = len(df_real)
        wins    = (df_real["Win/Loss/BE"]=="Win").sum()
        losses  = (df_real["Win/Loss/BE"]=="Loss").sum()
        be_tr   = (df_real["Win/Loss/BE"]=="BE").sum()

        win_rate = round(100*wins/total,2) if total else 0
        gross_p  = df_real[df_real["USD"]>0]["USD"].sum()
        gross_l  = df_real[df_real["USD"]<0]["USD"].sum()
        net_p    = df_real["USD"].sum()
        commissions_sum = df_real["Commission"].sum()
        prof_factor = round(abs(gross_p/gross_l),2) if gross_l else 0
        payoff = (round(df_real[df_real["USD"]>0]["USD"].mean() /
                        abs(df_real[df_real["USD"]<0]["USD"].mean()),2)
                  if losses else 0)

        # DD & objetivos
        current_eq = initial_cap + net_p
        pct_change = round(100*(current_eq-initial_cap)/initial_cap,2)
        dd_limit   = initial_cap * 0.90
        dist_dd    = current_eq - dd_limit
        trades_to_burn = math.ceil(abs(dist_dd)/(initial_cap*0.0025)) if dist_dd<0 else math.ceil(dist_dd/(initial_cap*0.0025))

        f1_target  = initial_cap * 1.08
        f2_target  = initial_cap * 1.13
        dist_f1    = f1_target - current_eq
        dist_f2    = f2_target - current_eq
        f1_done    = dist_f1 <= 0
        risk_amt   = initial_cap*0.0025
        r_total    = round(net_p/risk_amt,2)
        r_f1       = round(max(dist_f1,0)/risk_amt,2)
        r_f2       = round(max(dist_f2,0)/risk_amt,2)
        t13_f1 = max(0,int(np.ceil(r_f1/3)))
        t13_f2 = max(0,int(np.ceil(r_f2/3)))
        t14_f1 = max(0,int(np.ceil(r_f1/4)))
        t14_f2 = max(0,int(np.ceil(r_f2/4)))
        t15_f1 = max(0,int(np.ceil(r_f1/5)))
        t15_f2 = max(0,int(np.ceil(r_f2/5)))

        # ---------- layout 3 x 7 ----------
        k = st.columns(7)
        k[0].metric("Total Trades", total)
        k[1].metric("Win Rate", f"{win_rate}%")
        k[2].metric("Profit Factor", prof_factor)
        k[3].metric("Payoff ratio", payoff)
        k[4].metric("Net Profit", f"{net_p:.2f} USD")
        k[5].metric("Gross Profit", f"{gross_p:.2f}")
        k[6].metric("Gross Loss", f"{gross_l:.2f}")

        k = st.columns(7)
        k[0].metric("Comisiones", f"{commissions_sum:.2f} USD")
        k[1].metric("Equity", f"{current_eq:.2f}", f"{pct_change}%")
        k[2].metric("Dist. DD −10%", f"{dist_dd:+.2f}", "")
        k[3].metric("Trades p/quemar", trades_to_burn)
        k[4].metric("R acumuladas", r_total)
        k[5].metric("BE count", be_tr)
        k[6].metric("Win/Loss/BE", f"{wins}/{losses}/{be_tr}")

        k = st.columns(7)
        k[0].metric("Fase 1 +8%", ("✅" if f1_done else f"{dist_f1:.2f} USD"), 
                    None if f1_done else f"{r_f1} R")
        k[1].metric("Fase 2 +13%", f"{dist_f2:.2f} USD", f"{r_f2} R")
        k[2].metric("Trades 1:3 F1", t13_f1)
        k[3].metric("Trades 1:3 F2", t13_f2)
        k[4].metric("Trades 1:4/5 F1", f"{t14_f1}/{t15_f1}")
        k[5].metric("Trades 1:4/5 F2", f"{t14_f2}/{t15_f2}")
        k[6].write(" ")

        # Pie chart
        st.plotly_chart(px.pie(names=["Win","Loss","BE"],
                               values=[wins,losses,be_tr]), use_container_width=True)

        # Equity curve
        df_sorted = df_real.sort_values("Datetime")
        df_sorted["Equity"] = initial_cap + df_sorted["USD"].cumsum()
        st.plotly_chart(px.line(df_sorted, x="Datetime", y="Equity",
                                title="Equity curve"), use_container_width=True)

# ======================================================
# 3 · Balance Adjustment
# ======================================================
with st.expander("🩹 Balance Adjustment", expanded=False):
    current_net = round(df[df["Win/Loss/BE"]!="Adj"]["USD"].sum(),2)
    st.write(f"Net Profit actual (sin ADJ): **{current_net} USD**")
    mt5_val = st.number_input("Net Profit según MT5", current_net, step=0.01, format="%.2f")
    diff = round(mt5_val - current_net, 2)
    st.write(f"Diferencia a ajustar: **{diff:+} USD**")

    if st.button("➕ Crear ajuste") and diff!=0:
        today = datetime.today().strftime("%Y-%m-%d")
        now   = datetime.today().strftime("%H:%M:%S")
        adj = dict(zip(HEADER, [
            today, now, "ADJ","Adj",0.0,"","Adj", diff,0.0, diff,
            calc_r(diff), "","","Adjustment","","","No","","","",
            ""  # BEOutcome
        ]))
        ws.append_row([adj.get(c,"") for c in HEADER])
        st.success("Ajuste añadido; Rerun para ver métricas.")

# ======================================================
# 4 · Historial
# ======================================================
with st.expander("📜 Historial de trades", expanded=False):
    st.dataframe(df, use_container_width=True)

# ======================================================
# 5 · Editar / Borrar
# ======================================================
with st.expander("✏️ Editar / Borrar", expanded=False):
    if df.empty:
        st.info("No hay trades.")
    else:
        idx = st.number_input("Índice (0-based)", 0, df.shape[0]-1, step=1)
        sel = df.loc[idx].to_dict()
        st.json(sel)

        if st.button("Borrar este trade"):
            df = df.drop(idx).reset_index(drop=True)
            ws.clear(); ws.append_row(HEADER)
            ws.append_rows(df[HEADER].values.tolist())
            st.success("Trade borrado.")
            df = get_all()

        with st.form("edit"):
            new_vals={}
            for col in ["Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
                        "Gross_USD","Screenshot","Comentarios","Post-Analysis",
                        "EOD","ErrorCategory","LossTradeReviewURL","IdeaMissedURL"]:
                if col in ("Comentarios","Post-Analysis"):
                    new_vals[col] = st.text_area(col, sel[col])
                elif col=="Volume":
                    new_vals[col] = st.number_input(col, 0.0, step=0.01, value=float(sel[col]))
                else:
                    new_vals[col] = st.text_input(col, sel[col])
            resolved_chk = st.checkbox("Resolved", value=(sel["Resolved"].lower()=="yes"))
            submitted = st.form_submit_button("Guardar")
            if submitted:
                vol      = float(new_vals["Volume"])
                comm     = true_commission(vol)
                gross    = float(new_vals["Gross_USD"])
                if new_vals["Win/Loss/BE"] in ("Loss","BE") and gross>0:
                    gross = -abs(gross)
                net_usd = -comm if new_vals["Win/Loss/BE"]=="BE" else gross-comm
                sel.update(new_vals)
                sel["Commission"]       = comm
                sel["Gross_USD"]        = gross if new_vals["Win/Loss/BE"]!="BE" else 0.0
                sel["USD"]              = net_usd
                sel["R"]                = calc_r(net_usd)
                sel["Resolved"]         = "Yes" if resolved_chk else "No"
                update_row(idx, sel)
                st.success("Guardado.")
                df = get_all()
# ------------------------------------------------------ end app.py
