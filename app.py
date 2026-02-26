import streamlit as st
import pandas as pd
from datetime import datetime
import io
import json
import os
import xlsxwriter

# --- CONFIGURACIÓN GLOBAL ---
st.set_page_config(page_title="Gestor de Errores SAP", page_icon="📊", layout="wide")

DB_FILE = "database_ptra.json"

# --- ESTILOS PERSONALIZADOS (ESTÉTICA DECATHLON SUTIL) ---
st.markdown("""
    <style>
    /* Importar Roboto desde Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');

    /* Fuente general de la App */
    html, body, [class*="css"] {
        font-family: 'Roboto', sans-serif !important;
    }

    /* Títulos y Subtítulos (Roboto Bold) */
    h1, h2, h3, h4, h5, h6, .stMetric label, [data-testid="stHeader"] {
        font-family: 'Roboto', sans-serif !important;
        font-weight: 700 !important;
    }

    /* Sidebar: Azul de Francia con texto blanco */
    [data-testid="stSidebar"] {
        background-color: #0082C3 !important;
    }

    /* Forzar texto blanco en Sidebar y Radio Buttons */
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    
    /* Color de los iconos de los Radio Buttons al estar seleccionados */
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        color: white !important;
    }

    /* Fondo principal */
    .main { background-color: #f5f7f9; }

    /* Botones estilo Decathlon */
    .stButton>button { 
        width: 100%; 
        border-radius: 4px; 
        height: 3em; 
        background-color: #0082C3; 
        color: white; 
        border: none;
        font-weight: 700;
    }
    
    .stButton>button:hover {
        border: 1px solid white;
        color: white;
    }

    /* Hack Visual: Itálica para 'A' y 'O' en títulos */
    /* Usamos una clase especial que activaremos con JS */
    .italic-char {
        display: inline-block;
        font-style: italic;
        font-family: inherit;
    }
    </style>

    <script>
    /* Script para aplicar itálica a las letras A y O en títulos */
    function applyItalicStyle() {
        const headers = window.parent.document.querySelectorAll('h1, h2, h3, h4');
        headers.forEach(header => {
            if (header.getAttribute('data-italicized') === 'true') return;
            
            let text = header.innerHTML;
            // Reemplaza A, a, O, o por un span con clase italic-char
            const newText = text.replace(/[aAoO]/g, (match) => {
                return `<span class="italic-char">${match}</span>`;
            });
            header.innerHTML = newText;
            header.setAttribute('data-italicized', 'true');
        });
    }
    // Ejecutar periódicamente para capturar cambios de Streamlit
    setInterval(applyItalicStyle, 1000);
    </script>
    """, unsafe_allow_html=True)

# --- MODAL DE USUARIO ---
@st.dialog("Identificación de Usuario")
def login_modal():
    st.write("### 👋 ¡Bienvenido!")
    st.write("Por favor, ingrese su nombre para registrar las operaciones en SAP.")
    user = st.text_input("Nombre de Usuario")
    if st.button("Ingresar"):
        if user.strip():
            st.session_state.user_sap = user.strip()
            st.success(f"Sesión iniciada como: {user}")
            st.rerun()
        else:
            st.error("El nombre es obligatorio para la trazabilidad.")

if "user_sap" not in st.session_state:
    login_modal()

# --- GESTIÓN DE BASE DE DATOS ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- LÓGICA DE PROCESAMIENTO ---
def procesar_datos_base(df, user_name, solo_migo=False):
    df_result = df.copy()
    
    # 1. Tratamiento de Fechas y Horas
    for col_prefix in ['despacho', 'recepcion']:
        date_col = f'created_date_{col_prefix}'
        hora_col = f'hora_{col_prefix}'
        if date_col in df_result.columns:
            temp_dt = df_result[date_col].astype(str).str.split(' ', expand=True)
            df_result[date_col] = temp_dt[0]
            horas = temp_dt[1] if len(temp_dt.columns) > 1 else "00:00:00"
            
            if hora_col not in df_result.columns:
                idx = df_result.columns.get_loc(date_col)
                df_result.insert(idx + 1, hora_col, horas)

    # 2. Columnas de Gestión
    cols_sap = {
        'PTRA': "", 'DESPACHO': "", 'RECEPCION': "", 
        'OBSERVACIONES': "", 'fecha_de_carga_SAP': "", 'usuario_SAP': ""
    }
    for col, val in cols_sap.items():
        if col not in df_result.columns:
            df_result[col] = val

    # 3. Lógica de Estados SAP
    c45 = (df_result['status_despacho'] == 4) & (df_result['status_recepcion'] == 5)
    c85 = (df_result['status_despacho'] == 8) & (df_result['status_recepcion'] == 5)
    c64 = (df_result['status_despacho'] == 6) & (df_result['status_recepcion'] == 4)

    df_result.loc[c45 | c85 | c64, 'usuario_SAP'] = user_name

    if solo_migo:
        df_result = df_result[c85 | c64].copy()

    return df_result

def generar_excel_descargable(df, sheet_name, db_data):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        header_fmt = workbook.add_format({'bold': True, 'bg_color': "#2A42C9", 'border': 1})
        
        ws_ptra = workbook.add_worksheet('DB_PTRA')
        ws_ptra.write(0, 0, 'mooving_id', header_fmt)
        ws_ptra.write(0, 1, 'PTRA_VAL', header_fmt)
        
        for i, (k, v) in enumerate(db_data.items()):
            try:
                ws_ptra.write_number(i + 1, 0, int(k))
            except:
                ws_ptra.write(i + 1, 0, k)
            ws_ptra.write(i + 1, 1, v)

        if 'mooving_id_recepcion' in df.columns and 'PTRA' in df.columns:
            m_idx = df.columns.get_loc('mooving_id_recepcion')
            p_idx = df.columns.get_loc('PTRA')
            col_letter = xlsxwriter.utility.xl_col_to_name(m_idx)
            
            for row in range(1, len(df) + 1):
                formula = f'=IFERROR(VLOOKUP({col_letter}{row+1}, DB_PTRA!$A:$B, 2, FALSE), "")'
                worksheet.write_formula(row, p_idx, formula)

        for i, col in enumerate(df.columns):
            if col == 'PTRA':
                worksheet.set_column(i, i, 25)
            else:
                column_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
                worksheet.set_column(i, i, min(column_len, 40))

    return output.getvalue()

# --- INTERFAZ PRINCIPAL ---
db = load_db()
fecha_hoy = datetime.now().strftime('%Y-%m-%d')

with st.sidebar:
    st.title("Control SAP")
    if "user_sap" in st.session_state:
        st.info(f"👤 **Usuario:** {st.session_state.user_sap}")
    
    opcion = st.radio(
        "Navegación",
        ["Inicio", "Errores Vinculados", "Reporte MIGO", "ZDESPACHO", "Configurar PTRA"]
    )
    st.divider()
    st.caption(f"v2.0 | Base de datos: {len(db)} registros")

if opcion == "Inicio":
    st.title("📊 Panel de Control Logístico")
    col1, col2, col3 = st.columns(3)
    col1.metric("Registros PTRA", len(db))
    col2.metric("Estado Sistema", "Online", delta="Estable")
    col3.metric("Fecha", fecha_hoy)
    
    st.markdown("""
    ### Instrucciones Rápidas:
    1. **Reporte Vinculados:** Cruce general de datos con usuario SAP en las celdas con Errores.
    2. **Reporte para MIGO:** Filtro de Productos con errores de Recepcion.
    3. **Reporte para ZDESPACHO:** Archivo simplificado para la carga de Errores de Despacho y Recepcion.
    4. **PTRA:** Mantén actualizada la relación ID Mooving <-> Código PTRA.
    """)

elif opcion == "Errores Vinculados":
    st.header("🔗 Procesamiento de Errores Vinculados")
    up = st.file_uploader("Cargar archivo de errores de despacho y recepcion vinculados", type=["xlsx", "csv"])
    
    if up:
        df_in = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
        if st.button("Procesar y Generar Excel"):
            with st.spinner("Procesando datos..."):
                df_proc = procesar_datos_base(df_in, st.session_state.user_sap)
                data_xls = generar_excel_descargable(df_proc, 'ERRORES', db)
                st.success("¡Proceso completado!")
                st.download_button("📥 Descargar Reporte de Vinculados", data_xls, f"Vinculados_{fecha_hoy}.xlsx")

elif opcion == "Reporte MIGO":
    st.header("📦 Generar Reporte para carga en MIGO")
    st.info("Filtra automáticamente: status_despacho = 8 & status_recepción = 5 / status_despacho = 6 & status_recepción = 4")
    up = st.file_uploader("Cargar archivo 'Reporte_Vinculados_dd.mm.aaaa'", type=["xlsx", "csv"])
    
    if up:
        df_in = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
        if st.button("Generar Reporte para MIGO"):
            df_proc = procesar_datos_base(df_in, st.session_state.user_sap, solo_migo=True)
            if not df_proc.empty:
                data_xls = generar_excel_descargable(df_proc, 'MIGO', db)
                st.download_button("📥 Descargar MIGO", data_xls, f"Errores_MIGO_{fecha_hoy}.xlsx")
            else:
                st.warning("No hay registros que cumplan las condiciones MIGO.")

elif opcion == "ZDESPACHO":
    st.header("📋 Generar Reporte para carga en ZDESPACHO")
    st.info("Filtra automáticamente: status_despacho = 4 & status_recepción = 5")
    up = st.file_uploader("Cargar archivo 'Reporte_Vinculados_dd.mm.aaaa'", type=["xlsx"])
    
    if up:
        df_in = pd.read_excel(up)
        if 'mooving_id_recepcion' in df_in.columns:
            df_in['PTRA'] = df_in['mooving_id_recepcion'].apply(lambda x: db.get(str(x).split('.')[0].strip(), ""))
            
        mask = (df_in['status_despacho'] == 4) & (df_in['status_recepcion'] == 5)
        res = df_in[mask][['PTRA', 'item_id_recepcion', 'quantity_recepcion']].copy()
        res.columns = ['PTRA', 'ITEM', 'CANTIDAD']
        
        st.subheader("Previsualización:")
        st.dataframe(res, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            res.to_excel(writer, index=False, sheet_name='ZDESPACHO')
            ws = writer.sheets['ZDESPACHO']
            ws.set_column(0, 0, 25)
        
        st.download_button("📥 Descargar Reporte para ZDESPACHO", output.getvalue(), f"Errores_{fecha_hoy}.xlsx")

elif opcion == "Configurar PTRA":
    st.header("⚙️ Gestión de Base de Datos PTRA")
    t1, t2 = st.tabs(["✏️ Registro Individual", "📂 Carga Masiva"])
    
    with t1:
        with st.form("individual_form"):
            mid = st.text_input("ID Mooving (Key)")
            pval = st.text_input("Código PTRA (Value)")
            if st.form_submit_button("Guardar Registro"):
                if mid and pval:
                    db[str(mid)] = str(pval)
                    save_db(db)
                    st.success(f"ID {mid} actualizado.")
                    st.rerun()

    with t2:
        st.write("Pega el listado con formato: `ID_MOOVING PTRA_VAL` (separado por espacio o tab)")
        txt = st.text_area("Listado masivo", height=200, placeholder="12345 PTRA001\n67890 PTRA002")
        if st.button("Actualizar Base"):
            count = 0
            for line in txt.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    db[str(parts[0])] = " ".join(parts[1:])
                    count += 1
            save_db(db)
            st.success(f"Se actualizaron {count} registros.")
            st.rerun()

    with st.expander("Ver base de datos actual"):
        if db:
            df_db = pd.DataFrame(list(db.items()), columns=["ID Mooving", "Código PTRA"])
            st.dataframe(df_db, use_container_width=True)
        else:
            st.write("La base de datos está vacía.")