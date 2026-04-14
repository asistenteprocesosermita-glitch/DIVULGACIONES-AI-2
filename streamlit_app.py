import streamlit as st
import os
import PyPDF2
import google.generativeai as genai
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from unicodedata import normalize  # Para normalización de texto

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
# LISTA DE PROCESOS (completa)
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
    "INVESTIGACIÓN", "VIGILANCIA EPIDEMIOLÓGICA Y SEGURIDAD"
]

# Función auxiliar para normalizar texto (eliminar acentos y mayúsculas)
def normalizar_texto(texto):
    if not texto:
        return ""
    texto = normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return texto.strip().upper()

# Pre-calcular versiones normalizadas de PROCESOS para búsqueda rápida
PROCESOS_NORM = [normalizar_texto(p) for p in PROCESOS]

# ------------------------------------------------------------------
# MAPEO DE TIPO DE DOCUMENTO SEGÚN CÓDIGO
# ------------------------------------------------------------------
def get_tipo_documento(codigo):
    if not codigo:
        return "documento"
    partes = codigo.split('-')
    prefijo = partes[0].upper() if partes else ""
    mapeo = {
        "D": "Política o Directriz",
        "C": "Caracterización de proceso",
        "PG": "Programa",
        "M": "Manual",
        "P": "Procedimiento",
        "G": "Guía",
        "PR": "Protocolo",
        "I": "Instructivo",
        "RT": "Ruta",
        "R": "Formato"
    }
    if prefijo in mapeo:
        return mapeo[prefijo]
    if len(prefijo) == 1 and prefijo in mapeo:
        return mapeo[prefijo]
    return "documento"

# ------------------------------------------------------------------
# EXTRACCIÓN DE TEXTO (solo PDF)
# ------------------------------------------------------------------
def extraer_texto_pdf(archivo):
    texto = ""
    pdf = PyPDF2.PdfReader(archivo)
    for pagina in pdf.pages:
        texto += pagina.extract_text() or ""
    return texto

# ------------------------------------------------------------------
# ANÁLISIS CON GEMINI (incluye campos extra para manuales)
# ------------------------------------------------------------------
def analizar_documento(texto, filename):
    prompt = f"""
    Eres un asistente que extrae información de documentos internos de una clínica.
    Devuelve ÚNICAMENTE un objeto JSON válido con las siguientes claves:
    - "proceso": el proceso responsable (debe coincidir exactamente con la lista)
    - "codigo": el código del documento (ej. M-SST-003, R-TH-003, etc.)
    - "version": la versión del documento (formato XX, ej. 01, 02). Si es un manual de funciones, extrae el valor después de "Consecutivo:".
    - "documento": el nombre completo del documento.
    - "vigencia": la fecha desde que aplica (formato YYYY.MM.DD). Si es manual de funciones, extrae la fecha más reciente del control de versiones.
    - "importancia": un resumen de máximo 15 palabras.
    - "cargo": si el documento es un manual de funciones (código comienza con R-TH-), extrae el nombre del cargo al que pertenece. Si no, puedes omitirlo.
    - "consecutivo": si el documento es manual de funciones, extrae el número de consecutivo (ej. 01, 02) tal como aparece junto a "Consecutivo:".

    Lista de procesos:
    {', '.join(PROCESOS)}

    Texto del documento:
    {texto}
    """
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)
    texto_respuesta = response.text
    inicio = texto_respuesta.find('{')
    fin = texto_respuesta.rfind('}') + 1
    if inicio != -1 and fin != 0:
        datos = json.loads(texto_respuesta[inicio:fin])
        # Ajuste para manuales: si es manual y no se extrajo cargo, usar el nombre del archivo
        if datos.get("codigo", "").upper().startswith("R-TH-"):
            if not datos.get("cargo"):
                base = os.path.splitext(os.path.basename(filename))[0]
                datos["cargo"] = base
            if datos.get("consecutivo"):
                datos["version"] = f"Consecutivo: {datos['consecutivo']}"
        return datos
    else:
        raise ValueError("No se encontró JSON en la respuesta")

# ------------------------------------------------------------------
# ENVÍO DE CORREO CON HTML (colores dinámicos según empresa)
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

# Título en mayúsculas y descripción mejorada
st.markdown("""
    <div style="text-align: center; margin-bottom: 20px;">
        <h1 style="font-size: 2.5rem; font-weight: bold; color: #003366;">📢 DIVULGACIONES AUTOMÁTICAS</h1>
        <p style="font-size: 1rem; color: #555;">Carga hasta 5 documentos en PDF. Para cada uno, la IA extraerá los datos y podrás definir la empresa y si es Creación o Actualización. Luego se enviará un único correo con el resumen de todos.</p>
    </div>
""", unsafe_allow_html=True)

# Selección de empresa (con colores pastel)
empresa_opciones = {
    "Clínica La Ermita": {"nombre": "CLÍNICA LA ERMITA", "color": "#6ab0de"},
    "Red Integrada de Ambulancia": {"nombre": "RED INTEGRADA DE AMBULANCIA", "color": "#5a7d9a"},
    "Coonegan": {"nombre": "COONEGAN", "color": "#5fad7a"}
}
empresa_seleccionada = st.selectbox("Empresa destinataria de la divulgación", list(empresa_opciones.keys()))
empresa_nombre = empresa_opciones[empresa_seleccionada]["nombre"]
empresa_color = empresa_opciones[empresa_seleccionada]["color"]

# Selector global de tipo de operación
tipo_operacion_global = st.radio(
    "Tipo de operación para todos los documentos",
    ["Creación", "Actualización"],
    index=1,  # Por defecto "Actualización"
    horizontal=True
)

# Carga de archivos (solo PDF)
archivos = st.file_uploader(
    "Selecciona los documentos (máx 5, solo PDF)",
    type=["pdf"],
    accept_multiple_files=True
)

if archivos and len(archivos) > 5:
    st.warning("Máximo 5 documentos. Solo se procesarán los primeros 5.")
    archivos = archivos[:5]

# Procesamiento
if archivos:
    st.session_state["archivos_subidos"] = archivos
    st.info("✅ Documentos cargados. Haz clic en 'Procesar' para analizarlos con IA y preparar los datos para el envío del correo.")
            
    if st.button("🚀 Procesar", use_container_width=True):
        documentos_info = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, archivo in enumerate(archivos):
            status_text.text(f"Procesando {archivo.name}...")
            texto = extraer_texto_pdf(archivo)

            if not texto.strip():
                st.error(f"No se pudo extraer texto de {archivo.name}. Se omite.")
                continue

            try:
                datos = analizar_documento(texto, archivo.name)
            except Exception as e:
                st.error(f"Error en IA para {archivo.name}: {e}")
                continue

            with st.expander(f"📄 Documento {i+1}: {archivo.name} - Editar datos", expanded=True):
                st.json(datos)
                
                # --- Manejo seguro del proceso ---
                proceso_sugerido = datos.get("proceso", "").strip()
                # Normalizar el sugerido para comparar
                proceso_norm = normalizar_texto(proceso_sugerido)
                try:
                    # Buscar índice usando la lista normalizada
                    idx_proceso = PROCESOS_NORM.index(proceso_norm)
                except ValueError:
                    # Si no coincide, usar el primer elemento (índice 0)
                    idx_proceso = 0
                datos["proceso"] = st.selectbox("Proceso", PROCESOS, index=idx_proceso, key=f"proceso_{i}")
                
                datos["codigo"] = st.text_input("Código", datos.get("codigo", ""), key=f"codigo_{i}")
                datos["version"] = st.text_input("Versión", datos.get("version", ""), key=f"version_{i}")
                datos["documento"] = st.text_input("Documento", datos.get("documento", ""), key=f"documento_{i}")
                datos["vigencia"] = st.text_input("Vigencia (YYYY.MM.DD)", datos.get("vigencia", ""), key=f"vigencia_{i}")
                datos["importancia"] = st.text_area("Importancia", datos.get("importancia", ""), key=f"importancia_{i}", height=80)

            documentos_info.append({
                "nombre": archivo.name,
                "datos": datos,
                "tipo": tipo_operacion_global
            })
            progress_bar.progress((i+1)/len(archivos))

        status_text.text("¡Análisis completado!")
        st.session_state["documentos_info"] = documentos_info

    if "documentos_info" in st.session_state and st.session_state["documentos_info"]:
        st.divider()
        destinatarios_input = st.text_input(
            "Correos destinatarios (Para, separados por coma)",
            value=""
        )

        if st.button("📨 Enviar correo con todos los documentos", use_container_width=True):
            destinatarios_lista = [d.strip() for d in destinatarios_input.split(",") if d.strip()]
            if not destinatarios_lista:
                st.error("Debes ingresar al menos un destinatario en el campo Para.")
                st.stop()

            cc_fijos = [
                "coord-procesos@clinicalaermitadecartagena.com",
                "profesionalprocesos2@clinicalaermitadecartagena.com",
                "asistente-procesos@clinicalaermitadecartagena.com",
                "aprendiz-procesos2@clinicalaermitadecartagena.com"
            ]

            # Lista de documentos (viñetas)
            lista_items = []
            for doc in st.session_state["documentos_info"]:
                datos = doc["datos"]
                if datos.get("codigo", "").upper().startswith("R-TH-"):
                    nombre = datos.get("cargo", os.path.splitext(doc["nombre"])[0])
                else:
                    nombre = f"{datos.get('codigo', '')} {datos.get('documento', '')}".strip()
                if nombre:
                    lista_items.append(f"<li>{nombre}</li>")
            lista_nombres_str = "<ul style='margin: 0; padding-left: 20px;'>" + "".join(lista_items) + "</ul>" if lista_items else "Sin documentos"

            proceso_encabezado = st.session_state["documentos_info"][0]["datos"].get("proceso", "GESTIÓN DEL TALENTO HUMANO")

            # Obtener la palabra clave según el tipo global (minúscula)
            operacion_texto = tipo_operacion_global.lower()  # "creación" o "actualización"

            # Generar tarjetas por documento
            tarjetas_html = ""
            for doc in st.session_state["documentos_info"]:
                datos = doc["datos"]
                tipo_doc = get_tipo_documento(datos.get("codigo", ""))

                if datos.get("codigo", "").upper().startswith("R-TH-"):
                    nombre_documento = datos.get("cargo", os.path.splitext(doc["nombre"])[0])
                    codigo_tabla = "No Aplica"
                else:
                    nombre_documento = f"{tipo_doc} {datos.get('codigo', '')} {datos.get('documento', '')}".strip()
                    codigo_tabla = datos.get("codigo", "") or "N/A"

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

            # Plantilla HTML completa con la palabra dinámica
            cuerpo_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
            </head>
            <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f7f9;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f4f7f9;">
                    <tr>
                        <td align="center">
                            <table width="700" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; border-collapse: collapse;">
                                <!-- Header con color de la empresa -->
                                <tr>
                                    <td style="background-color: {empresa_color}; color: #ffffff; padding: 20px 30px;">
                                        <h1 style="margin: 0 0 10px; font-size: 22px;">Divulgación de Documentos</h1>
                                        <div style="font-size: 13px; margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.3); padding-top: 12px;">
                                            <strong>Documentos asociados:</strong><br>
                                            {lista_nombres_str}
                                        </div>
                                    </td>
                                </tr>
                                <!-- Mensaje de avance con borde del color corporativo y palabra dinámica -->
                                <tr>
                                    <td style="padding: 20px 30px;">
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f0f7ff; border: 1px solid {empresa_color};">
                                            <tr>
                                                <td style="padding: 15px 20px; text-align: center; color: #004085;">
                                                    El equipo de <strong>{proceso_encabezado}</strong> ha logrado un avance en la {operacion_texto} documental y gestión del conocimiento en su área.
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <!-- Tarjetas de documentos -->
                                <tr>
                                    <td style="padding: 10px 30px;">
                                        {tarjetas_html}
                                    </td>
                                </tr>
                                <!-- Bloque socialización -->
                                <tr>
                                    <td style="padding: 0 30px 20px 30px;">
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #fff3f3; border-left: 4px solid #cc0000;">
                                            <tr>
                                                <td style="padding: 15px;">
                                                    <h4 style="margin: 0 0 10px; color: #cc0000;">📢 SOCIALIZACIÓN Y APLICACIÓN INMEDIATA</h4>
                                                    <ul style="margin: 0; padding-left: 20px;">
                                                        <li>El líder del proceso es el responsable de socializar el documento con su equipo.</li>
                                                        <li><strong style="color: #cc0000;">Conforme a lo establecido P-PRC-001 Procedimiento de Control Documental, el líder del Proceso tiene 3 días hábiles para la socialización del documento.</strong></li>
                                                    </ul>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <!-- Acceso IT SOLUTION -->
                                <tr>
                                    <td style="padding: 0 30px 20px 30px;">
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f8f9fa; border: 1px solid #d1d5db;">
                                            <tr>
                                                <td style="padding: 20px; text-align: center;">
                                                    <h3 style="margin: 0 0 10px; color: #003366;">Acceso a Plataforma IT SOLUTION</h3>
                                                    <p style="font-size: 14px; margin-bottom: 15px; text-align: left;">
                                                        Pueden acceder al documento oficial siguiendo esta ruta:<br>
                                                        <strong>Ruta:</strong> Gestión Documental → Consultar Documentos → (Seleccionar empresa) → Filtrar por nombre.
                                                    </p>
                                                    <a href="http://172.16.20.166:8080/ItSolution/index.jsp" style="background-color: {empresa_color}; color: #ffffff; padding: 12px 24px; text-decoration: none; font-weight: bold; display: inline-block;">Abrir IT SOLUTION</a>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <!-- Footer -->
                                <tr>
                                    <td style="background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #777777; border-top: 1px dashed #cccccc;">
                                        <p style="margin: 0 0 5px; font-weight: bold; color: #003366; font-size: 13px;">¡HAZ PARTE DEL CAMBIO!</p>
                                        <p style="margin: 0 0 15px;">#TransformaciónDigitalDeLosProcesos</p>
                                        <p style="margin: 0;"><em>Este correo es un desarrollo automático con inteligencia artificial, por favor no responder a este mensaje.</em></p>
                                        <p style="margin: 10px 0 0;">Si desea comunicarse con el área de procesos, escriba a:<br>
                                        {', '.join(cc_fijos)}</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """

            asunto = f"Divulgación de Documentos - {datetime.now().strftime('%Y.%m.%d')} - {empresa_seleccionada}"

            with st.spinner("Enviando correo..."):
                if enviar_correo(destinatarios_lista, cc_fijos, asunto, cuerpo_html):
                    st.success("✅ Correo enviado correctamente.")
                else:
                    st.error("❌ Falló el envío. Revisa la configuración SMTP.")
