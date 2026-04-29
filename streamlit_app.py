import streamlit as st
import os
import PyPDF2
import google.generativeai as genai
import smtplib
import json
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from unicodedata import normalize

# ------------------------------------------------------------------
# CONFIGURACIÓN DE CLAVES 
# ------------------------------------------------------------------
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SMTP_SERVER = st.secrets["SMTP_SERVER"]
    SMTP_PORT = int(st.secrets["SMTP_PORT"])
    SMTP_USER = st.secrets["SMTP_USER"]
    SMTP_PASSWORD = st.secrets["SMTP_PASSWORD"]
except:
    from dotenv import load_dotenv
    load_dotenv()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

if not GEMINI_API_KEY:
    st.error("Falta la API Key de Gemini. Configúrala en Secrets o .env.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------------------------------------------
# LISTA DE PROCESOS
# ------------------------------------------------------------------
PROCESOS = [
    "ADHERENCIA AL TRATAMIENTO", "ADMISIONES", "ALMACÉN", "AMBIENTE FÍSICO",
    "ANESTESIOLOGÍA", "ARCHIVO CLÍNICO", "ATENCION PREHOSPITALARIA (PHE)",
    "AUDITORÍA", "AUDITORÍA CONCURRENTE", "AUDITORÍA DE CUENTAS MÉDICAS",
    "CALIBRACIÓN", "CALL CENTER", "CARTERA", "CENTRAL DE MEZCLAS PARENTERALES",
    "CIRUGÍA", "CLÍNICA ERMITA", "COCINA", "COMPRAS", "CONSULTA EXTERNA",
    "CONTABILIDAD", "CONTRATACIÓN", "CONTROL INTERNO", "CONVENIO", "COSTOS",
    "CUENTA DE ALTO COSTO", "CUMPLIMIENTO", "DIRECCIONAMIENTO",
    "DIRECCIONAMIENTO ESTRATÉGICO", "DPTO. ENFERMERÍA", "ENFERMERIA",
    "ENFOQUE AL CLIENTE", "ESTERILIZACIÓN", "FACTURACIÓN", "FINANCIERA",
    "GASES MEDICINALES", "GESTIÓN ADMINISTRATIVA", "GESTIÓN AMBIENTAL",
    "GESTIÓN DE ACTIVOS FIJOS", "GESTIÓN DE COSTOS", "GESTIÓN DE LA CALIDAD",
    "GESTIÓN DE LA INFORMACIÓN", "GESTIÓN DE MEDIO AMBIENTE", "GESTIÓN DE RIESGOS",
    "GESTIÓN DEL TALENTO HUMANO", "GESTIÓN DE TECNOLOGÍA BIOMÉDICA",
    "GESTIÓN DE TECNOLOGÍA NO PBS", "GESTIÓN JURÍDICA", "GESTIÓN MÉDICA",
    "HEMODINAMIA", "HOSPITALIZACIÓN", "IMÁGENES DIAGNÓSTICAS",
    "INFORMACIÓN AL USUARIO", "INVENTARIOS", "JURÍDICA", "LABORATORIO CLÍNICO",
    "MANTENIMIENTO", "MEDICARDIO", "MERCADEO Y COMUNICACIONES", "NUTRICIÓN Y DIETÉTICA",
    "OBSTETRICIA", "ONCOLOGÍA", "PATOLOGÍA", "PROCESOS", "PROGRAMA CANGURO",
    "REFERENCIA Y CONTRARREFERENCIA", "SEGUIMIENTO Y MEJORA", "SEGURIDAD DEL PACIENTE",
    "SEGURIDAD Y SALUD EN EL TRABAJO", "SERVICIO FARMACÉUTICO", "SERVICIO TRANSFUSIONAL",
    "SERVICIOS GENERALES", "SIAU", "SISTEMAS DE INFORMACIÓN", "TALENTO HUMANO",
    "TECNOLOGÍA BIOMÉDICA", "TERAPIA", "TESORERÍA", "UNIDAD DE CUIDADO ADULTO",
    "UNIDAD DE CUIDADO NEONATAL", "UNIDAD TRANSFUSIONAL", "URGENCIAS", "VACUNACIÓN",
    "INVESTIGACIÓN", "VIGILANCIA EPIDEMIOLÓGICA"
]

def normalizar_texto(texto):
    if not texto:
        return ""
    texto = normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return texto.strip().upper()

PROCESOS_NORM = [normalizar_texto(p) for p in PROCESOS]

def get_tipo_documento(codigo):
    if not codigo:
        return "documento"
    codigo_str = str(codigo)
    partes = codigo_str.split('-')
    prefijo = partes[0].upper() if partes else ""
    mapeo = {
        "D": "Política o Directriz", "C": "Caracterización de proceso",
        "PG": "Programa", "M": "Manual", "P": "Procedimiento",
        "G": "Guía", "PR": "Protocolo", "I": "Instructivo",
        "RT": "Ruta", "R": "Formato"
    }
    return mapeo.get(prefijo, "documento")

# ------------------------------------------------------------------
# EXTRACCIÓN DE TEXTO (control de páginas según si es manual)
# ------------------------------------------------------------------
def extraer_texto_pdf(archivo, leer_completo=False):
    texto = ""
    pdf = PyPDF2.PdfReader(archivo)
    if leer_completo:
        for pagina in pdf.pages:
            texto += pagina.extract_text() or ""
    else:
        for i, pagina in enumerate(pdf.pages):
            if i >= 3:
                break
            texto += pagina.extract_text() or ""
    return texto

def extraer_texto_excel(archivo):
    try:
        df = pd.read_excel(archivo, sheet_name=None, dtype=str)
        texto_completo = []
        for nombre_hoja, hoja in df.items():
            texto_completo.append(f"--- Hoja: {nombre_hoja} ---")
            hoja_str = hoja.fillna('').astype(str)
            for _, fila in hoja_str.iterrows():
                texto_completo.append(' '.join(fila.values))
        return '\n'.join(texto_completo)
    except Exception as e:
        raise Exception(f"Error al leer Excel: {e}")

# ------------------------------------------------------------------
# ANÁLISIS CON GEMINI (para manuales NO extrae versión ni vigencia)
# ------------------------------------------------------------------
def analizar_documento(texto, filename, es_manual=False):
    if es_manual:
        prompt = f"""
        Eres un asistente que extrae información de MANUALES DE FUNCIONES de una clínica.
        El documento es un manual de funciones.
        Devuelve ÚNICAMENTE un objeto JSON válido con las siguientes claves:
        - "proceso": el proceso responsable (debe coincidir exactamente con la lista)
        - "codigo": el código del documento (ej. R-TH-003). Si no aparece, déjalo vacío.
        - "documento": el nombre completo del documento. Si encuentras "NOMBRE DEL CARGO", úsalo como nombre del documento.
        - "importancia": un resumen de máximo 15 palabras.
        - "cargo": el nombre del cargo (busca "NOMBRE DEL CARGO").
        - NOTA: NO extraigas "version", "vigencia" ni "consecutivo". Esos campos los completará el usuario manualmente.

        Lista de procesos:
        {', '.join(PROCESOS)}

        Texto del documento:
        {texto[:15000]}
        """
    else:
        prompt = f"""
        Eres un asistente que extrae información de documentos internos de una clínica.
        Devuelve ÚNICAMENTE un objeto JSON válido con las siguientes claves:
        - "proceso": el proceso responsable (debe coincidir exactamente con la lista)
        - "codigo": el código del documento (ej. M-SST-003)
        - "version": la versión del documento (formato XX, ej. 01, 02)
        - "documento": el nombre completo del documento
        - "vigencia": la fecha desde que aplica (formato YYYY.MM.DD)
        - "importancia": un resumen de máximo 15 palabras
        - "cargo": (opcional, solo si aparece)
        - "consecutivo": (opcional)

        Lista de procesos:
        {', '.join(PROCESOS)}

        Texto del documento:
        {texto[:10000]}
        """

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        raw_response = response.text
        inicio = raw_response.find('{')
        fin = raw_response.rfind('}') + 1
        if inicio != -1 and fin != 0:
            datos = json.loads(raw_response[inicio:fin])
        else:
            raise ValueError("No se encontró JSON en la respuesta")

        # Sanitizar None
        for clave in ["proceso", "codigo", "version", "documento", "vigencia", "importancia", "cargo", "consecutivo"]:
            if datos.get(clave) is None:
                datos[clave] = ""

        if es_manual:
            # Si no se extrajo cargo, usar el nombre del archivo como respaldo
            if not datos.get("cargo") and not datos.get("documento"):
                base = os.path.splitext(os.path.basename(filename))[0]
                datos["cargo"] = base
                datos["documento"] = base
            elif datos.get("cargo") and not datos.get("documento"):
                datos["documento"] = datos["cargo"]
            # Para manuales, forzamos que versión y vigencia estén vacías (el usuario las llenará manualmente)
            datos["version"] = ""
            datos["vigencia"] = ""
            datos["consecutivo"] = ""
        return datos
    except Exception as e:
        st.error(f"Error en IA: {e}")
        return {
            "proceso": "", "codigo": "", "version": "", "documento": "",
            "vigencia": "", "importancia": "", "cargo": "", "consecutivo": ""
        }

# ------------------------------------------------------------------
# ENVÍO DE CORREO
# ------------------------------------------------------------------
def enviar_correo(destinatarios, cc_list, asunto, cuerpo_html):
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(destinatarios)
        msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo_html, "html"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error al enviar correo: {e}")
        return False

# ------------------------------------------------------------------
# INTERFAZ STREAMLIT
# ------------------------------------------------------------------
st.set_page_config(page_title="Divulgaciones AI", layout="centered", page_icon="📢")

st.markdown("""
    <div style="text-align: center; margin-bottom: 20px;">
        <h1 style="font-size: 2.5rem; font-weight: bold; color: #003366;">📢 DIVULGACIONES AUTOMÁTICAS</h1>
        <p style="font-size: 1rem; color: #555;">Carga hasta 5 documentos (PDF o Excel). La IA extraerá los datos y podrás editarlos antes de enviar el correo.</p>
    </div>
""", unsafe_allow_html=True)

empresa_opciones = {
    "Clínica La Ermita": {"nombre": "CLÍNICA LA ERMITA", "color": "#6ab0de"},
    "Red Integrada de Ambulancia": {"nombre": "RED INTEGRADA DE AMBULANCIA", "color": "#5a7d9a"},
    "Coonegan": {"nombre": "COONEGAN", "color": "#5fad7a"}
}
empresa_seleccionada = st.selectbox("Empresa destinataria de la divulgación", list(empresa_opciones.keys()))
empresa_color = empresa_opciones[empresa_seleccionada]["color"]

tipo_operacion_global = st.radio(
    "Tipo de operación para todos los documentos",
    ["Creación", "Actualización"],
    index=1,
    horizontal=True
)

# ------------------------------------------------------------------
# Carga de archivos y clasificación (manual o normal)
# ------------------------------------------------------------------
archivos = st.file_uploader(
    "Selecciona los documentos (máx 5, PDF o Excel)",
    type=["pdf", "xlsx", "xls"],
    accept_multiple_files=True
)

if archivos and len(archivos) > 5:
    st.warning("Máximo 5 documentos. Solo se procesarán los primeros 5.")
    archivos = archivos[:5]

if archivos:
    st.subheader("📌 Clasificación de documentos")
    es_manual_dict = {}
    for idx, archivo in enumerate(archivos):
        es_manual_dict[archivo.name] = st.checkbox(f"🔹 {archivo.name} - ¿Marcar como Manual de funciones? (la versión y vigencia deberán llenarse manualmente)", key=f"manual_{idx}")

    if st.button("🚀 Procesar documentos con IA", use_container_width=True):
        documentos_info = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, archivo in enumerate(archivos):
            status_text.text(f"Procesando {archivo.name}...")
            es_manual = es_manual_dict.get(archivo.name, False)
            extension = os.path.splitext(archivo.name)[1].lower()
            try:
                if extension == ".pdf":
                    texto = extraer_texto_pdf(archivo, leer_completo=es_manual)
                elif extension in [".xlsx", ".xls"]:
                    texto = extraer_texto_excel(archivo)
                else:
                    st.error(f"Formato no soportado: {archivo.name}")
                    continue
            except Exception as e:
                st.error(f"Error al extraer texto de {archivo.name}: {e}")
                continue

            if not texto.strip():
                st.error(f"No se pudo extraer texto de {archivo.name}. Se omite.")
                continue

            try:
                datos = analizar_documento(texto, archivo.name, es_manual=es_manual)
            except Exception as e:
                st.error(f"Error en IA para {archivo.name}: {e}")
                datos = {}

            # Si es manual, forzar código a "No Aplica" (si no tiene código)
            if es_manual:
                if not datos.get("codigo"):
                    datos["codigo"] = "No Aplica"

            documentos_info.append({
                "nombre": archivo.name,
                "datos": datos,
                "tipo": tipo_operacion_global,
                "es_manual": es_manual
            })
            progress_bar.progress((i+1)/len(archivos))

        status_text.text("¡Análisis completado!")
        st.session_state["documentos_info"] = documentos_info
        st.rerun()

    if "documentos_info" in st.session_state and st.session_state["documentos_info"] is not None:
        st.divider()
        st.subheader("✏️ Edición de datos extraídos")
        st.info("✏️ Los cambios se guardan automáticamente. Puedes editar todos los campos y luego hacer clic en 'Enviar correo'.")

        for idx, doc in enumerate(st.session_state["documentos_info"]):
            datos = doc["datos"]
            with st.expander(f"📄 Documento {idx+1}: {doc['nombre']}", expanded=True):
                # Mostrar si es manual y permitir cambiar la clasificación (esto actualizará los campos)
                es_manual_edit = st.checkbox("🔹 ¿Es manual de funciones? (versión y vigencia se llenan manualmente)", value=doc.get("es_manual", False), key=f"edit_manual_{idx}")
                if es_manual_edit != doc.get("es_manual", False):
                    doc["es_manual"] = es_manual_edit
                    if es_manual_edit:
                        datos["codigo"] = "No Aplica"
                        datos["version"] = ""
                        datos["vigencia"] = ""
                    st.session_state["documentos_info"][idx]["es_manual"] = es_manual_edit
                    st.session_state["documentos_info"][idx]["datos"] = datos
                    st.rerun()

                proceso_sugerido = datos.get("proceso", "").strip()
                proceso_norm = normalizar_texto(proceso_sugerido)
                try:
                    idx_proceso = PROCESOS_NORM.index(proceso_norm)
                except ValueError:
                    idx_proceso = 0
                nuevo_proceso = st.selectbox("Proceso", PROCESOS, index=idx_proceso, key=f"proceso_{idx}")
                nuevo_codigo = st.text_input("Código", datos.get("codigo", ""), key=f"codigo_{idx}")
                nuevo_version = st.text_input("Versión", datos.get("version", ""), key=f"version_{idx}")
                nuevo_documento = st.text_input("Documento", datos.get("documento", ""), key=f"documento_{idx}")
                nuevo_vigencia = st.text_input("Vigencia (YYYY.MM.DD)", datos.get("vigencia", ""), key=f"vigencia_{idx}")
                nuevo_importancia = st.text_area("Importancia", datos.get("importancia", ""), key=f"importancia_{idx}", height=80)

                st.session_state["documentos_info"][idx]["datos"] = {
                    "proceso": nuevo_proceso,
                    "codigo": nuevo_codigo,
                    "version": nuevo_version,
                    "documento": nuevo_documento,
                    "vigencia": nuevo_vigencia,
                    "importancia": nuevo_importancia,
                    "cargo": datos.get("cargo", ""),
                    "consecutivo": datos.get("consecutivo", "")
                }

        st.divider()
        st.subheader("📧 Envío de correo")
        destinatarios_input = st.text_input(
            "Correos destinatarios (Para, separados por coma)",
            value=""
        )
        if st.button("📨 Enviar correo de divulgación", use_container_width=True):
            destinatarios_lista = [d.strip() for d in destinatarios_input.split(",") if d.strip()]
            if not destinatarios_lista:
                st.error("Debes ingresar al menos un destinatario en el campo Para.")
                st.stop()

            cc_fijos = [
                "coord-procesos@clinicalaermitadecartagena.com",
                "profesional-procesos2@clinicalaermitadecartagena.com",
                "asistente-procesos@clinicalaermitadecartagena.com",
                "aprendiz-procesos2@clinicalaermitadecartagena.com",
                "lidercalidad-procesos@clinicalaermitadecartagena.com"
            ]

            docs = st.session_state["documentos_info"]

            lista_items = []
            for doc in docs:
                datos = doc["datos"]
                es_manual = doc.get("es_manual", False)
                if es_manual:
                    nombre = datos.get("cargo", os.path.splitext(doc["nombre"])[0])
                else:
                    nombre = f"{datos.get('codigo', '')} {datos.get('documento', '')}".strip()
                if nombre:
                    lista_items.append(f"<li>{nombre}</li>")
            lista_nombres_str = "<ul style='margin: 0; padding-left: 20px;'>" + "".join(lista_items) + "</ul>" if lista_items else "Sin documentos"

            proceso_encabezado = docs[0]["datos"].get("proceso", "GESTIÓN DEL TALENTO HUMANO")
            operacion_texto = tipo_operacion_global.lower()

            tarjetas_html = ""
            for doc in docs:
                datos = doc["datos"]
                es_manual = doc.get("es_manual", False)
                codigo = str(datos.get("codigo", ""))
                tipo_doc = get_tipo_documento(codigo)

                if es_manual:
                    nombre_documento = datos.get("cargo", os.path.splitext(doc["nombre"])[0])
                    codigo_tabla = "No Aplica"
                else:
                    nombre_documento = f"{tipo_doc} {codigo} {datos.get('documento', '')}".strip()
                    codigo_tabla = codigo or "N/A"

                version = datos.get("version", "") or "N/A"
                vigencia = datos.get("vigencia", "") or "N/A"
                importancia = datos.get("importancia", "") or "N/A"

                tarjetas_html += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; margin-bottom: 20px;">
                    <tr>
                        <td style="background-color: #f4f4f4; padding: 10px 15px; border: 1px solid #cccccc; border-bottom: none;">
                            <strong style="font-size: 16px; color: #003366;">📄 {nombre_documento}</strong>
                        </td>
                    </tr>
                    <tr>
                        <td style="border: 1px solid #cccccc; padding: 0;">
                            <table width="100%" cellpadding="8" cellspacing="0" border="0" style="border-collapse: collapse;">
                                <tr>
                                    <td width="30%" style="background-color: {empresa_color}; color: white; font-weight: bold; border-bottom: 1px solid #dddddd;">VERSIÓN</td>
                                    <td width="70%" style="border-bottom: 1px solid #dddddd;">{version}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: {empresa_color}; color: white; font-weight: bold; border-bottom: 1px solid #dddddd;">CÓDIGO</td>
                                    <td style="border-bottom: 1px solid #dddddd;">{codigo_tabla}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: {empresa_color}; color: white; font-weight: bold; border-bottom: 1px solid #dddddd;">VIGENCIA</td>
                                    <td style="border-bottom: 1px solid #dddddd;">{vigencia}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: {empresa_color}; color: white; font-weight: bold;">IMPORTANCIA</td>
                                    <td>{importancia}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
                """

            cuerpo_html = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="margin:0; padding:0; font-family: Arial, sans-serif; background-color: #f4f7f9;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f4f7f9;">
                    <tr><td align="center">
                        <table width="700" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; border-collapse: collapse;">
                            <tr><td style="background-color: {empresa_color}; color: #ffffff; padding: 20px 30px;">
                                <h1 style="margin:0 0 10px; font-size:22px;">Divulgación de Documentos</h1>
                                <div style="font-size:13px; border-top:1px solid rgba(255,255,255,0.3); padding-top:12px;">
                                    <strong>Documentos asociados:</strong><br>{lista_nombres_str}
                                </div>
                            </td>
                            </tr>
                            <tr><td style="padding:20px 30px;">
                                <table width="100%" style="background-color:#f0f7ff; border:1px solid {empresa_color};">
                                    <tr><td style="padding:15px; text-align:center; color:#004085;">
                                        El equipo de <strong>{proceso_encabezado}</strong> ha logrado un avance en la {operacion_texto} documental y gestión del conocimiento en su área.
                                    </td>
                                    </tr>
                                </table>
                            </td>
                            </tr>
                            <tr><td style="padding:10px 30px;">{tarjetas_html}</td>
                            <tr>
                            <tr><td style="padding:0 30px 20px 30px;">
                                <table width="100%" style="background-color:#fff3f3; border-left:4px solid #cc0000;">
                                    <tr><td style="padding:15px;">
                                        <h4 style="margin:0 0 10px; color:#cc0000;">📢 SOCIALIZACIÓN Y APLICACIÓN INMEDIATA</h4>
                                        <ul><li>El líder del proceso es el responsable de socializar el documento con su equipo.</li>
                                        <li><strong style="color:#cc0000;">Conforme a lo establecido P-PRC-001 Procedimiento de Control Documental, el líder del Proceso tiene 3 días hábiles para la socialización del documento.</strong></li></ul>
                                    </td>
                                    </tr>
                                </table>
                            </td>
                            </tr>
                            <tr><td style="padding:0 30px 20px 30px;">
                                <table width="100%" style="background-color:#f8f9fa; border:1px solid #d1d5db;">
                                    <tr><td style="padding:20px; text-align:center;">
                                        <h3 style="margin:0 0 10px; color:#003366;">Acceso a Plataforma IT SOLUTION</h3>
                                        <p><strong>Ruta:</strong> Gestión Documental → Consultar Documentos → (Seleccionar empresa) → Filtrar por nombre.</p>
                                        <a href="http://172.16.20.166:8080/ItSolution/index.jsp" style="background-color:{empresa_color}; color:#fff; padding:12px 24px; text-decoration:none; display:inline-block;">Abrir IT SOLUTION</a>
                                    </td>
                                    </tr>
                                </tr>
                            </td>
                            </tr>
                            <tr><td style="background-color:#f8f9fa; padding:20px; text-align:center; font-size:12px; color:#777; border-top:1px dashed #ccc;">
                                <p style="font-weight:bold; color:#003366;">¡HAZ PARTE DEL CAMBIO!</p>
                                <p>#TransformaciónDigitalDeLosProcesos</p>
                                <p><em>Este correo es un desarrollo automático con inteligencia artificial, por favor no responder a este mensaje.</em></p>
                                <p>Si desea comunicarse con el área de procesos, escriba a:<br>{', '.join(cc_fijos)}</p>
                            </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                </tr>
            </body>
            </html>
            """

            asunto = f"Divulgación de Documentos - {datetime.now().strftime('%Y.%m.%d')} - {empresa_seleccionada}"

            with st.spinner("Enviando correo..."):
                if enviar_correo(destinatarios_lista, cc_fijos, asunto, cuerpo_html):
                    st.success("✅ Correo enviado correctamente.")
                else:
                    st.error("❌ Falló el envío. Revisa la configuración SMTP.")
