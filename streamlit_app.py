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
# LISTA DE PROCESOS (misma que usabas)
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
# LLAMADA A GEMINI
# ------------------------------------------------------------------
def analizar_documento(texto):
    prompt = f"""
    Eres un asistente que extrae información de documentos internos de una clínica.
    Devuelve ÚNICAMENTE un JSON válido con las claves:
    - "proceso" (debe coincidir exactamente con la lista)
    - "codigo"
    - "version"
    - "documento"
    - "vigencia"
    - "importancia" (máx 15 palabras)

    Lista de procesos:
    {', '.join(PROCESOS)}

    Texto:
    {texto}
    """
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)
    texto_respuesta = response.text
    # Extraer JSON
    inicio = texto_respuesta.find('{')
    fin = texto_respuesta.rfind('}') + 1
    if inicio != -1 and fin != 0:
        return json.loads(texto_respuesta[inicio:fin])
    else:
        raise ValueError("No se encontró JSON en la respuesta")

# ------------------------------------------------------------------
# ENVÍO DE CORREO
# ------------------------------------------------------------------
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
st.set_page_config(page_title="Divulgaciones AI", layout="centered")
st.title("📢 Divulgaciones Automáticas")
st.markdown("Sube un documento (PDF o Word) y se enviará un correo con los datos extraídos por IA.")

archivo = st.file_uploader("Documento", type=["pdf", "docx"])

if archivo is not None:
    st.write(f"**Archivo:** {archivo.name}")

    # Opción: ingresar destinatarios manualmente o usar lista predefinida
    destinatarios = st.text_input(
        "Correos destinatarios (separados por coma)",
        value="asistente-procesos@clinicalaermitadecartagena.com"
    )

    if st.button("🚀 Procesar y enviar"):
        # 1. Extraer texto
        with st.spinner("Extrayendo texto del documento..."):
            if archivo.type == "application/pdf":
                texto = extraer_texto_pdf(archivo)
            else:
                texto = extraer_texto_docx(archivo)

        if not texto.strip():
            st.error("No se pudo extraer texto. ¿El documento es escaneado?")
            st.stop()

        # 2. Analizar con Gemini
        with st.spinner("Analizando con Gemini..."):
            try:
                datos = analizar_documento(texto)
            except Exception as e:
                st.error(f"Error en IA: {e}")
                st.stop()

        st.success("Datos extraídos:")
        st.json(datos)

        # 3. Armar correo
        asunto = f"Actualización de Documento - {datos.get('documento', 'Sin título')}"
        cuerpo = f"""
Buen día,

Cordial saludo.

Se ha procesado el documento:

Proceso: {datos.get('proceso')}
Código: {datos.get('codigo')}
Versión: {datos.get('version')}
Documento: {datos.get('documento')}
Vigencia: {datos.get('vigencia')}
Importancia: {datos.get('importancia')}

El formato está disponible en la plataforma IT SOLUTION siguiendo la ruta:
Gestión Documental → Consultar Documentos → (Seleccionar empresa) → Filtrar por nombre o código.

Enlace de acceso:
http://190.131.206.250:8085/ItSolution/index.jsp

Cordialmente,
"""
        # 4. Enviar correo
        with st.spinner("Enviando correo..."):
            destinatarios_lista = [d.strip() for d in destinatarios.split(",") if d.strip()]
            if not destinatarios_lista:
                st.error("Debes ingresar al menos un destinatario.")
                st.stop()
            if enviar_correo(destinatarios_lista, asunto, cuerpo):
                st.success("✅ Correo enviado correctamente.")
            else:
                st.error("❌ Falló el envío. Revisa la configuración SMTP.")
