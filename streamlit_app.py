import streamlit as st
import os
import PyPDF2
import docx
import google.generativeai as genai
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ------------------------------------------------------------------
# CONFIGURACIÓN DE CLAVES (desde secrets de Streamlit)
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
# EXTRACCIÓN DE TEXTO
# ------------------------------------------------------------------
def extraer_texto_pdf(archivo):
    texto = ""
    pdf = PyPDF2.PdfReader(archivo)
    for pagina in pdf.pages:
        texto += pagina.extract_text() or ""
    return texto

def extraer_texto_docx(archivo):
    doc = docx.Document(archivo)
    return "\n".join([p.text for p in doc.paragraphs])

# ------------------------------------------------------------------
# ANÁLISIS CON GEMINI
# ------------------------------------------------------------------
def analizar_documento(texto):
    prompt = f"""
    Eres un asistente que extrae información de documentos internos de una clínica.
    Devuelve ÚNICAMENTE un objeto JSON válido con las claves:
    - "proceso" (debe coincidir exactamente con la lista)
    - "codigo"
    - "version"
    - "documento"
    - "vigencia" (en formato YYYY.MM.DD, ejemplo: 2024.10.21)
    - "importancia" (máx 15 palabras)

    Lista de procesos:
    {', '.join(PROCESOS)}

    Texto:
    {texto}
    """
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)
    texto_respuesta = response.text
    inicio = texto_respuesta.find('{')
    fin = texto_respuesta.rfind('}') + 1
    if inicio != -1 and fin != 0:
        return json.loads(texto_respuesta[inicio:fin])
    else:
        raise ValueError("No se encontró JSON en la respuesta")

# ------------------------------------------------------------------
# ENVÍO DE CORREO CON HTML (nuevo diseño)
# ------------------------------------------------------------------
def enviar_correo(destinatarios, cc_list, asunto, cuerpo_html):
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(destinatarios)
        msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo_html, "html"))

        todos = destinatarios + cc_list
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
st.set_page_config(page_title="Divulgaciones AI - Múltiples Documentos", layout="centered")
st.title("📢 Divulgaciones Automáticas (Múltiples Documentos)")
st.markdown("Carga hasta 5 documentos (PDF/Word). Para cada uno, la IA extraerá los datos y podrás definir si es **Creación** o **Actualización**. Luego se enviará un único correo con el resumen de todos.")

# Selección de empresa
empresa_opciones = {
    "Clínica La Ermita": "CLÍNICA LA ERMITA",
    "Red Integrada de Ambulancia": "RED INTEGRADA DE AMBULANCIA",
    "Coonegan": "COONEGAN"
}
empresa_seleccionada = st.selectbox("Empresa destinataria de la divulgación", list(empresa_opciones.keys()))
empresa_nombre = empresa_opciones[empresa_seleccionada]

# Carga de archivos
archivos = st.file_uploader(
    "Selecciona los documentos (máx 5)",
    type=["pdf", "docx"],
    accept_multiple_files=True
)

if archivos and len(archivos) > 5:
    st.warning("Máximo 5 documentos. Solo se procesarán los primeros 5.")
    archivos = archivos[:5]

if archivos:
    st.session_state["archivos_subidos"] = archivos
    st.info("Documentos cargados. Haz clic en 'Procesar y enviar' para analizarlos con IA y enviar el correo.")

    if st.button("🚀 Procesar y enviar correo"):
        documentos_info = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, archivo in enumerate(archivos):
            status_text.text(f"Procesando {archivo.name}...")
            if archivo.type == "application/pdf":
                texto = extraer_texto_pdf(archivo)
            else:
                texto = extraer_texto_docx(archivo)

            if not texto.strip():
                st.error(f"No se pudo extraer texto de {archivo.name}. Se omite.")
                continue

            try:
                datos = analizar_documento(texto)
            except Exception as e:
                st.error(f"Error en IA para {archivo.name}: {e}")
                continue

            with st.expander(f"Documento {i+1}: {archivo.name} - Editar datos"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.json(datos)
                with col2:
                    tipo = st.radio("Tipo", ["Creación", "Actualización"], key=f"tipo_{i}", horizontal=True)

                # Permitir edición manual
                datos["proceso"] = st.selectbox("Proceso", PROCESOS, index=PROCESOS.index(datos.get("proceso", PROCESOS[0])), key=f"proceso_{i}")
                datos["codigo"] = st.text_input("Código", datos.get("codigo", ""), key=f"codigo_{i}")
                datos["version"] = st.text_input("Versión", datos.get("version", ""), key=f"version_{i}")
                datos["documento"] = st.text_input("Documento", datos.get("documento", ""), key=f"documento_{i}")
                datos["vigencia"] = st.text_input("Vigencia (YYYY.MM.DD)", datos.get("vigencia", ""), key=f"vigencia_{i}")
                datos["importancia"] = st.text_area("Importancia", datos.get("importancia", ""), key=f"importancia_{i}", height=80)

            documentos_info.append({
                "nombre": archivo.name,
                "datos": datos,
                "tipo": tipo
            })
            progress_bar.progress((i+1)/len(archivos))

        status_text.text("¡Análisis completado!")
        st.session_state["documentos_info"] = documentos_info

    if "documentos_info" in st.session_state and st.session_state["documentos_info"]:
        st.divider()
        destinatarios_input = st.text_input(
            "Correos destinatarios (Para, separados por coma)",
            value="asistenteprocesosermita@gmail.com"
        )

        if st.button("📨 Enviar correo con todos los documentos"):
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

            # -------- Construir listado de documentos para el encabezado --------
            listado_docs = []
            for doc in st.session_state["documentos_info"]:
                datos = doc["datos"]
                cod = datos.get("codigo", "")
                nom = datos.get("documento", "")
                if cod and nom:
                    listado_docs.append(f"{cod} {nom}")
                elif cod:
                    listado_docs.append(cod)
                elif nom:
                    listado_docs.append(nom)
            listado_docs_str = "<br>".join(listado_docs) if listado_docs else "Sin documentos"

            # Proceso principal (tomar el primer documento o default)
            proceso_principal = st.session_state["documentos_info"][0]["datos"].get("proceso", "GESTIÓN DEL TALENTO HUMANO")

            # Fecha actual en formato DD.MM.AAAA
            fecha_actual = datetime.now().strftime("%d.%m.%Y")

            # Asunto dinámico
            asunto = f"DIVULGACIÓN DE DOCUMENTOS - {proceso_principal} - {fecha_actual} - {empresa_seleccionada}"

            # -------- Construir tarjetas por documento --------
            tarjetas_html = ""
            for doc in st.session_state["documentos_info"]:
                datos = doc["datos"]
                # Limpieza de datos nulos
                version = datos.get("version", "") or "---"
                codigo = datos.get("codigo", "") or "---"
                vigencia = datos.get("vigencia", "") or "---"
                importancia = datos.get("importancia", "") or "---"
                tipo_doc = get_tipo_documento(datos.get("codigo", ""))
                nombre_documento = f"{tipo_doc} {datos.get('codigo', '')} {datos.get('documento', '')}".strip()
                if not nombre_documento:
                    nombre_documento = "Documento sin título"

                tarjetas_html += f"""
                <div style="border: 1px solid #e1e8ed; border-radius: 6px; margin-bottom: 25px;">
                    <div style="background-color: #f8f9fa; padding: 12px 15px; border-bottom: 1px solid #e1e8ed; display: flex; align-items: center;">
                        <span style="font-size: 18px; margin-right: 10px;">📄</span>
                        <strong style="color: #333; font-size: 14px;">{nombre_documento}</strong>
                    </div>
                    <table width="100%" cellpadding="10" cellspacing="0" style="font-size: 13px; border-collapse: collapse;">
                        <tr style="border-bottom: 1px solid #f1f1f1;">
                            <td width="30%" style="color: #666; font-weight: bold; background-color: #fafafa;">VERSIÓN</td>
                            <td width="70%">{version}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f1f1f1;">
                            <td style="color: #666; font-weight: bold; background-color: #fafafa;">CÓDIGO</td>
                            <td>{codigo}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f1f1f1;">
                            <td style="color: #666; font-weight: bold; background-color: #fafafa;">VIGENCIA</td>
                            <td>{vigencia}</td>
                        </tr>
                        <tr>
                            <td style="color: #666; font-weight: bold; background-color: #fafafa;">IMPORTANCIA</td>
                            <td style="line-height: 1.4;">{importancia}</td>
                        </tr>
                    </table>
                </div>
                """

            # Plantilla HTML completa (basada en la última versión)
            cuerpo_html = f"""
            <!DOCTYPE html>
            <html lang="es">
            <head>
                <meta charset="UTF-8">
            </head>
            <body style="margin: 0; padding: 0; background-color: #f4f7f9;">
                <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 700px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
                    
                    <div style="background-color: #003366; color: #ffffff; padding: 30px; border-bottom: 4px solid #0056b3;">
                        <h1 style="margin: 0 0 12px 0; font-size: 22px; letter-spacing: 0.5px;">Divulgación de Documentos</h1>
                        <div style="font-size: 13px; line-height: 1.5; color: #b3d1ff; font-weight: 400; border-top: 1px solid #1a4d80; padding-top: 12px;">
                            <strong>Documentos asociados:</strong><br>
                            {listado_docs_str}
                        </div>
                    </div>

                    <div style="padding: 25px 30px 10px 30px;">
                        <div style="background-color: #f0f7ff; border: 1px solid #cfe2ff; padding: 15px 20px; border-radius: 6px; text-align: center;">
                            <p style="margin: 0; font-size: 15px; color: #004085; line-height: 1.4;">
                                El equipo de <strong>{proceso_principal}</strong> ha logrado un avance en la actualización documental y gestión del conocimiento en su área.
                            </p>
                        </div>
                    </div>

                    <div style="padding: 10px 30px;">
                        {tarjetas_html}
                    </div>

                    <div style="margin: 10px 30px 30px 30px; padding: 25px; background-color: #ffffff; border: 2px dashed #003366; border-radius: 8px; text-align: center;">
                        <h3 style="margin: 0 0 15px 0; color: #003366; font-size: 17px;">📍 Acceso a Plataforma IT SOLUTION</h3>
                        <p style="font-size: 13px; color: #555; margin-bottom: 20px; text-align: left;">
                            <strong>Ruta de acceso:</strong><br>
                            Gestión Documental → Consultar Documentos → (Seleccionar empresa) → Filtrar por nombre.
                        </p>
                        <a href="http://172.16.20.166:8080/ItSolution/Formulario.jsp" 
                           style="background-color: #28a745; color: #ffffff; padding: 14px 40px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; font-size: 15px; box-shadow: 0 2px 5px rgba(40,167,69,0.3);">
                           INGRESAR A LA PLATAFORMA
                        </a>
                    </div>

                    <div style="background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 11px; color: #888;">
                        <p style="margin: 0 0 5px 0; font-weight: bold; color: #003366; font-size: 13px;">¡HAZ PARTE DEL CAMBIO!</p>
                        <p style="margin: 0 0 15px 0;">#TransformaciónDigitalDeLosProcesos</p>
                        <p style="font-style: italic;">Este es un correo automático generado por IA. Por favor, no responda a este mensaje.</p>
                        <p>Si desea comunicarse con el área de procesos, escriba a:<br>
                        {', '.join(cc_fijos)}</p>
                    </div>
                </div>
            </body>
            </html>
            """

            with st.spinner("Enviando correo..."):
                if enviar_correo(destinatarios_lista, cc_fijos, asunto, cuerpo_html):
                    st.success("✅ Correo enviado correctamente.")
                else:
                    st.error("❌ Falló el envío. Revisa la configuración SMTP.")
