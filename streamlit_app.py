import streamlit as st
import os
import PyPDF2
import docx
import google.generativeai as genai
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
    "INVESTIGACIÓN", "VIGILANCIA EPIDEMIOLÓGICA Y SEGURIDAD"
]

# ------------------------------------------------------------------
# FUNCIONES AUXILIARES
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

def analizar_documento(texto):
    prompt = f"""
    Eres un asistente que extrae información de documentos internos de una clínica.
    Devuelve ÚNICAMENTE un objeto JSON válido con las claves:
    - "proceso" (debe coincidir exactamente con la lista)
    - "codigo"
    - "version"
    - "documento"
    - "vigencia" (en formato DD/MM/AAAA)
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

def enviar_correo(destinatarios, asunto, cuerpo):
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(destinatarios)
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo, "plain"))

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

# ------------------------------------------------------------------
# 1. Carga de múltiples archivos
# ------------------------------------------------------------------
archivos = st.file_uploader(
    "Selecciona los documentos (máx 5)",
    type=["pdf", "docx"],
    accept_multiple_files=True
)

if archivos and len(archivos) > 5:
    st.warning("Máximo 5 documentos. Solo se procesarán los primeros 5.")
    archivos = archivos[:5]

if archivos:
    # ------------------------------------------------------------------
    # 2. Procesar cada archivo
    # ------------------------------------------------------------------
    documentos_info = []
    st.write("---")
    for i, archivo in enumerate(archivos, start=1):
        st.subheader(f"Documento {i}: {archivo.name}")

        # Extraer texto
        with st.spinner(f"Extrayendo texto de {archivo.name}..."):
            if archivo.type == "application/pdf":
                texto = extraer_texto_pdf(archivo)
            else:
                texto = extraer_texto_docx(archivo)

        if not texto.strip():
            st.error(f"No se pudo extraer texto del documento {archivo.name}. Se omite.")
            continue

        # Analizar con Gemini
        with st.spinner(f"Analizando {archivo.name} con IA..."):
            try:
                datos = analizar_documento(texto)
            except Exception as e:
                st.error(f"Error en IA para {archivo.name}: {e}")
                continue

        # Mostrar datos extraídos y permitir edición
        col1, col2 = st.columns([3, 1])
        with col1:
            st.json(datos)
        with col2:
            tipo = st.radio(
                "Tipo de operación",
                ["Creación", "Actualización"],
                key=f"tipo_{i}",
                horizontal=True
            )

        # Botón para editar manualmente si es necesario
        with st.expander("✏️ Editar datos manualmente"):
            datos["proceso"] = st.selectbox("Proceso", PROCESOS, index=PROCESOS.index(datos.get("proceso", PROCESOS[0])), key=f"proceso_{i}")
            datos["codigo"] = st.text_input("Código", datos.get("codigo", ""), key=f"codigo_{i}")
            datos["version"] = st.text_input("Versión", datos.get("version", ""), key=f"version_{i}")
            datos["documento"] = st.text_input("Documento", datos.get("documento", ""), key=f"documento_{i}")
            datos["vigencia"] = st.text_input("Vigencia", datos.get("vigencia", ""), key=f"vigencia_{i}")
            datos["importancia"] = st.text_area("Importancia", datos.get("importancia", ""), key=f"importancia_{i}", height=80)

        documentos_info.append({
            "nombre_archivo": archivo.name,
            "datos": datos,
            "tipo": tipo
        })
        st.write("---")

    # ------------------------------------------------------------------
    # 3. Configurar destinatarios y enviar correo
    # ------------------------------------------------------------------
    if documentos_info:
        destinatarios_input = st.text_input(
            "Correos destinatarios (separados por coma)",
            value="asistenteprocesosermita@gmail.com"
        )
        if st.button("📨 Enviar correo con todos los documentos"):
            destinatarios_lista = [d.strip() for d in destinatarios_input.split(",") if d.strip()]
            if not destinatarios_lista:
                st.error("Debes ingresar al menos un destinatario.")
                st.stop()

            # Construir el cuerpo del correo con formato solicitado
            cuerpo = "Buen día,\n\n"
            for doc in documentos_info:
                datos = doc["datos"]
                tipo = doc["tipo"].lower()
                fecha_vigencia = datos.get("vigencia", "fecha no especificada")
                accion = "creado" if tipo == "creación" else "actualizado"
                codigo_doc = datos.get("codigo", "sin código")
                nombre_doc = datos.get("documento", "sin título")

                cuerpo += f"Les informo que se encuentra disponible para su consulta el registro **{codigo_doc} {nombre_doc}** de la empresa CLÍNICA LA ERMITA, {accion} el {fecha_vigencia}.\n\n"
                cuerpo += f"Fecha de vigencia: {fecha_vigencia}\n\n"

            cuerpo += "Pueden acceder al documento en la plataforma IT SOLUTION siguiendo esta ruta:\n"
            cuerpo += "• Ruta: Gestión Documental → Consultar Documentos → (Seleccionar empresa) → Filtrar por nombre.\n"
            cuerpo += "• Enlace: http://190.131.206.250:8085/ItSolution/index.jsp\n\n"
            cuerpo += "Agradecemos su atención y cumplimiento.\n\nCordialmente,\nÁrea de procesos\nClínica La Ermita"

            asunto = "Actualización de Documentos - Clínica La Ermita"

            with st.spinner("Enviando correo..."):
                if enviar_correo(destinatarios_lista, asunto, cuerpo):
                    st.success("✅ Correo enviado correctamente.")
                else:
                    st.error("❌ Falló el envío. Revisa la configuración SMTP.")
