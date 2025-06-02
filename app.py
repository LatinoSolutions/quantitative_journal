# ------------------  app.py  ------------------
import streamlit as st, pandas as pd, numpy as np, math, re
import plotly.express as px, plotly.graph_objects as go
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

# ---------- Conexión ----------
st.set_page_config("Quantitative Journal – Ingreso / KPIs", layout="wide")

creds = Credentials.from_service_account_info(
    st.secrets["quantitative_journal"],
    scopes=["https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"])
ws = gspread.authorize(creds)\
        .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")\
        .worksheet("sheet1")

HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Ticket","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios",
    "Post-Analysis","EOD","ErrorCategory","Resolved","SecondTradeValid?",
    "LossTradeReviewURL","IdeaMissedURL","IsIdeaOnly","BEOutcome"
]
if ws.row_values(1) != HEADER:
    ws.update('A1', [HEADER])

# ---------- Helpers ----------
import math

initial_cap = 60000

def true_commission(vol: float) -> float:
    return round(vol * 4.0, 2)

def calc_r(net: float) -> float:
    risk = initial_cap * 0.0025          # 0.25 %
    return round(net / risk, 2) if risk else 0

def get_all():
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty:
        df["Datetime"] = pd.to_datetime(
            df["Fecha"] + " " + df["Hora"], errors="coerce")
    return df

# --- NUEVO: util para convertir número → letra de columna ---
def col_letter(n: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA, …"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def update_row(i: int, d: dict):
    """Actualiza fila i (0-based) con todas las columnas de HEADER."""
    row  = i + 2                          # +1 por header, +1 índice 0-based
    last = col_letter(len(HEADER))        # calcula la última letra
    ws.update(f"A{row}:{last}{row}",
              [[d.get(c, "") for c in HEADER]])

df = get_all()
st.title("Quantitative Journal · Registro & Métricas")

# ======================================================
# 0 · 📅 Daily Impressions  (ANALYSIS PRE-MARKET)
#     • Usa pestaña "daily_impressions" en el mismo Sheets
#     • Hasta 5 imágenes URL por día, separadas por coma
# ======================================================
with st.expander("📅 Daily Impressions", expanded=False):
    # ---------- cargar / crear hoja ----------
    try:
        ws_imp = ws.spreadsheet.worksheet("daily_impressions")
    except gspread.WorksheetNotFound:
        ws_imp = ws.spreadsheet.add_worksheet("daily_impressions", rows=2000, cols=10)
        ws_imp.append_row(["Date","Impression","Reflection",
                           "IsAccurate","ImageURLs","Tags"])

    df_imp = pd.DataFrame(ws_imp.get_all_records())
    if not df_imp.empty:
        df_imp["Date"] = pd.to_datetime(df_imp["Date"]).dt.date
    else:
        df_imp = pd.DataFrame(columns=["Date","Impression","Reflection",
                                       "IsAccurate","ImageURLs","Tags"])

    # ---------- navegación mensual ----------
    today = datetime.today()
    sel_year  = st.number_input("Año",  2020, 2100, today.year, 1, key="imp_year")
    sel_month = st.number_input("Mes",     1,   12, today.month, 1, key="imp_mon")
    first_day = datetime(sel_year, sel_month, 1).date()
    last_day  = (datetime(sel_year, sel_month, 28) + timedelta(days=4)).date().replace(day=1) - timedelta(days=1)

    # ---------- dibujar calendario ----------
    weekdays = ["Lu","Ma","Mi","Ju","Vi","Sa","Do"]
    st.markdown("#### "
        f"{first_day.strftime('%B').capitalize()} {sel_year}")

    cal = pd.date_range(first_day, last_day, freq="D")
    cal_df = pd.DataFrame({"Date": cal})
    cal_df["Dow"] = cal_df["Date"].dt.weekday              # 0=Lunes
    cal_df["Week"] = (cal_df.index + cal_df.iloc[0]["Dow"]) // 7

    grid = st.columns(7)
    for d, w in enumerate(weekdays):
        grid[d].markdown(f"**{w}**")

    rows = cal_df["Week"].max() + 1
    for r in range(rows):
        cols = st.columns(7)
        for d in range(7):
            cell = cal_df[(cal_df["Week"] == r) & (cal_df["Dow"] == d)]
            if cell.empty: cols[d].write(" ")
            else:
                day = cell.iloc[0]["Date"].date()
                rec  = df_imp[df_imp["Date"] == day]
                bg   = "#f1f1f1" if rec.empty else (
                       "#d4f4d2" if rec.iloc[0]["IsAccurate"]=="Yes" else "#ffd6d6")
                emoji= "" if rec.empty else ("✔️" if rec.iloc[0]["IsAccurate"]=="Yes" else "❌")
                if cols[d].button(f"{day.day} {emoji}",
                                  key=f"day_{day}", help=str(day),
                                  use_container_width=True):
                    st.session_state["imp_modal_day"] = str(day)
                cols[d].markdown(
                    f"<div style='height:4px;background:{bg};border-radius:4px;'></div>",
                    unsafe_allow_html=True)

    # ---------- modal edición ----------
    modal_key = st.session_state.get("imp_modal_day")
    if modal_key:
        day_sel = datetime.strptime(modal_key, "%Y-%m-%d").date()
        rec = df_imp[df_imp["Date"] == day_sel]
        impression   = rec.iloc[0]["Impression"]   if not rec.empty else ""
        reflection   = rec.iloc[0]["Reflection"]   if not rec.empty else ""
        is_accurate  = rec.iloc[0]["IsAccurate"]   if not rec.empty else "N/A"
        image_urls   = rec.iloc[0]["ImageURLs"]    if not rec.empty else ""
        tags         = rec.iloc[0]["Tags"]         if not rec.empty else ""

        with st.modal(f"Impression – {day_sel}"):
            st.write("### Primera impresión")
            imp_txt  = st.text_area("Impression", value=impression, height=80)
            refl_txt = st.text_area("Reflection (fin de día)",
                                    value=reflection, height=80)
            acc_sel  = st.selectbox("¿Fue acertada?",
                                    ["N/A","Yes","No"],
                                    index=["N/A","Yes","No"].index(is_accurate))
            img_txt  = st.text_area("Image URLs (máx 5, coma separadas)",
                                    value=image_urls, height=60)
            tags_txt = st.text_input("Tags (coma separadas)", value=tags)

            if img_txt:
                for u in [u.strip() for u in img_txt.split(",")[:5]]:
                    st.image(u, width=100)

            if st.button("💾 Guardar"):
                new_row = {"Date":     str(day_sel),
                           "Impression": imp_txt,
                           "Reflection": refl_txt,
                           "IsAccurate": acc_sel,
                           "ImageURLs":  img_txt,
                           "Tags":       tags_txt}
                if rec.empty:
                    ws_imp.append_row(list(new_row.values()))
                else:
                    i = rec.index[0] + 2           # fila real (1-based, +header)
                    ws_imp.update(f"A{i}:F{i}", [list(new_row.values())])
                st.success("Guardado.")
                st.session_state.pop("imp_modal_day")
                st.experimental_rerun()


# ======================================================
# 1 · Registrar trade
# ======================================================
with st.expander("➕ Registrar trade", expanded=False):
    c1, c2 = st.columns(2)

    # ---------- columna 1 ----------
    with c1:
        fecha  = st.date_input("Fecha").strftime("%Y-%m-%d")
        hora   = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.text_input("Symbol", "EURUSD")
        ttype  = st.selectbox("Type", ["Long", "Short"])
        volume = st.number_input("Volume (lotes)", 0.0, step=0.01)
        result = st.selectbox("Resultado", ["Win", "Loss", "BE"])

    # ---------- columna 2 ----------
    with c2:
        gross       = st.number_input("Gross USD (antes comisión, ±)",
                                      0.0, step=0.01, format="%.2f")
        screenshot  = st.text_input("Screenshot URL")
        comments    = st.text_area("Comentarios")
        post_an     = st.text_area("Post-Analysis")
        eod_link    = st.text_input("EOD (link Canva)")
        err_cat     = st.text_input("Error Category")

        # NUEVO selector SecondTradeValid?
        if result == "Loss":
            second_valid = st.selectbox("SecondTradeValid?",
                                        ["N/A", "Yes", "No"], index=0)
        else:
            second_valid = "N/A"

        resolved_chk = st.checkbox("¿Error Resuelto?", False)
        ltr_urls     = st.text_input("LossTradeReviewURL(s)")
        missed_urls  = st.text_input("IdeaMissedURL(s)")

    # ---------- cálculos numéricos ----------
    commission = true_commission(volume)
    if result in ("Loss", "BE") and gross > 0:
        gross = -abs(gross)
    if result == "BE":
        net_usd = -commission
        gross   = 0.0
    else:
        net_usd = gross - commission
    r_val = calc_r(net_usd)

    # ---------- guardar ----------
    if st.button("Agregar Trade"):
        trade = {
            **{c: "" for c in HEADER},  # inicializa claves vacías
            "Fecha": fecha, "Hora": hora, "Symbol": symbol, "Type": ttype,
            "Volume": volume, "Win/Loss/BE": result, "Gross_USD": gross,
            "Commission": commission, "USD": net_usd, "R": r_val,
            "Screenshot": screenshot, "Comentarios": comments,
            "Post-Analysis": post_an, "EOD": eod_link,
            "ErrorCategory": err_cat,
            "Resolved": "Yes" if resolved_chk else "No",
            "SecondTradeValid?": second_valid,
            "LossTradeReviewURL": ltr_urls,
            "IdeaMissedURL": missed_urls,
            "IsIdeaOnly": "No", "BEOutcome": ""
        }
        ws.append_row([trade[c] for c in HEADER])
        st.success("✔️ Trade agregado")
        df = get_all()

# ======================================================
# 2 · KPI panel
# ======================================================
with st.expander("📊 Métricas / KPIs", expanded=False):
    if df.empty:
        st.info("Aún no hay trades.")
    else:
        # ----------- datos reales -----------
        df_real = df[df["Win/Loss/BE"] != "Adj"].copy()
        df_real["USD"]    = pd.to_numeric(df_real["USD"], errors="coerce")
        df_real["Volume"] = pd.to_numeric(df_real["Volume"], errors="coerce")

        total   = len(df_real)
        wins    = (df_real["Win/Loss/BE"] == "Win").sum()
        losses  = (df_real["Win/Loss/BE"] == "Loss").sum()
        be_tr   = (df_real["Win/Loss/BE"] == "BE").sum()
        win_rate= round(100 * wins / total, 2) if total else 0

        gross_p = df_real[df_real["USD"] > 0]["USD"].sum()
        gross_l = df_real[df_real["USD"] < 0]["USD"].sum()
        net_p   = df_real["USD"].sum()
        commissions_sum = df_real["Commission"].sum()

        prof_factor = round(abs(gross_p / gross_l), 2) if gross_l else 0
        payoff = (round(df_real[df_real["USD"] > 0]["USD"].mean() /
                        abs(df_real[df_real["USD"] < 0]["USD"].mean()), 2)
                  if losses else 0)

        # ----------- equity y objetivos -----------
        current_eq = initial_cap + net_p
        pct_change = 100 * (current_eq - initial_cap) / initial_cap

        dd_limit   = initial_cap * 0.90
        dist_dd    = current_eq - dd_limit
        trades_to_burn = math.ceil(abs(dist_dd) / (initial_cap * 0.0025))

        f1_target  = initial_cap * 1.08
        f2_target  = initial_cap * 1.13
        dist_f1    = f1_target - current_eq
        dist_f2    = f2_target - current_eq
        f1_done    = dist_f1 <= 0

        risk_amt   = initial_cap * 0.0025
        r_total    = net_p / risk_amt
        r_f1       = max(dist_f1, 0) / risk_amt
        r_f2       = max(dist_f2, 0) / risk_amt

        pct_f1 = 100 * max(dist_f1, 0) / initial_cap
        pct_f2 = 100 * max(dist_f2, 0) / initial_cap

        t13_f1 = max(0, int(np.ceil(r_f1 / 3)))
        t13_f2 = max(0, int(np.ceil(r_f2 / 3)))
        t14_f1 = max(0, int(np.ceil(r_f1 / 4)))
        t14_f2 = max(0, int(np.ceil(r_f2 / 4)))
        t15_f1 = max(0, int(np.ceil(r_f1 / 5)))
        t15_f2 = max(0, int(np.ceil(r_f2 / 5)))

        fmt = lambda v: f"{v:,.2f}"

        # ---------- PRIMERA fila ----------
        k = st.columns(7)
        k[0].metric("Total Trades", total)
        k[1].metric("Win Rate", f"{win_rate:.2f} %")
        k[2].metric("Profit Factor", fmt(prof_factor))
        k[3].metric("Payoff ratio", fmt(payoff))
        k[4].metric("Net Profit", fmt(net_p))
        k[5].metric("Gross Profit", fmt(gross_p))
        k[6].metric("Gross Loss", fmt(gross_l))

        # ---------- SEGUNDA fila ----------
        k = st.columns(7)
        k[0].metric("Comisiones", fmt(commissions_sum))
        k[1].metric("Equity", fmt(current_eq), f"{pct_change:.2f} %")
        k[2].metric("Dist. DD −10 %", fmt(dist_dd), f"{trades_to_burn} trades")

      # ----- Loss convertibles (YES / total Loss) -----
        conv_yes = ((df_real["Win/Loss/BE"]=="Loss") &
            (df_real["SecondTradeValid?"]=="Yes")).sum()
        conv_tot = (df_real["Win/Loss/BE"]=="Loss").sum()
        conv_pct = 100*conv_yes/conv_tot if conv_tot else 0
        k[3].metric("SecondTradeValid", f"{conv_yes}/{conv_tot}",
            f"{conv_pct:.1f}%",
            delta_color="normal" if conv_pct < 50 else "inverse")
        k[4].metric("R acumuladas", f"{r_total:.2f}")
        k[5].metric("BE count", be_tr)
        k[6].metric("Win/Loss", f"{wins} / {losses}")


        # ---------- TERCERA fila ----------
        k = st.columns(7)
        k[0].metric("Fase 1 +8 %", "✅" if f1_done else fmt(dist_f1),
                    None if f1_done else f"{r_f1:.1f} R | {pct_f1:.2f}%")
        k[1].metric("Fase 2 +13 %", fmt(dist_f2),
                    f"{r_f2:.1f} R | {pct_f2:.2f}%")
        k[2].metric("Trades 1:3 F1", t13_f1)
        k[3].metric("Trades 1:3 F2", t13_f2)
        k[4].metric("Trades 1:4/5 F1", f"{t14_f1}/{t15_f1}")
        k[5].metric("Trades 1:4/5 F2", f"{t14_f2}/{t15_f2}")
        k[6].write(" ")

        # ---------- Distribución Win/Loss/BE ----------
        st.plotly_chart(
            px.pie(names=["Win","Loss","BE"],
                   values=[wins, losses, be_tr],
                   title="Distribución Win / Loss / BE"),
            use_container_width=True)

        # ---------- Curva de equity ----------
        df_sorted = df_real.sort_values("Datetime")
        df_sorted["Equity"] = initial_cap + df_sorted["USD"].cumsum()
        st.plotly_chart(
            px.line(df_sorted, x="Datetime", y="Equity",
                    title="Evolución de Equity"),
            use_container_width=True)
# ======================================================
# 3 · Balance Adjustment (fantasma)
# ======================================================
with st.expander("🩹 Balance Adjustment", expanded=False):
    current_net = round(df_real["USD"].sum(),2)
    st.write(f"Net Profit sin ajustes: **{current_net:,.2f} USD**")
    mt5_val = st.number_input("Net Profit según MT5",
                              current_net, step=0.01, format="%.2f")
    diff = round(mt5_val-current_net,2)
    st.write(f"Diferencia: **{diff:+,.2f} USD**")
    if st.button("➕ Crear ajuste") and diff!=0:
        today=datetime.today().strftime("%Y-%m-%d")
        now  =datetime.today().strftime("%H:%M:%S")
        adj=dict(zip(HEADER,[
            today,now,"ADJ","Adj",0.0,"","Adj", diff,0.0,diff,
            calc_r(diff),"","","Adjustment","","","No","","","",""
        ]))
        ws.append_row([adj[c] for c in HEADER])
        st.success("Ajuste añadido; F5 para ver métricas.")

# ======================================================
# X · ⚠️ Loss sin Resolver
# ======================================================
with st.expander("⚠️ Loss sin Resolver", expanded=False):
    # Filtramos solo Loss sin 'Resolved'
    pend = df[(df["Win/Loss/BE"] == "Loss") & (df["Resolved"] != "Yes")]
    st.metric("Pendientes", len(pend))          # mini-métrica rápida
    if pend.empty:
        st.success("Todo resuelto ✅")
    else:
        # mostramos columnas clave
        st.dataframe(
            pend[["Fecha", "Hora", "Screenshot", "USD", "ErrorCategory"]],
            height=200
        )
        # botón para saltar al editor del primer pendiente
        if st.button("Ir al primero en Editar/Borrar"):
            idx_first = int(pend.index[0])
            # Guarda parámetro en la URL para que Edit/Borrar lo lea
            st.experimental_set_query_params(edit=str(idx_first))
            st.experimental_rerun()

# ======================================================
# 4 · Historial
# ======================================================
with st.expander("📜 Historial", expanded=False):
    st.dataframe(df, use_container_width=True)

# ======================================================# ======================================================
# 5 · Editar / Borrar
# ======================================================
with st.expander("✏️ Editar / Borrar", expanded=False):
    if df.empty:
        st.info("No hay trades.")
    else:
        idx = st.number_input("Idx", 0, df.shape[0] - 1, step=1)
        sel = df.loc[idx].to_dict()
        st.json(sel)

        # ---------- BORRAR ----------
        if st.button("Borrar"):
            df = df.drop(idx).reset_index(drop=True)
            ws.clear(); ws.append_row(HEADER)
            ws.append_rows(df[HEADER].values.tolist())
            st.success("Borrado."); df = get_all()

        # ---------- EDITAR ----------
        with st.form("edit"):
            new = {}
            for col in ["Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
                        "Gross_USD","Screenshot","Comentarios","Post-Analysis",
                        "EOD","ErrorCategory","SecondTradeValid?",
                        "LossTradeReviewURL","IdeaMissedURL"]:

                if col in ("Comentarios","Post-Analysis"):
                    new[col] = st.text_area(col, sel.get(col,""))
                elif col == "Volume":
                    new[col] = st.number_input(col, 0.0, step=0.01,
                                               value=float(sel.get(col,0)))
                elif col == "SecondTradeValid?":
                    current = str(sel.get(col,"N/A")).strip().title()
                    if current not in ("Yes","No","N/A"): current = "N/A"
                    new[col] = st.selectbox(col, ["N/A","Yes","No"],
                                            index=["N/A","Yes","No"].index(current))
                else:
                    new[col] = st.text_input(col, sel.get(col, ""))

            res_chk = st.checkbox("Resolved",
                                  str(sel.get("Resolved","No")).lower() == "yes")

            submit = st.form_submit_button("Guardar")
            if submit:
                # --- recalcular números ---
                vol   = float(new["Volume"])
                comm  = true_commission(vol)
                gross = float(new["Gross_USD"])
                if new["Win/Loss/BE"] in ("Loss","BE") and gross > 0:
                    gross = -abs(gross)
                net = -comm if new["Win/Loss/BE"] == "BE" else gross - comm

                sel.update(new)
                sel.update({
                    "Commission": comm,
                    "Gross_USD": gross if new["Win/Loss/BE"] != "BE" else 0,
                    "USD": net,
                    "R": calc_r(net),
                    "Resolved": "Yes" if res_chk else "No",
                })

                update_row(idx, sel)
                st.success("Guardado."); df = get_all()

# ======================================================
# 6 · Auditoría de integridad (DumpTrades)
# ======================================================
with st.expander("🔍 Auditoría DumpTrades MT5", expanded=False):
    raw=st.text_area("Pega aquí el DumpTrades",height=180)
    if st.button("Analizar Dump"):
        rows=[]
        for ln in raw.strip().splitlines():
            if "DumpTrades" in ln:
                ln=re.split(r"\)\s+",ln,1)[-1]
            parts=ln.split(",")
            if len(parts)==7: rows.append(parts)
        if not rows: st.error("No CSV."); st.stop()
        df_log=pd.DataFrame(rows,columns=
            ["Fecha","Hora","Ticket","Symbol","Volume","TypeCode","Profit"])
        df_log["Fecha"]=pd.to_datetime(df_log["Fecha"]).dt.strftime("%Y-%m-%d")
        df_log["Hora"]=(pd.to_datetime(df_log["Hora"])-pd.Timedelta(hours=1)).dt.strftime("%H:%M:%S")
        df_log["Volume"]=df_log["Volume"].astype(float)
        df_log["Profit"]=df_log["Profit"].astype(float)
        if "Ticket" not in df.columns: df["Ticket"]=""
        merged=df_log.merge(df,on="Ticket",how="left",indicator=True,
                            suffixes=("_log","_sh"))
        faltan=merged[merged["_merge"]=="left_only"].copy()
        diff=merged[(merged["_merge"]=="both") &
                    (abs(merged["Profit"]-merged["USD"])>0.01)].copy()
        st.write(f"Trades log: {len(df_log)}")
        st.write(f"Faltan en hoja: {len(faltan)}")
        st.write(f"Profit distinto: {len(diff)}")
        if not faltan.empty: st.dataframe(faltan,height=200)
        if not diff.empty:   st.dataframe(diff,height=200)
        if st.button("⚠️ Sincronizar hoja"):
            added=repl=fixed=0
            def sym(df_): return "Symbol_log" if "Symbol_log" in df_.columns else "Symbol"
            for _,r in faltan.iterrows():
                vol=float(r["Volume"]); comm=true_commission(vol)
                usd=r["Profit"]; gross=usd+comm
                res="Win" if usd>0 else ("BE" if abs(usd+comm)<0.01 else "Loss")
                match=df[(df["Ticket"]=="") &
                         (df["Fecha"]==r["Fecha"]) &
                         (df["Symbol"]==r[sym(faltan)]) &
                         (abs(df["Volume"]-vol)<0.001)]
                if not match.empty:
                    i=match.index[0]; repl+=1
                    df.loc[i,["Ticket","Volume","Gross_USD","Commission","USD","R","Win/Loss/BE"]]=[
                        r["Ticket"],vol,gross,comm,usd,calc_r(usd),res]
                else:
                    new=dict(zip(HEADER,[r["Fecha"],r["Hora"],r[sym(faltan)],
                        "Long" if int(r["TypeCode"])%2 else "Short",
                        vol,r["Ticket"],res,gross,comm,usd,calc_r(usd),
                        "","","","","","No","","","",""]))
                    ws.append_row([new[c] for c in HEADER]); added+=1
            for _,r in diff.iterrows():
                i=df[df["Ticket"]==r["Ticket"]].index
                if i.size:
                    i=i[0]; fixed+=1
                    vol=float(r["Volume"]); comm=true_commission(vol)
                    usd=r["Profit"]; gross=usd+comm
                    df.loc[i,["Volume","Gross_USD","Commission","USD","R","Win/Loss/BE"]]=[
                        vol,gross,comm,usd,calc_r(usd),
                        ("Win" if usd>0 else ("BE" if abs(usd)<0.01 else "Loss"))]
            if added or repl or fixed:
                ws.clear(); ws.append_row(HEADER)
                ws.append_rows(df[HEADER].values.tolist())
            st.success(f"Nuevos {added} | Reemplazados {repl} | Corregidos {fixed} — F5.")
# ======================================================
# 7 · 🛠️ Reparar signos de Loss
# ======================================================
with st.expander("🛠️ Reparar signos (Loss positivos)", expanded=False):
    # detecta filas mal firmadas
    bad = df[(df["Win/Loss/BE"]=="Loss") & (pd.to_numeric(df["Gross_USD"], errors="coerce")>0)]
    st.write(f"Filas con signo incorrecto: **{len(bad)}**")
    if not bad.empty:
        st.dataframe(bad[["Fecha","Hora","Symbol","Gross_USD","Commission","USD"]])
    if st.button("⚙️ Corregir todos") and not bad.empty:
        count = 0
        for i, row in bad.iterrows():
            gross = -abs(float(row["Gross_USD"]))         # cambia a negativo
            comm  = float(row["Commission"])
            usd   = gross - comm
            row_dict = row.to_dict()
            row_dict.update({"Gross_USD": gross,
                             "USD": usd,
                             "R": calc_r(usd)})
            update_row(i, row_dict)
            count += 1
        st.success(f"{count} fila(s) corregidas ✔️ — pulsa Rerun.")
