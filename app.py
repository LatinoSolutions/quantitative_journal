# ----------------------  app.py  ----------------------
import streamlit as st, pandas as pd, numpy as np, math
import plotly.express as px, plotly.graph_objects as go
from datetime import datetime, timedelta       # ← añade esta línea
from google.oauth2.service_account import Credentials
import gspread

# ------------------ Config ---------------------------
st.set_page_config("Quantitative Journal – Ingreso / KPIs", layout="wide")

creds = Credentials.from_service_account_info(
            st.secrets["quantitative_journal"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
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

# ---------- Verificar / fijar cabecera (21 columnas) ----------
first_row = ws.row_values(1)
if first_row != HEADER:
    ws.update('A1', [HEADER])        # solo re-escribe fila 1, no borra datos
    st.toast("Cabecera actualizada en Google Sheet ✔️", icon="📑")


# -------------- helpers ------------------------------
def get_all():
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")
    return df

def calc_r(usd, cap=60000, pct=0.25):
    risk = cap*(pct/100)
    return round(float(usd)/risk, 2) if risk else 0

# ---------- actualizar UNA fila sin tocar tus notas ----------
def update_row(idx, d):          # idx es 0-based
    sheet_row = idx + 2          # + cabecera
    row_vals  = [d.get(c, "") for c in HEADER]
    ws.update(f"A{sheet_row}:U{sheet_row}", [row_vals])   # A-U = 21 cols

def trades_needed(r_faltante, RR):
    return max(0, math.ceil(r_faltante/RR))

# -------------- Fix old BE ---------------------------
def fix_be(df):
    changed=False
    for i,row in df.iterrows():
        if row["Win/Loss/BE"]=="BE" and float(row["USD"])==0:
            comm=float(row["Commission"]) or float(row["Volume"])*4.0
            df.at[i,"Gross_USD"]=0
            df.at[i,"Commission"]=comm
            df.at[i,"USD"]=-comm
            df.at[i,"R"]=calc_r(-comm)
            changed=True
    if changed:
        ws.clear(); ws.append_row(HEADER)
        ws.append_rows(df[HEADER].values.tolist())
    return df

# -------------- Load data ----------------------------
df = fix_be(get_all())
st.title("Quantitative Journal · Registro & Métricas")

# ====================================================
# 1) Registrar trade
# ====================================================
with st.expander("➕ Registrar trade", expanded=False):
    c1,c2 = st.columns(2)
    with c1:
        fecha  = st.date_input("Fecha").strftime("%Y-%m-%d")
        hora   = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.text_input("Symbol","EURUSD")
        ttype  = st.selectbox("Type",["Long","Short"])
        vol    = st.number_input("Volume (lots)",0.0,step=0.01)
        result = st.selectbox("Resultado",["Win","Loss","BE"])
    with c2:
        gross  = st.number_input("Gross USD (antes comisión)",0.0,step=0.01)
        screenshot = st.text_input("Screenshot URL")
        comments   = st.text_area("Comentarios")
        post_an    = st.text_area("Post-Analysis")
        eod_link   = st.text_input("EOD (link Canva)")
        err_cat    = st.text_input("Error Category")
        resolved   = st.checkbox("¿Error Resuelto?",False)
        ltr_urls   = st.text_input("LossTradeReviewURL(s)")
        missed_urls= st.text_input("IdeaMissedURL(s)")
        idea_only  = st.checkbox("¿Sólo idea / Miedito?",False)

    comm   = vol*4.0
    if result=="BE":  # BE -> net negativo comisión
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

# ====================================================
# 2) KPIs
# ====================================================
with st.expander("📊 Métricas / KPIs", expanded=False):
    if df.empty:
        st.info("Sin datos.")
    else:
        df_real = df[df["IsIdeaOnly"]!="Yes"].copy()
        df_real["USD"]=pd.to_numeric(df_real["USD"],errors="coerce")

        total=len(df_real)
        wins=(df_real["Win/Loss/BE"]=="Win").sum()
        losses=(df_real["Win/Loss/BE"]=="Loss").sum()
        be_tr=(df_real["Win/Loss/BE"]=="BE").sum()
        win_rt=round(100*wins/total,2) if total else 0

        gross_p=df_real[df_real["USD"]>0]["USD"].sum()
        gross_l=df_real[df_real["USD"]<0]["USD"].sum()
        net_p=df_real["USD"].sum()
        pf=round(abs(gross_p/gross_l),2) if gross_l else 0
        payoff=round(df_real[df_real["USD"]>0]["USD"].mean() /
                     abs(df_real[df_real["USD"]<0]["USD"].mean()),2) if losses else 0

        initial=60000
        equity=initial+net_p
        pct_eq=round(100*(equity-initial)/initial,2)

        # Fase objetivos
        goal1=initial*1.08
        goal2=initial*1.13
        usd_to1=max(0,goal1-equity)
        usd_to2=max(0,goal2-equity)
        pct_to1=round(100*usd_to1/initial,2) if usd_to1>0 else 0
        pct_to2=round(100*usd_to2/initial,2) if usd_to2>0 else 0

        # draw-down
        dd_limit=initial*0.90
        dist_dd=equity-dd_limit
        trades_left=math.ceil(dist_dd/(equity*0.0025)) if dist_dd>0 else 0

        risk_amt=initial*0.0025
        total_R=round(net_p/risk_amt,2)
        R_to1=round(usd_to1/risk_amt,2) if usd_to1>0 else 0
        R_to2=round(usd_to2/risk_amt,2) if usd_to2>0 else 0

        # Trades 1:x para cada fase
        t13f1,tr14f1,tr15f1 = trades_needed(R_to1,3), trades_needed(R_to1,4), trades_needed(R_to1,5)
        t13f2,tr14f2,tr15f2 = trades_needed(R_to2,3), trades_needed(R_to2,4), trades_needed(R_to2,5)

        be_saved=((df_real["Win/Loss/BE"]=="BE")&(df_real["BEOutcome"]=="SavedCapital")).sum()
        be_missed=((df_real["Win/Loss/BE"]=="BE")&(df_real["BEOutcome"]=="MissedOpportunity")).sum()

        # ---- Display ----
        k1,k2,k3,k4=st.columns(4)
        k1.metric("Total Trades",total)
        k2.metric("Win Rate",f"{win_rt}%")
        k3.metric("Profit Factor",pf)
        k4.metric("Payoff ratio",payoff)

        k5,k6,k7,k8=st.columns(4)
        k5.metric("Net Profit",f"{round(net_p,2)} USD")
        k6.metric("Equity",f"{round(equity,2)} USD",f"{pct_eq}%")
        k7.metric("Dist. DD -10 %",f"{round(dist_dd,2)} USD",
                  f"{round(100*dist_dd/initial,2)} %")
        k8.metric("Trades p/ quemar cuenta",trades_left)

        k9,k10,k11,k12=st.columns(4)
        k9.metric("Fase 1 +8 %",f"{round(usd_to1,2)} USD",f"{pct_to1}%")
        k10.metric("Fase 2 +13 %",f"{round(usd_to2,2)} USD",f"{pct_to2}%")
        k11.metric("Trades 1:3 (F1|F2)",f"{t13f1} | {t13f2}")
        k12.metric("Trades 1:4|1:5 (F1|F2)",
                   f"{tr14f1}/{tr15f1} | {tr14f2}/{tr15f2}")

        st.write(f"**BE Saved:** {be_saved}   |   **BE Missed:** {be_missed}")

        st.plotly_chart(px.pie(names=["Win","Loss","BE"],
                               values=[wins,losses,be_tr],
                               title="Distribución Win/Loss/BE"),
                        use_container_width=True)

        df_real=df_real.sort_values("Datetime")
        df_real["Equity"]=initial+df_real["USD"].cumsum()
        hwm=df_real["Equity"].cummax()
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=df_real["Datetime"],y=df_real["Equity"],
                                 mode="lines",name="Equity"))
        fig.add_trace(go.Scatter(x=df_real["Datetime"],y=hwm,
                                 mode="lines",name="HWM",
                                 line=dict(dash="dash",color="green")))
        fig.update_layout(title="Evolución Equity",showlegend=True)
        st.plotly_chart(fig,use_container_width=True)

# ====================================================
# 3) Editar / Borrar   (idéntico al enviado antes)
# ====================================================
with st.expander("✏️ Editar / Borrar trades", expanded=False):
    if df.empty:
        st.info("No hay trades.")
    else:
        idx=st.number_input("Índice (0-based)",0,df.shape[0]-1,step=1)
        sel=df.loc[idx].to_dict()
        st.json(sel)

        if st.button("Borrar este trade"):
            df=df.drop(idx).reset_index(drop=True)
            ws.clear(); ws.append_row(HEADER)
            ws.append_rows(df[HEADER].values.tolist())
            st.success("Trade borrado ✔️")
            df=get_all()

        with st.form("edit"):
            edits={}
            for col in ["Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
                        "Gross_USD","Screenshot","Comentarios","Post-Analysis",
                        "EOD","ErrorCategory","LossTradeReviewURL","IdeaMissedURL"]:
                if col in ["Comentarios","Post-Analysis"]:
                    edits[col]=st.text_area(col,sel.get(col,""))
                elif col in ["LossTradeReviewURL","IdeaMissedURL"]:
                    edits[col]=st.text_input(col,sel.get(col,""))
                elif col=="Volume":
                    edits[col]=st.number_input(col,0.0,step=0.01,
                                               value=float(sel.get(col,0)))
                else:
                    edits[col]=st.text_input(col,sel.get(col,""))
            res_chk=st.checkbox("Resolved",sel["Resolved"].lower()=="yes")
            idea_chk=st.checkbox("¿Sólo idea / Miedito?",sel["IsIdeaOnly"]=="Yes")
            be_out=sel.get("BEOutcome","")
            if sel["Win/Loss/BE"]=="BE":
                be_out=st.selectbox("BE Outcome",["","SavedCapital","MissedOpportunity"],
                                    index=["","SavedCapital","MissedOpportunity"].index(be_out))

            if st.form_submit_button("Guardar"):
                vol=float(edits["Volume"]); gross=float(edits["Gross_USD"])
                comm=vol*4.0
                if edits["Win/Loss/BE"]=="BE": gross=0
                net=gross-comm; r_val=calc_r(net)

                sel.update(edits)
                sel["Gross_USD"]=gross; sel["Commission"]=comm
                sel["USD"]=net; sel["R"]=r_val
                sel["Resolved"]="Yes" if res_chk else "No"
                sel["IsIdeaOnly"]="Yes" if idea_chk else "No"
                sel["BEOutcome"]=be_out
                if idea_chk:
                    sel["Win/Loss/BE"]="Miedito"
                    sel["Gross_USD"]=sel["Commission"]=sel["USD"]=sel["R"]=0

                update_row(idx,sel)
                st.success("Cambios guardados ✔️")
                df=get_all()

# ====================================================
# 4) Historial
# ====================================================
with st.expander("📜 Historial", expanded=False):
    st.dataframe(df,use_container_width=True)

# =========================================================
# 5) Auditoría y corrección automática  (una sola vez)
# =========================================================
with st.expander("🛠️  Auditoría de integridad (BE & Net)", expanded=False):

    if st.button("➤  Escanear hoja"):
        issues = []
        for i,row in df.iterrows():
            vol  = float(row["Volume"] or 0)
            comm = float(row["Commission"] or 0)
            gross= float(row["Gross_USD"] or 0)
            usd  = float(row["USD"] or 0)
            if row["Win/Loss/BE"]=="BE":
                if not (abs(gross) < 0.01 and abs(usd + comm) < 0.01):
                    issues.append((i,row["Fecha"],row["Hora"],"BE incorrecto"))
            elif row["Win/Loss/BE"] in ["Win","Loss"]:
                if abs(usd - (gross-comm)) > 0.01:
                    issues.append((i,row["Fecha"],row["Hora"],"Neto≠gross-com"))
        if not issues:
            st.success("✅  Todos los trades cuadran.")
        else:
            st.warning(f"{len(issues)} fila(s) con problema:")
            st.table(pd.DataFrame(issues,
                     columns=["idx","Fecha","Hora","Detalle"]))

    if st.button("⚠️  Corregir automáticamente BE incorrectos"):
        fixed = 0
        for i,row in df.iterrows():
            if row["Win/Loss/BE"]=="BE" and abs(float(row["USD"])) < 0.01:
                vol  = float(row["Volume"] or 0)
                comm = round(vol*4.0,2)
                df.at[i,"Gross_USD"]  = 0
                df.at[i,"Commission"] = comm
                df.at[i,"USD"]        = -comm
                df.at[i,"R"]          = calc_r(-comm)
                fixed += 1
        if fixed:
            ws.clear(); ws.append_row(HEADER)
            ws.append_rows(df[HEADER].values.tolist())
            st.success(f"Arregladas {fixed} filas BE; recarga la app.")
        else:
            st.info("No había BE con USD = 0 para corregir.")
            
# =========================================================
# 6) Importar log MT5 (DumpTrades) – reconciliación por Ticket
# =========================================================
import csv, io, re, pandas as pd
with st.expander("📥 Importar log MT5 (DumpTrades)", expanded=False):

    raw = st.text_area("Pega aquí las líneas completas del log DumpTrades",
                       height=220)

    if st.button("➤ Analizar log"):
        if not raw.strip():
            st.warning("Nada pegado."); st.stop()

        # ---------- Parseo del texto ----------
        rows = []
        for line in raw.strip().splitlines():
            if "DumpTrades" in line and ")" in line:
                line = re.split(r"\)\s+", line, maxsplit=1)[-1]
            parts = line.split(",")
            if len(parts) == 7 and parts[0] != "DATE":
                rows.append(parts)

        if not rows:
            st.error("No se detectó CSV válido."); st.stop()

        df_log = pd.DataFrame(rows, columns=
            ["Fecha","Hora","Ticket","Symbol","Volume","TypeCode","Profit"])
        df_log["Fecha"]  = pd.to_datetime(df_log["Fecha"]).dt.strftime("%Y-%m-%d")
        df_log["Hora"]   = (pd.to_datetime(df_log["Hora"])
                            - pd.Timedelta(hours=1)).dt.strftime("%H:%M:%S")
        df_log["Volume"] = df_log["Volume"].astype(float)
        df_log["Profit"] = df_log["Profit"].astype(float)
        df_log["Ticket"] = df_log["Ticket"].astype(str)

        if "Ticket" not in df.columns:
            df["Ticket"] = ""

        # ---------- Cruce inicial por Ticket ----------
        merged = df_log.merge(df, on="Ticket", how="left", indicator=True,
                              suffixes=("_log","_sheet"))

        faltan  = merged[merged["_merge"] == "left_only"].copy()
        diffval = merged[(merged["_merge"] == "both") &
                         (abs(merged["Profit"]-merged["USD"]) > 0.01)].copy()

        st.write(f"Trades en log: {len(df_log)}")
        st.write(f"Faltan en hoja: {len(faltan)}")
        st.write(f"Profit distinto: {len(diffval)}")

        if not faltan.empty:
            st.dataframe(faltan, height=220)

        if not diffval.empty:
            st.dataframe(diffval, height=220)

        # ---------- Botón para sincronizar ----------
        if st.button("⚠️  Sincronizar hoja"):
            added = fixed = replaced = 0

            # Helper: símbolo columna correcto
            def sym(df_any): return "Symbol_log" if "Symbol_log" in df_any.columns else "Symbol"

            # ------- 1) procesar 'faltan' -------
            for _, r in faltan.iterrows():
                vol  = float(r["Volume"])
                comm = round(vol * 4.0, 2)
                usd  = r["Profit"]
                gross = usd + comm
                res  = "Win" if usd > 0 else "Loss"
                if abs(usd + comm) < 0.01:
                    res = "BE"; gross = 0

                # Buscar fila sin Ticket pero misma Fecha-Symbol-Volume
                match = df[(df["Ticket"] == "") &
                           (df["Fecha"]  == r["Fecha"]) &
                           (df["Symbol"] == r[sym(faltan)]) &
                           (abs(df["Volume"] - vol) < 0.001)]

                if not match.empty:
                    i = match.index[0]      # REEMPLAZAR
                    df.at[i,"Ticket"]      = r["Ticket"]
                    df.at[i,"Volume"]      = vol
                    df.at[i,"Gross_USD"]   = gross
                    df.at[i,"Commission"]  = comm
                    df.at[i,"USD"]         = usd
                    df.at[i,"R"]           = calc_r(usd)
                    df.at[i,"Win/Loss/BE"] = res
                    replaced += 1
                else:                       # INSERTAR nuevo
                    trade = dict(zip(HEADER, [
                        r["Fecha"], r["Hora"], r[sym(faltan)],
                        "Long" if int(r["TypeCode"]) % 2 else "Short",
                        vol, r["Ticket"], res, gross, comm, usd,
                        calc_r(usd), "", "", "", "", "", "No",
                        "","",""
                    ]))
                    ws.append_row([trade[c] for c in HEADER])
                    added += 1

            # ------- 2) corregir Profit distintos -------
            for _, r in diffval.iterrows():
                idx = df[df["Ticket"] == r["Ticket"]].index
                if idx.size:
                    i = idx[0]
                    vol  = float(r["Volume"])
                    comm = round(vol * 4.0, 2)
                    usd  = r["Profit"]
                    gross = usd + comm
                    df.at[i,"Volume"]      = vol
                    df.at[i,"Gross_USD"]   = gross
                    df.at[i,"Commission"]  = comm
                    df.at[i,"USD"]         = usd
                    df.at[i,"R"]           = calc_r(usd)
                    df.at[i,"Win/Loss/BE"] = ("Win" if usd>0 else
                                              ("BE" if abs(usd)<0.01 else "Loss"))
                    fixed += 1

            # ------- 3) guardar si hubo cambios -------
            if added or fixed or replaced:
                ws.clear(); ws.append_row(HEADER)
                ws.append_rows(df[HEADER].values.tolist())

            st.success(f"Nuevos: {added}  |  Reemplazados: {replaced}  |  "
                       f"Correcciones: {fixed}.  Pulsa Rerun.")

# =========================================================
#  🩹 Balance Adjustment (parche rápido)
# =========================================================
with st.expander("🩹 Balance Adjustment", expanded=False):

    current_net = round(df["USD"].sum(), 2) if not df.empty else 0.0
    st.write(f"Net Profit actual en el journal: **{current_net} USD**")

    mt5_value = st.number_input(
        "Escribe aquí el Net Profit exacto que ves en MT5",
        value=current_net, step=0.01, format="%.2f")

    diff = round(mt5_value - current_net, 2)
    st.write(f"Diferencia a ajustar: **{diff:+} USD**")

    if st.button("➕ Crear ajuste") and diff != 0:
        today = datetime.today().strftime("%Y-%m-%d")
        now   = datetime.today().strftime("%H:%M:%S")

        adj_row = dict(zip(HEADER, [
            today, now, "ADJ", "Adj", 0.0, "",           # Fecha Hora Symbol Type Volume Ticket
            "Adj", diff, 0.0, diff,                      # Win/Loss/BE Gross Commission USD
            calc_r(diff), "", "", "", "Adjustment", "",  # R y columnas de notas
            "No", "", "", ""                             # Resolved, IdeaOnly, BEOutcome
        ]))

        ws.append_row([adj_row[c] for c in HEADER])
        st.success("Fila de ajuste añadida ✔️ — pulsa *Rerun* para ver métricas actualizadas.")
