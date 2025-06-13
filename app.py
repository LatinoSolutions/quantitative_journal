# ------------------  app.py  ------------------
import streamlit as st, pandas as pd, numpy as np, math, re, time, random
import plotly.express as px, plotly.graph_objects as go
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread
from gspread.exceptions import APIError

# ---------- Conexión ----------
st.set_page_config("Quantitative Journal – Ingreso / KPIs", layout="wide")

creds = Credentials.from_service_account_info(
    st.secrets["quantitative_journal"],
    scopes=["https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"])

def with_retry(fn, *args, **kwargs):
    """Ejecuta fn con reintento exponencial (máx 3)."""
    for attempt in range(3):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            if attempt == 2:
                raise
            wait = 1.5 * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(wait)

gc = gspread.authorize(creds)

def open_ws(sheet_key:str, tab:str):
    sh = with_retry(gc.open_by_key, sheet_key)
    try:
        return sh.worksheet(tab)
    except gspread.exceptions.WorksheetNotFound:
        ws_new = with_retry(sh.add_worksheet, tab, rows=1000, cols=20)
        return ws_new

ws = open_ws("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE", "sheet1")

HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Ticket","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios",
    "Post-Analysis","EOD","ErrorCategory","Resolved","SecondTradeValid?",
    "LossTradeReviewURL","IdeaMissedURL","IsIdeaOnly","BEOutcome"
]

# -- fuerza cabecera --
if with_retry(ws.row_values, 1) != HEADER:
    with_retry(ws.update, "A1", [HEADER])

# ---------- Helpers ----------
initial_cap = 60000

def true_commission(vol: float) -> float:
    return round(vol * 4.0, 2)

def calc_r(net: float) -> float:
    risk = initial_cap * 0.0025
    return round(net / risk, 2) if risk else 0

def get_all():
    data = with_retry(ws.get_all_records)
    df = pd.DataFrame(data)
    if not df.empty:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"],
                                        errors="coerce")
    return df

def col_letter(n:int) -> str:
    s=""
    while n:
        n, r = divmod(n-1, 26)
        s = chr(65+r)+s
    return s

def update_row(i:int, d:dict):
    row  = i + 2
    last = col_letter(len(HEADER))
    vals = [[d.get(c,"") for c in HEADER]]
    with_retry(ws.update, f"A{row}:{last}{row}", vals)

df = get_all()
st.title("Quantitative Journal · Registro & Métricas")


# ======================================================
# 📅 · Daily Impressions  (calendario + formulario)
# ======================================================
with st.expander("📅 Daily Impressions", expanded=False):

    IMP_HEADER = ["Fecha", "Impression", "Reflection",
                  "Good?", "ImageURLs"]              # cabecera fija

    # ---------- obtener / crear hoja ----------
    try:
        ws_imp = gspread.authorize(creds)\
                 .open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE")\
                 .worksheet("daily_impressions")
    except gspread.exceptions.WorksheetNotFound:
        ws_imp = ws.add_worksheet("daily_impressions", rows=1000, cols=10)
        ws_imp.append_row(IMP_HEADER)

    # ---------- fuerza cabecera correcta (con retry) ----------
    try:
        if ws_imp.row_values(1) != IMP_HEADER:
            ws_imp.update("A1", [IMP_HEADER])
    except gspread.exceptions.APIError:
        time.sleep(1.5)
        if ws_imp.row_values(1) != IMP_HEADER:
            ws_imp.update("A1", [IMP_HEADER])

    # ---------- DataFrame (si no hay filas, crea columnas vacías) ----------
    imp_records = ws_imp.get_all_records()
    imp_df = (pd.DataFrame(imp_records)
              if imp_records else pd.DataFrame(columns=IMP_HEADER))
    if not imp_df.empty:
        imp_df["Fecha"] = pd.to_datetime(imp_df["Fecha"]).dt.strftime("%Y-%m-%d")

    # ---------- mes actual ----------
    today = datetime.today()
    y = st.session_state.get("imp_y", today.year)
    m = st.session_state.get("imp_m", today.month)

    def _shift(delta):
        ym = datetime(y, m, 1) + pd.DateOffset(months=delta)
        st.session_state["imp_y"], st.session_state["imp_m"] = ym.year, ym.month
        st.experimental_rerun()

    nav1, nav2, nav3, nav4, nav5 = st.columns([1,1,3,1,1])
    if nav1.button("⏮"): _shift(-12)
    if nav2.button("◀"):  _shift(-1)
    nav3.markdown(f"<h4 style='text-align:center'>{datetime(y,m,1):%B %Y}</h4>",
                  unsafe_allow_html=True)
    if nav4.button("▶"):  _shift(+1)
    if nav5.button("⏭"): _shift(+12)

    # ---------- calendario ----------
    m_ini = datetime(y, m, 1)
    m_end = (m_ini + pd.offsets.MonthEnd()).to_pydatetime()
    cols = st.columns(7)
    offset = m_ini.weekday()                           # lunes = 0
    for _ in range(offset): cols[_].write(" ")

    for i, d in enumerate(pd.date_range(m_ini, m_end)):
        if i and (offset+i) % 7 == 0:
            cols = st.columns(7)
        col = cols[(offset+i) % 7]

        d_str = d.strftime("%Y-%m-%d")
        rec   = imp_df[imp_df["Fecha"] == d_str]
        has_i = not rec.empty

        if col.button(str(d.day), key=f"btn_{d_str}"):
            st.session_state["imp_sel"] = d_str

        if has_i and rec.iloc[0]["ImageURLs"]:
            thumb = rec.iloc[0]["ImageURLs"].splitlines()[0].strip()
            try:
                col.image(thumb, width=50)
            except st.runtime.media_file_storage.MediaFileStorageError:
                col.write("🖼️")
        else:
            col.write(" ")

    # ---------- formulario ----------
    sel = st.session_state.get("imp_sel")
    if sel:
        rec = imp_df[imp_df["Fecha"] == sel]
        getv = lambda k: (rec.iloc[0][k] if (k in rec.columns and not rec.empty) else "")

        st.markdown("---")
        st.subheader(f"Impression – {sel}")

        f_imp   = st.text_area("✏️ Primera impresión", getv("Impression"))
        reflect = st.text_area("🔍 Reflexión / Análisis", getv("Reflection"))
        good    = st.selectbox("¿Acertada?", ["N/A","Yes","No"],
                               index=["N/A","Yes","No"].index(getv("Good?") or "N/A"))
        urls    = st.text_area("URLs imágenes (una por línea)", getv("ImageURLs"))

        if st.button("💾 Guardar / Actualizar"):
            row = {"Fecha": sel, "Impression": f_imp,
                   "Reflection": reflect, "Good?": good,
                   "ImageURLs": urls}

        if rec.empty:
                with_retry(ws_imp.append_row,
                           [row[c] for c in IMP_HEADER])
        else:
                r = rec.index[0] + 2
                with_retry(ws_imp.update,
                           f"A{r}:E{r}", [[row[c] for c in IMP_HEADER]])

        st.success("Guardado ✔️")
            # deselecciona día para evitar rerun en bucle
        st.session_state.pop("imp_sel", None)




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
# 1·5  ⬆️ Importar reporte MT5 (.xlsx)
#        – Añade / actualiza trades en la misma hoja
# ======================================================
with st.expander("⬆️ Importar reporte MT5 (.xlsx)", expanded=False):

    upl_file = st.file_uploader(
        "Arrastra aquí el ReportHistory-*.xlsx exportado desde MT5",
        type=["xlsx"]
    )

    if upl_file:
        try:
            # ---------- 1) leemos Excel ----------
            rep = pd.read_excel(upl_file, engine="openpyxl")

            # ---------- 2) columnas mínimas ----------
            COL_MAP = {
                "Ticket":       ["Ticket", "Deal", "Order"],
                "Fecha":        ["Time", "Open Time", "Open Time GMT", "Open Time"],
                "Symbol":       ["Symbol", "Instrument"],
                "Volume":       ["Volume", "Lots"],
                "Tipo":         ["Type", "Direction"],
                "Profit":       ["Profit", "Net Profit", "Result"]
            }
            def find(col):
                for c in COL_MAP[col]:
                    if c in rep.columns: return c
                st.error(f"Columna «{col}» no encontrada en el XLS 😢"); st.stop()

            rep = rep.rename(columns={
                find("Ticket"):  "Ticket",
                find("Fecha"):   "Fecha",
                find("Symbol"):  "Symbol",
                find("Volume"):  "Volume",
                find("Tipo"):    "Type",
                find("Profit"):  "Profit"
            })[["Ticket","Fecha","Symbol","Volume","Type","Profit"]]

            # normalizamos formatos
            rep["Fecha"]  = pd.to_datetime(rep["Fecha"])
            rep["Date"]   = rep["Fecha"].dt.strftime("%Y-%m-%d")
            rep["Time"]   = (rep["Fecha"] - pd.Timedelta(hours=1))\
                              .dt.strftime("%H:%M:%S")      #  –1 h (ajusta si quieres)
            rep["Volume"] = rep["Volume"].astype(float)
            rep["Profit"] = rep["Profit"].astype(float)

            # calculamos campos que faltan
            rep["Commission"] = rep["Volume"].apply(true_commission)
            rep["Gross_USD"]  = rep["Profit"] + rep["Commission"]
            rep["Win/Loss/BE"] = np.where(
                abs(rep["Profit"]) < 0.01, "BE",
                np.where(rep["Profit"] > 0, "Win", "Loss")
            )
            rep["R"] = rep["Profit"].apply(calc_r)

            # ---------- 3) cruzamos con hoja existente ----------
            df_old = get_all()
            tickets_old = set(df_old["Ticket"].astype(str))

            to_add    = rep[~rep["Ticket"].astype(str).isin(tickets_old)].copy()
            to_update = rep[rep["Ticket"].astype(str).isin(tickets_old)].copy()

            st.success(f"Detectados {len(to_add)} nuevos trade(s) · "
                       f"{len(to_update)} actualización(es).")

            with st.expander("👀 Pre-visualizar diferencia", expanded=False):
                st.subheader("Nuevos")
                st.dataframe(to_add, use_container_width=True, height=180)
                st.subheader("Actualiza")
                st.dataframe(to_update, use_container_width=True, height=180)

            if st.button("✅ Aplicar cambios"):
                # --- añadir ---
                for _, r in to_add.iterrows():
                    row = dict(zip(HEADER, [
                        r["Date"], r["Time"], r["Symbol"],
                        "Long" if r["Type"].lower().startswith("buy") else "Short",
                        r["Volume"], r["Ticket"], r["Win/Loss/BE"],
                        r["Gross_USD"], r["Commission"], r["Profit"], r["R"],
                        "", "", "", "", "", "No", "N/A", "", "", "No", ""
                    ]))
                    ws.append_row([row[c] for c in HEADER])

                # --- actualizar ---
                if not to_update.empty and "Ticket" in df_old.columns:
                    for _, r in to_update.iterrows():
                        idx = df_old.index[df_old["Ticket"] == str(r["Ticket"])]
                        if idx.size:
                            i = idx[0]
                            upd = df_old.loc[i].to_dict()
                            upd.update({
                                "Fecha":        r["Date"],
                                "Hora":         r["Time"],
                                "Symbol":       r["Symbol"],
                                "Volume":       r["Volume"],
                                "Type":         "Long" if r["Type"].lower().startswith("buy") else "Short",
                                "Win/Loss/BE":  r["Win/Loss/BE"],
                                "Gross_USD":    r["Gross_USD"],
                                "Commission":   r["Commission"],
                                "USD":          r["Profit"],
                                "R":            r["R"],
                                "Ticket":       r["Ticket"],
                            })
                            update_row(i, upd)

                st.success("Importación completada ✔️ – pulsa **Rerun** para ver métricas.")
        except Exception as e:
            st.error(f"❌ Error procesando el XLS: {e}")

# ======================================================
# 2 · KPI panel
# ======================================================
with st.expander("📊 Métricas / KPIs", expanded=False):
    if df.empty:
        st.info("Aún no hay trades.")
    else:
        # ----------- datos reales -----------
        df_real = df[df["Win/Loss/BE"] != "Adj"].copy()
        df_real[["USD","Volume"]] = df_real[["USD","Volume"]].apply(
                                        pd.to_numeric, errors="coerce")

        total   = len(df_real)
        wins    = (df_real["Win/Loss/BE"]=="Win").sum()
        losses  = (df_real["Win/Loss/BE"]=="Loss").sum()
        be_tr   = (df_real["Win/Loss/BE"]=="BE").sum()
        win_rate= round(100*wins/total,2) if total else 0

        gross_p = df_real[df_real["USD"]>0]["USD"].sum()
        gross_l = df_real[df_real["USD"]<0]["USD"].sum()
        net_p   = df_real["USD"].sum()
        commissions_sum = df_real["Commission"].sum()

        prof_factor = round(abs(gross_p/gross_l),2) if gross_l else 0
        payoff = (round(df_real[df_real["USD"]>0]["USD"].mean() /
                        abs(df_real[df_real["USD"]<0]["USD"].mean()),2)
                  if losses else 0)

        # ----------- equity y objetivos -----------
        current_eq = initial_cap + net_p
        pct_change = 100*(current_eq-initial_cap)/initial_cap

        dd_limit   = initial_cap*0.90
        dist_dd    = current_eq-dd_limit
        trades_to_burn = math.ceil(abs(dist_dd)/(initial_cap*0.0025))

        f1_target  = initial_cap*1.08
        f2_target  = initial_cap*1.13
        dist_f1    = f1_target-current_eq
        dist_f2    = f2_target-current_eq
        f1_done    = dist_f1<=0

        risk_amt   = initial_cap*0.0025
        r_total    = net_p/risk_amt
        r_f1       = max(dist_f1,0)/risk_amt
        r_f2       = max(dist_f2,0)/risk_amt

        pct_f1 = 100*max(dist_f1,0)/initial_cap
        pct_f2 = 100*max(dist_f2,0)/initial_cap

        t13_f1 = max(0,int(np.ceil(r_f1/3)));  t13_f2 = max(0,int(np.ceil(r_f2/3)))
        t14_f1 = max(0,int(np.ceil(r_f1/4)));  t14_f2 = max(0,int(np.ceil(r_f2/4)))
        t15_f1 = max(0,int(np.ceil(r_f1/5)));  t15_f2 = max(0,int(np.ceil(r_f2/5)))

        fmt = lambda v: f"{v:,.2f}"

        # ---------- 1ª fila ----------
        k = st.columns(7)
        k[0].metric("Total Trades", total)
        k[1].metric("Win Rate", f"{win_rate:.2f} %")
        k[2].metric("Profit Factor", fmt(prof_factor))
        k[3].metric("Payoff ratio", fmt(payoff))
        k[4].metric("Net Profit", fmt(net_p))
        k[5].metric("Gross Profit", fmt(gross_p))
        k[6].metric("Gross Loss", fmt(gross_l))

        # ---------- 2ª fila ----------
        k = st.columns(7)
        k[0].metric("Comisiones", fmt(commissions_sum))
        k[1].metric("Equity", fmt(current_eq), f"{pct_change:.2f} %")
        k[2].metric("Dist. DD −10 %", fmt(dist_dd), f"{trades_to_burn} trades")

        # ----- Loss convertibles (Yes / total Loss) -----
        conv_yes = ((df_real["Win/Loss/BE"]=="Loss") &
                    (df_real["SecondTradeValid?"]=="Yes")).sum()
        conv_tot = losses
        conv_pct = 100*conv_yes/conv_tot if conv_tot else 0
        k[3].metric("SecondTradeValid", f"{conv_yes}/{conv_tot}",
                    f"{conv_pct:.1f} %",
                    delta_color="normal" if conv_pct>=50 else "inverse")

        k[4].metric("R acumuladas", f"{r_total:.2f}")
        k[5].metric("BE count", be_tr)
        k[6].metric("Win / Loss", f"{wins} / {losses}")

        # ---------- 3ª fila ----------
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

        # ---------- gráficos ----------
        st.plotly_chart(px.pie(names=["Win","Loss","BE"],
                               values=[wins,losses,be_tr]), use_container_width=True)
        df_sorted = df_real.sort_values("Datetime")
        df_sorted["Equity"] = initial_cap + df_sorted["USD"].cumsum()
        st.plotly_chart(px.line(df_sorted, x="Datetime", y="Equity",
                                title="Equity curve"), use_container_width=True)

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

# ======================================================#
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
