
import streamlit as st, pandas as pd, gspread, numpy as np
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# 1) Config inicial
st.set_page_config(page_title="QuantJournal – Ingreso", layout="wide")
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["quantitative_journal"]
gc = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
ws = gc.open_by_key("1D4AlYBD1EClp0gGe0qnxr8NeGMbpSvdOx8yHimQDmbE").worksheet("sheet1")

HEADER = [
    "Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
    "Gross_USD","Commission","USD","R","Screenshot","Comentarios","Post-Analysis",
    "EOD","ErrorCategory","Resolved","LossTradeReviewURL","IdeaMissedURL"
]

# ---------- utilidades ----------
def get_all(): 
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty:
        df["Datetime"] = pd.to_datetime(df["Fecha"]+" "+df["Hora"], errors="coerce")
    return df

def calculate_r(net_usd, acct=60000, rpct=0.25):
    risk = acct*(rpct/100)
    return round(float(net_usd)/risk, 2)

def append_trade(d):
    ws.append_row([d.get(col,"") for col in HEADER])

def update_row(idx, d):
    sheet_row = idx+2                                 # 0‑based → 1‑based (+ header)
    row_vals  = [d.get(col,"") for col in HEADER]
    ws.update(f"A{sheet_row}:R{sheet_row}", [row_vals])   # 18 col = A…R

df = get_all()
st.title("Quantitative Journal · Ingreso / Edición")

# ------------------------------------------------------
# 3) Funciones auxiliares
# ------------------------------------------------------
def get_all_trades() -> pd.DataFrame:
    """
    Lee todos los registros de la hoja y los retorna como DataFrame.
    """
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    # Convertir a datetime si existen esas columnas
    if not df.empty and "Fecha" in df.columns and "Hora" in df.columns:
        df["Datetime"] = pd.to_datetime(df["Fecha"] + " " + df["Hora"], errors="coerce")
    return df

def append_trade(trade_dict: dict):
    row_values = [
        trade_dict.get("Fecha",""),
        trade_dict.get("Hora",""),
        trade_dict.get("Symbol",""),
        trade_dict.get("Type",""),
        trade_dict.get("Volume",""),
        trade_dict.get("Win/Loss/BE",""),
        trade_dict.get("Gross_USD",""),
        trade_dict.get("Commission",""),
        trade_dict.get("USD",""),
        trade_dict.get("R",""),
        trade_dict.get("Screenshot",""),
        trade_dict.get("Comentarios",""),
        trade_dict.get("Post-Analysis",""),
        trade_dict.get("StudyCaseLink",""),
        trade_dict.get("ErrorCategory",""),         # nuevo
        trade_dict.get("Resolved",""),              # nuevo
        trade_dict.get("StudyCaseImageURL","")      # nuevo
    ]
    worksheet.append_row(row_values)

def overwrite_sheet(df: pd.DataFrame):
    """
    Reemplaza toda la hoja con el DataFrame + encabezados.
    1) Convierte 'Datetime' a string si existe (evita TypeError).
    2) Reemplaza NaN por "" para que no falle la serialización.
    3) Limpia la hoja, reescribe encabezados y luego todas las filas.
    """
    if "Datetime" in df.columns and pd.api.types.is_datetime64_any_dtype(df["Datetime"]):
        df["Datetime"] = df["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    df = df.fillna("")  # Reemplazar NaN con ""
    worksheet.clear()
    worksheet.append_row(df.columns.tolist())
    rows = df.values.tolist()
    worksheet.append_rows(rows)

def update_single_row_in_sheet(row_index: int, trade_dict: dict):
    sheet_row = row_index + 2  # la fila en la hoja (1-based) 
    row_values = [
        trade_dict.get("Fecha",""),
        trade_dict.get("Hora",""),
        trade_dict.get("Symbol",""),
        trade_dict.get("Type",""),
        trade_dict.get("Volume",""),
        trade_dict.get("Win/Loss/BE",""),
        trade_dict.get("Gross_USD",""),
        trade_dict.get("Commission",""),
        trade_dict.get("USD",""),
        trade_dict.get("R",""),
        trade_dict.get("Screenshot",""),
        trade_dict.get("Comentarios",""),
        trade_dict.get("Post-Analysis",""),
        trade_dict.get("StudyCaseLink",""),
        trade_dict.get("ErrorCategory",""),
        trade_dict.get("Resolved",""),
        trade_dict.get("StudyCaseImageURL","")  # <-- la 17.ª 
    ]
    # Si ya son 17 columnas, necesitas usar Q en el rango
    worksheet.update(f"A{sheet_row}:Q{sheet_row}", [row_values])

def calculate_r(usd_value: float, account_size=60000, risk_percent=0.25):
    """
    Calcula cuántas R's representa la ganancia/pérdida en 'usd_value'.
    Por defecto, tomamos 60k como tamaño de cuenta.
    OJO: risk_percent=0.25 equivale a 0.25%.
    """
    risk_amount = account_size * (risk_percent / 100.0)  # 0.25% => 0.0025 * 60000 = 150
    R = float(usd_value) / risk_amount
    return round(R, 2)

def check_rules(df: pd.DataFrame, new_trade: dict) -> list:
    """
    Valida las reglas (esperar 10 min tras un SL, no sobrepasar 2 SL diarios, no más de 6 SL consecutivos/semana, etc.).
    Retorna una lista de strings con las violaciones encontradas.
    """
    alerts = []
    if new_trade["Win/Loss/BE"] == "Loss":
        if not df.empty:
            df_loss = df[df["Win/Loss/BE"] == "Loss"].copy()
            if not df_loss.empty:
                last_loss_time = pd.to_datetime(df_loss["Datetime"].iloc[-1])
                new_time = pd.to_datetime(new_trade["Fecha"] + " " + new_trade["Hora"])
                if (new_time - last_loss_time) < timedelta(minutes=10):
                    alerts.append("Violación: No esperaste 10 min después del último SL.")

    today_str = new_trade["Fecha"]
    if not df.empty:
        df_today = df[df["Fecha"] == today_str]
        losses_today = df_today[df_today["Win/Loss/BE"] == "Loss"].shape[0]
        if new_trade["Win/Loss/BE"] == "Loss" and losses_today >= 2:
            alerts.append("Violación: Llevas 2 SL hoy. No deberías operar más hoy.")

    if not df.empty:
        new_trade_datetime = pd.to_datetime(new_trade["Fecha"] + " " + new_trade["Hora"])
        week_number = new_trade_datetime.isocalendar().week
        year_number = new_trade_datetime.isocalendar().year

        df["week"] = df["Datetime"].apply(lambda x: x.isocalendar().week)
        df["year"] = df["Datetime"].apply(lambda x: x.isocalendar().year)
        df_this_week = df[(df["week"] == week_number) & (df["year"] == year_number)]
        df_this_week = df_this_week.sort_values("Datetime").reset_index(drop=True)

        consecutive_sl = 0
        max_consecutive_sl = 0
        for _, row in df_this_week.iterrows():
            if row["Win/Loss/BE"] == "Loss":
                consecutive_sl += 1
                max_consecutive_sl = max(max_consecutive_sl, consecutive_sl)
            else:
                consecutive_sl = 0
        if new_trade["Win/Loss/BE"] == "Loss":
            consecutive_sl += 1
            max_consecutive_sl = max(max_consecutive_sl, consecutive_sl)

        if max_consecutive_sl >= 6:
            alerts.append("Violación: 6 SL consecutivos esta semana. Debes parar hasta el próximo Lunes.")

    return alerts


# ------------------------------------------------------
# 4) Lectura inicial del DF y Layout
# ------------------------------------------------------
df = get_all_trades()

st.title("Quantitative Journal - 60K Account")

# =========================================================
#  SECCIÓN 1 · Registrar un trade
# =========================================================
with st.expander("➕ Registrar trade", expanded=False):
    c1,c2 = st.columns(2)
    with c1:
        fecha  = st.date_input("Fecha").strftime("%Y-%m-%d")
        hora   = st.time_input("Hora").strftime("%H:%M:%S")
        symbol = st.text_input("Symbol", value="EURUSD")
        ttype  = st.selectbox("Type", ["Long","Short"])
        vol    = st.number_input("Volume (lotes)", 0.0, step=0.01)
        result = st.selectbox("Resultado", ["Win","Loss","BE"])
    with c2:
        gross  = st.number_input("Gross USD (antes comisión)", 0.0, step=0.01)
        ss     = st.text_input("Screenshot URL (opcional)")
        com    = vol*4.0
        # ----- campos nuevos -----
        eod_link   = st.text_input("EOD (Enlace Canva) – opcional")
        err_cat    = st.text_input("Error Category – opcional")
        resolved   = st.checkbox("¿Error Resuelto?", value=False)
        ltr_urls   = st.text_input("LossTradeReviewURL(s)  (separa con coma)")
        missed_urls= st.text_input("IdeaMissedURL(s)  (opcional)")

    # BE → auto‑ajustamos neto = 0 descontando comisión
    if result == "BE":
        gross = com                       # bruto = comisión
    net_usd   = gross - com
    r_value   = calculate_r(net_usd)

    if st.button("Agregar Trade"):
        trade = dict(zip(HEADER, [
            fecha,hora,symbol,ttype,vol,result,
            gross,com,net_usd,r_value,ss,"","",
            eod_link,err_cat,"Yes" if resolved else "No",
            ltr_urls, missed_urls
        ]))
        append_trade(trade)
        st.success("✔️ Trade agregado")
        df = get_all()


# ======================================================
# SECCIÓN 2: Feature Engineering y Métricas
# ======================================================
with st.expander("2. Feature Engineering y Métricas", expanded=False):
    st.write("Métricas generales de la cuenta y visualizaciones principales.")

    if df.empty:
        st.warning("Aún no hay datos registrados.")
    else:
        # Convertir a tipo numérico las columnas numéricas
        for col_name in ["Volume","Gross_USD","Commission","USD","R"]:
            if col_name in df.columns:
                df[col_name] = pd.to_numeric(df[col_name], errors="coerce")

        total_trades = len(df)
        wins = len(df[df["Win/Loss/BE"] == "Win"])
        losses = len(df[df["Win/Loss/BE"] == "Loss"])
        be = len(df[df["Win/Loss/BE"] == "BE"])
        win_rate = round((wins / total_trades) * 100, 2) if total_trades > 0 else 0

        gross_profit = df[df["USD"] > 0]["USD"].sum()
        gross_loss = df[df["USD"] < 0]["USD"].sum()
        net_profit = df["USD"].sum()

        profit_factor = 0
        if gross_loss != 0:
            profit_factor = round(abs(gross_profit / gross_loss), 2)

        best_profit = df["USD"].max()
        worst_loss = df["USD"].min()
        avg_profit = df[df["USD"] > 0]["USD"].mean() if wins > 0 else 0
        avg_loss = df[df["USD"] < 0]["USD"].mean() if losses > 0 else 0
        expectancy = round(df["USD"].mean(), 2) if total_trades > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", total_trades)
        col2.metric("Win Rate", f"{win_rate}%")
        col3.metric("Profit Factor", profit_factor)
        col4.metric("Expectancy", f"{expectancy} USD")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Gross Profit (neto)", round(gross_profit,2))
        col6.metric("Gross Loss (neto)", round(gross_loss,2))
        col7.metric("Net Profit", round(net_profit,2))
        col8.write(" ")

        initial_capital = 60000
        monthly_target_usd = initial_capital * 0.14
        df = df.sort_values("Datetime").reset_index(drop=True)

        df["Cumulative_USD"] = initial_capital + df["USD"].cumsum()
        current_equity = df["Cumulative_USD"].iloc[-1]
        pct_change = ((current_equity - initial_capital)/initial_capital)*100

        col9, col10 = st.columns(2)
        col9.metric("Equity actual", f"{round(current_equity,2)} USD", f"{round(pct_change,2)}% vs. inicio")
        target_equity = initial_capital + monthly_target_usd
        distance_to_target = target_equity - current_equity
        if distance_to_target > 0:
            dist_text = f"{round(distance_to_target,2)} USD"
        else:
            dist_text = "Meta superada!"
        col10.metric("Dist. a +14%", dist_text)

        # Pie Chart Win/Loss/BE
        fig_pie = px.pie(
            names=["Win","Loss","BE"],
            values=[wins, losses, be],
            title="Distribución Win / Loss / BE"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # Objetivos en R
        risk_amount = initial_capital * 0.0025
        total_R_acum = net_profit / risk_amount
        R_faltantes = (monthly_target_usd - net_profit) / risk_amount
        trades_13_faltan = max(0, int(np.ceil(R_faltantes / 3))) if R_faltantes > 0 else 0

        st.write(f"**R's acumuladas**: {round(total_R_acum,2)}")
        st.write(f"**R's faltantes** para objetivo +14%: {round(R_faltantes,2)}")
        st.write(f"Trades 1:3 necesarios aprox: {trades_13_faltan}")

        fig_line = px.line(
            df, 
            x="Datetime", 
            y="Cumulative_USD", 
            title="Evolución de la cuenta (USD Neto)"
        )
        st.plotly_chart(fig_line, use_container_width=True)

# ======================================================
# SECCIÓN 3: Historial de Trades
# ======================================================
with st.expander("3. Historial de trades", expanded=False):
    if df.empty:
        st.warning("No hay trades registrados.")
    else:
        st.dataframe(df, use_container_width=True)

# =========================================================
#  SECCIÓN 4 · Editar / borrar
# =========================================================
with st.expander("✏️ Editar / Borrar", expanded=False):
    if df.empty:
        st.info("No hay trades.")
    else:
        idx = st.number_input("Índice (0‑based)", 0, df.shape[0]-1, step=1)
        sel = df.loc[idx].to_dict()
        st.json(sel)

        if st.button("Borrar este trade"):
            df = df.drop(idx).reset_index(drop=True)
            ws.clear()
            ws.append_row(HEADER)
            ws.append_rows(df[HEADER].values.tolist())
            st.success("Trade borrado")
            df = get_all()

        with st.form("edit"):
            new_vals = {}
            for col in ["Fecha","Hora","Symbol","Type","Volume","Win/Loss/BE",
                        "Gross_USD","Screenshot","Comentarios","Post-Analysis",
                        "EOD","ErrorCategory","LossTradeReviewURL","IdeaMissedURL"]:
                if col in ["Comentarios","Post-Analysis"]:
                    new_vals[col] = st.text_area(col, sel[col])
                elif col in ["LossTradeReviewURL","IdeaMissedURL"]:
                    new_vals[col] = st.text_input(col, sel.get(col,""))
                elif col == "Volume":
                    new_vals[col] = st.number_input(col, 0.0, step=0.01, value=float(sel[col]))
                else:
                    new_vals[col] = st.text_input(col, sel[col])

            resolved_chk = st.checkbox("Resolved", value=(sel["Resolved"].lower()=="yes"))
            submitted = st.form_submit_button("Guardar")
            if submitted:
                # recalculamos comisión / neto / R
                volume  = float(new_vals["Volume"])
                gross   = float(new_vals["Gross_USD"])
                comm    = volume*4.0
                if new_vals["Win/Loss/BE"] == "BE":
                    gross = comm
                net_usd = gross - comm
                r_val   = calculate_r(net_usd)

                # actualizamos dict completo
                sel.update(new_vals)
                sel["Gross_USD"]  = gross
                sel["Commission"] = comm
                sel["USD"]        = net_usd
                sel["R"]          = r_val
                sel["Resolved"]   = "Yes" if resolved_chk else "No"

                update_row(idx, sel)
                st.success("Cambios guardados")
                df = get_all()
# ------------- resto de tu app (historial, etc.) -------------
st.dataframe(df)

# Fin de la app
