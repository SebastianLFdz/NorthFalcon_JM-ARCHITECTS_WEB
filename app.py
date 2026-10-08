# app.py — JM Architects
# Flask + PostgreSQL (Neon) + Resend, desplegable en Vercel mediante api/index.py.
import base64
import binascii
import os
import secrets
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse

import click
import psycopg
import resend
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import escape
from psycopg.rows import dict_row
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

# Cargar variables locales desde .env; en Vercel se usan las variables configuradas en el proyecto.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

EN_VERCEL = bool(os.environ.get("VERCEL"))

app = Flask(__name__)

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if EN_VERCEL:
        raise RuntimeError("Configura la variable de entorno SECRET_KEY en Vercel antes de publicar.")
    _secret_key = "jm-architects-clave-solo-para-desarrollo"
app.secret_key = _secret_key

app.config.update(
    # Vercel rechaza peticiones mayores a 4.5 MB; dejamos margen para el resto del formulario.
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=EN_VERCEL,
)


# ---- Contenido fijo del sitio ----
SERVICIOS = [
    {"titulo": "Urbanización", "descripcion": "Proyecto y gestión de obras de urbanización: vialidades, infraestructura y factibilidades ante las autoridades.", "icono": "fa-city"},
    {"titulo": "Lotificación de terrenos", "descripcion": "Diseñamos la distribución de lotes y acompañamos el trámite para que cada fracción pueda escriturarse por separado.", "icono": "fa-border-all"},
    {"titulo": "Subdivisiones y fusiones", "descripcion": "Partición o unión de predios conforme a la Ley de Asentamientos Humanos de Nuevo León.", "icono": "fa-object-ungroup"},
    {"titulo": "Avalúos", "descripcion": "Determinamos el valor de tu inmueble para compraventa, herencia, crédito o trámites fiscales.", "icono": "fa-scale-balanced"},
    {"titulo": "Trámites catastrales", "descripcion": "Altas, actualizaciones, manifestaciones y aclaraciones de información ante catastro.", "icono": "fa-file-signature"},
    {"titulo": "Levantamientos topográficos", "descripcion": "Medidas, colindancias y superficie real del predio con equipo de precisión.", "icono": "fa-ruler-combined"},
    {"titulo": "Rectificación de medidas y superficie", "descripcion": "Corregimos las diferencias entre lo que dicen tus documentos y lo que realmente mide tu terreno.", "icono": "fa-pen-ruler"},
]

TIPOS_SERVICIO = [s["titulo"] for s in SERVICIOS] + ["Otro"]

ARTICULOS = [
    {
        "slug": "dividir-terreno-nuevo-leon",
        "titulo": "¿Quieres dividir un terreno en Nuevo León? Lo que dice la Ley antes de firmar",
        "titulo_corto": "¿Quieres dividir un terreno en Nuevo León?",
        "extracto": "Lo que dice la Ley antes de firmar.",
        "subtitulo": "El problema: La historia del \"terreno desaparecido\" y la trampa del cálculo a ojo",
        "imagen": "IMG/front-view-blurry-lawyer-working.jpg",
        "slider": ["IMG/somos_negro.png", "IMG/somos_blanco.png"],
        "parrafos": [
            "Es una escena clásica en muchas familias: un propietario decide heredar o vender una parte de su propiedad creyendo que tiene, por ejemplo, 500m2 disponibles. Todo se planea sobre la marcha basándose en cercas antiguas, referencias de vecinos o documentos viejos. Sin embargo, al momento de realizar la medición técnica previa al diseño o al trámite formal, la realidad aparece: el terreno mide 430m2.",
            "Esta diferencia no solo genera desacuerdos familiares o contratiempos con los compradores, sino que altera por completo cualquier proyecto. Confiar en \"medidas estimadas\" o asumir que un terreno se puede dividir simplemente tirando una barda a la mitad es uno de los errores más costosos al gestionar un patrimonio. Sin precisión técnica, surgen problemas de retiros obligatorios, áreas de construcción reducidas y la imposibilidad de escriturar de forma independiente.",
        ],
        "secciones": [
            {
                "titulo": "El respaldo legal: Lo que establece la Ley de Asentamientos Humanos de Nuevo León",
                "parrafos": [
                    "Para realizar cualquier división de manera válida, la costumbre no basta; es indispensable cumplir con el marco legal vigente en el estado. La Ley de Asentamientos Humanos, Ordenamiento Territorial y Desarrollo Urbano para el Estado de Nuevo León regula estrictamente este tipo de procedimientos:",
                    "Definición legal de subdivisión (Artículo 230, Fracción II): La ley define la subdivisión como la partición de un predio ubicado dentro del límite de un centro de población en dos o más fracciones, siempre y cuando dicha partición no requiera la apertura de nuevas vías públicas. Si el proyecto exige la creación de calles o infraestructura pública, se trata entonces de un fraccionamiento, el cual contempla normativas y obligaciones distintas.",
                ],
            }
        ],
    },
]

PREGUNTAS = [
    ("¿Qué pasa si hago una división \"de palabra\" o por contrato privado sin permiso municipal?", "El Artículo 305 de la Ley de Asentamientos Humanos de Nuevo León establece que ninguna división surtirá efectos legales ni podrá inscribirse en el Instituto Registral y Catastral (IRCNL) sin la autorización del municipio. Sin esta licencia, las nuevas partes no podrán obtener escrituras individuales, servicios públicos a su nombre ni permisos de construcción futuros."),
    ("¿Por qué es obligatorio hacer un levantamiento topográfico antes de tramitar la subdivisión?", "Porque las medidas escritas en documentos antiguos o marcadas por cercas viejas suelen diferir de la realidad física. Un levantamiento topográfico con equipo de precisión determina los metros cuadrados reales, el frente, el fondo y los límites exactos del predio, evitando sorpresas al diseñar o al tramitar permisos."),
    ("¿Cuál es la diferencia entre subdividir y fraccionar un terreno?", "La diferencia principal radica en la infraestructura. Una subdivisión es la partición de un predio en dos o más fracciones dentro de un área urbana existente, siempre que no requiera la apertura de nuevas calles o vías públicas. Por otro lado, un fraccionamiento implica la creación de nuevos lotes que sí exigen el trazo de vialidades, obras de urbanización y donación de áreas verdes al municipio conforme a la ley."),
    ("¿Qué servicios ofrece JM Architects?", "Urbanización, lotificación de terrenos, subdivisiones y fusiones, avalúos, trámites catastrales, levantamientos topográficos y rectificación de medidas. Te acompañamos desde el diagnóstico hasta la entrega."),
    ("¿Cuánto tarda una asesoría?", "La primera conversación suele durar entre 30 y 45 minutos. Después revisamos el caso y compartimos una ruta de trabajo clara."),
    ("¿En qué zona trabajan?", "Atendemos principalmente Cadereyta Jiménez y el área metropolitana de Nuevo León. Escríbenos para revisar proyectos fuera de la zona."),
]

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


# ---- Conexión a base de datos (Neon / PostgreSQL) ----
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise RuntimeError("La variable de entorno DATABASE_URL no está configurada.")
        # prepare_threshold=None evita sentencias preparadas, incompatibles con algunos poolers.
        db = g._database = psycopg.connect(
            db_url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None
        )
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = g.pop("_database", None)
    if db is not None:
        db.close()


def consultar(sql, params=(), uno=False):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone() if uno else cursor.fetchall()


def ejecutar(sql, params=()):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        afectadas = cursor.rowcount
    db.commit()
    return afectadas


# ---- Seguridad: sesión y CSRF ----
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def volver(destino_por_defecto="home"):
    """Redirige a la página anterior solo si pertenece a este mismo sitio."""
    referer = request.referrer
    if referer and urlparse(referer).netloc == request.host:
        return redirect(referer)
    return redirect(url_for(destino_por_defecto))


@app.before_request
def proteger_formularios():
    if request.method == "POST":
        token = request.form.get("csrf_token", "")
        if not secrets.compare_digest(token, session.get("_csrf", "")):
            flash("El formulario expiró. Vuelve a intentarlo.", "error")
            return volver()


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return envoltura


@app.after_request
def cabeceras_seguridad(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


# ---- Utilidades de plantillas ----
@app.context_processor
def inyectar_globales():
    return {"year": datetime.now().year, "csrf_token": csrf_token}


@app.template_filter("fecha_larga")
def fecha_larga(valor):
    if not valor:
        return ""
    if isinstance(valor, datetime):
        valor = valor.date()
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


@app.template_filter("fecha_corta")
def fecha_corta(valor):
    return valor.strftime("%d/%m/%Y") if valor else ""


def version_imagen(proyecto):
    actualizado = proyecto.get("actualizado")
    return int(actualizado.timestamp()) if actualizado else 0


app.jinja_env.globals["version_imagen"] = version_imagen


# ---- Imágenes ----
FIRMAS_IMAGEN = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]


def detectar_tipo_imagen(datos):
    for firma, tipo in FIRMAS_IMAGEN:
        if datos.startswith(firma):
            return tipo
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def leer_imagen(archivo):
    """Convierte la imagen subida a data URL para guardarla en Neon (Vercel no conserva archivos)."""
    if not archivo or not archivo.filename:
        return None
    datos = archivo.read()
    if not datos:
        return None
    tipo = detectar_tipo_imagen(datos)
    if tipo is None:
        raise ValueError("La imagen debe ser JPG, PNG, WEBP o GIF.")
    return f"data:{tipo};base64,{base64.b64encode(datos).decode('ascii')}"


# ---- Rutas HTML ----
@app.route("/")
def home():
    return render_template("home.html", title="Somos tu solución")


@app.route("/nosotros")
def about():
    return render_template("about.html", title="Nosotros")


@app.route("/servicios")
def services():
    return render_template("services.html", title="Servicios", servicios=SERVICIOS)


@app.route("/blog")
def blog():
    return render_template("blog.html", title="Blog", articulos=ARTICULOS)


@app.route("/blog/<slug>")
def article(slug):
    seleccionado = next((a for a in ARTICULOS if a["slug"] == slug), None)
    if seleccionado is None:
        abort(404)
    return render_template("article.html", title=seleccionado["titulo"], articulo=seleccionado)


@app.route("/preguntas")
def questions():
    return render_template("questions.html", title="Preguntas frecuentes", faqs=PREGUNTAS)


# Compatibilidad con los enlaces del prototipo estático.
RUTAS_ANTERIORES = {
    "index.html": "home",
    "Nosotros.html": "about",
    "blog.html": "blog",
    "Preguntas.html": "questions",
    "Contacto.html": "contact",
}


@app.route("/<any(" + ", ".join(f'"{r}"' for r in RUTAS_ANTERIORES) + "):pagina>")
def ruta_anterior(pagina):
    return redirect(url_for(RUTAS_ANTERIORES[pagina]), code=301)


@app.route("/nota_1.html")
def nota_anterior():
    return redirect(url_for("article", slug=ARTICULOS[0]["slug"]), code=301)


# ---- Proyectos (publicaciones) ----
@app.route("/proyectos")
def proyectos():
    try:
        lista = consultar(
            "SELECT id, titulo, descripcion, fecha, actualizado FROM proyectos ORDER BY fecha DESC, id DESC"
        )
        error_db = False
    except Exception as e:
        app.logger.error("Error al consultar proyectos: %s", e)
        lista, error_db = [], True
    return render_template("proyectos.html", title="Proyectos", proyectos=lista, error_db=error_db)


@app.route("/proyectos/<int:proyecto_id>/imagen")
def imagen_proyecto(proyecto_id):
    try:
        fila = consultar("SELECT imagen_url FROM proyectos WHERE id = %s", (proyecto_id,), uno=True)
    except Exception as e:
        app.logger.error("Error al consultar la imagen del proyecto %s: %s", proyecto_id, e)
        abort(503)
    if not fila or not fila["imagen_url"]:
        abort(404)
    imagen = fila["imagen_url"]
    if imagen.startswith(("http://", "https://", "/")):
        return redirect(imagen)
    try:
        cabecera, contenido = imagen.split(",", 1)
        tipo = cabecera.split(":", 1)[1].split(";", 1)[0]
        datos = base64.b64decode(contenido)
    except (ValueError, IndexError, binascii.Error):
        abort(404)
    respuesta = Response(datos, mimetype=tipo)
    if request.args.get("v"):
        respuesta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        respuesta.headers["Cache-Control"] = "public, max-age=300"
    return respuesta


# ---- Reseñas ----
@app.route("/resenas", methods=["GET", "POST"])
@app.route("/reseñas", methods=["GET", "POST"])
@app.route("/referencias", methods=["GET", "POST"])
def reviews_page():
    if request.method == "POST":
        # Campo trampa: los bots lo llenan, las personas no lo ven.
        if request.form.get("sitio_web"):
            return redirect(url_for("reviews_page"))

        nombre = request.form.get("nombre", "").strip()
        comentario = request.form.get("comentario", "").strip()
        try:
            calificacion = round(float(request.form.get("calificacion", 5)) * 2) / 2
        except ValueError:
            calificacion = 0

        if not nombre or len(nombre) > 80:
            flash("Escribe un nombre válido de hasta 80 caracteres.", "error")
        elif not comentario or len(comentario) > 500:
            flash("La reseña debe tener entre 1 y 500 caracteres.", "error")
        elif not 1 <= calificacion <= 5:
            flash("Selecciona una calificación de 1 a 5 estrellas.", "error")
        else:
            try:
                ejecutar(
                    "INSERT INTO reviews (nombre, comentario, calificacion) VALUES (%s, %s, %s)",
                    (nombre, comentario, calificacion),
                )
                flash("Gracias por compartir tu experiencia.", "success")
            except Exception as e:
                app.logger.error("Error al guardar reseña: %s", e)
                flash("No pudimos guardar tu reseña en este momento. Intenta más tarde.", "error")
        return redirect(url_for("reviews_page"))

    filtro = request.args.get("stars", type=int)
    if filtro not in (1, 2, 3, 4, 5):
        filtro = None

    try:
        todas = consultar("SELECT calificacion FROM reviews")
        if filtro:
            # FLOOR coincide con las barras: 4.5 cuenta como 4 estrellas.
            resenas = consultar(
                "SELECT id, nombre, comentario, calificacion, fecha FROM reviews "
                "WHERE FLOOR(calificacion) = %s ORDER BY fecha DESC, id DESC",
                (filtro,),
            )
        else:
            resenas = consultar(
                "SELECT id, nombre, comentario, calificacion, fecha FROM reviews ORDER BY fecha DESC, id DESC"
            )
        error_db = False
    except Exception as e:
        app.logger.error("Error al consultar reseñas: %s", e)
        todas, resenas, error_db = [], [], True

    calificaciones = [float(r["calificacion"]) for r in todas]
    total = len(calificaciones)
    promedio = sum(calificaciones) / total if total else 0.0

    conteo = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for c in calificaciones:
        nivel = int(c)
        if nivel in conteo:
            conteo[nivel] += 1
    porcentajes = {k: (v / total * 100 if total else 0) for k, v in conteo.items()}

    return render_template(
        "reviews.html",
        title="Reseñas",
        resenas=resenas,
        total=total,
        promedio=round(promedio, 1),
        pct=porcentajes,
        filtro=filtro,
        error_db=error_db,
    )


# ---- Contacto (correo con Resend) ----
@app.route("/contacto", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip()
        telefono = request.form.get("telefono", "").strip()
        servicio = request.form.get("servicio", "").strip()
        mensaje = request.form.get("mensaje", "").strip()

        if not nombre or len(nombre) > 80:
            flash("Escribe tu nombre para poder contactarte.", "error")
            return volver("contact")
        if "@" not in correo or len(correo) > 120:
            flash("Escribe un correo electrónico válido.", "error")
            return volver("contact")
        if not mensaje or len(mensaje) > 2000:
            flash("Cuéntanos brevemente qué necesitas, en un máximo de 2000 caracteres.", "error")
            return volver("contact")

        resend_api_key = os.environ.get("RESEND_API_KEY")
        receptor = os.environ.get("RECEIVER_EMAIL", "jmarchitects.proyectos@gmail.com")
        remitente = os.environ.get("RESEND_FROM", "JM Architects <onboarding@resend.dev>")

        if not resend_api_key:
            app.logger.error("RESEND_API_KEY no está configurada.")
            flash("El formulario aún no está disponible. Escríbenos por WhatsApp o al correo de contacto.", "error")
            return volver("contact")

        html_content = """
        <html>
        <body style="font-family: Montserrat, Arial, sans-serif; background:#f3f3f3; padding:20px;">
          <div style="max-width:700px;margin:20px auto;background:#ffffff;border-radius:8px;padding:22px;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
            <h2 style="color:#000000;margin-bottom:6px;text-transform:uppercase;">Nueva solicitud de contacto</h2>
            <p style="color:#555;margin-top:0;">Has recibido un nuevo mensaje desde el formulario del sitio web.</p>
            <table style="width:100%;margin-top:12px;border-collapse:collapse;">
              <tr><td style="padding:8px;border-top:1px solid #ddd;"><strong>Nombre</strong></td><td style="padding:8px;border-top:1px solid #ddd;">{NOMBRE}</td></tr>
              <tr><td style="padding:8px;border-top:1px solid #ddd;"><strong>Correo</strong></td><td style="padding:8px;border-top:1px solid #ddd;">{CORREO}</td></tr>
              <tr><td style="padding:8px;border-top:1px solid #ddd;"><strong>Teléfono</strong></td><td style="padding:8px;border-top:1px solid #ddd;">{TELEFONO}</td></tr>
              <tr><td style="padding:8px;border-top:1px solid #ddd;"><strong>Servicio</strong></td><td style="padding:8px;border-top:1px solid #ddd;">{SERVICIO}</td></tr>
            </table>
            <h4 style="margin-top:18px;margin-bottom:8px;color:#222;">Mensaje</h4>
            <div style="background:#f9f9f9;border:1px solid #ddd;padding:12px;border-radius:6px;color:#333;">{MENSAJE}</div>
            <p style="font-size:12px;color:#777;margin-top:18px;">Enviado automáticamente desde el formulario de contacto — JM Architects.</p>
          </div>
        </body>
        </html>
        """.format(
            NOMBRE=escape(nombre),
            CORREO=escape(correo),
            TELEFONO=escape(telefono or "—"),
            SERVICIO=escape(servicio or "—"),
            MENSAJE=escape(mensaje).replace("\n", "<br>"),
        )

        resend.api_key = resend_api_key
        email_params = {
            "from": remitente,
            "to": [receptor],
            "subject": f"Solicitud de contacto - {nombre}",
            "html": html_content,
            "reply_to": correo,
        }

        archivo = request.files.get("archivo")
        if archivo and archivo.filename:
            datos = archivo.read()
            if datos:
                email_params["attachments"] = [{"filename": archivo.filename, "content": list(datos)}]

        try:
            resend.Emails.send(email_params)
        except Exception as e:
            app.logger.error("Error enviando correo con Resend: %s %s", type(e).__name__, e)
            flash("Ocurrió un problema al enviar tu mensaje. Intenta de nuevo más tarde.", "error")
            return volver("contact")
        return redirect(url_for("contact", exito=1))

    return render_template("contact.html", title="Contacto", servicios=TIPOS_SERVICIO)


# ---- Inicio de sesión ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario" in session:
        return redirect(url_for("admin"))

    error = None
    if request.method == "POST":
        usuario_input = request.form.get("usuario", "").strip()
        password_input = request.form.get("password", "")
        try:
            user = consultar(
                "SELECT id, usuario, password FROM usuarios WHERE usuario = %s",
                (usuario_input,),
                uno=True,
            )
            valido = False
            if user:
                guardada = user["password"]
                if guardada.startswith(("scrypt:", "pbkdf2:")):
                    valido = check_password_hash(guardada, password_input)
                elif secrets.compare_digest(guardada, password_input):
                    # Contraseña capturada en texto plano desde Neon: se reemplaza por su hash.
                    valido = True
                    ejecutar(
                        "UPDATE usuarios SET password = %s WHERE id = %s",
                        (generate_password_hash(password_input), user["id"]),
                    )
            if valido:
                session.clear()
                session["usuario"] = user["usuario"]
                return redirect(url_for("admin"))
            error = "Credenciales incorrectas"
        except Exception as e:
            app.logger.error("Error de base de datos en login: %s", e)
            error = "No fue posible conectar con la base de datos."

    return render_template("login.html", title="Acceso", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---- Panel administrativo ----
@app.route("/admin")
@login_requerido
def admin():
    try:
        lista_proyectos = consultar(
            "SELECT id, titulo, descripcion, fecha, actualizado FROM proyectos ORDER BY fecha DESC, id DESC"
        )
        lista_resenas = consultar(
            "SELECT id, nombre, comentario, calificacion, fecha FROM reviews ORDER BY fecha DESC, id DESC"
        )
    except Exception as e:
        app.logger.error("Error al consultar la base de datos: %s", e)
        flash("No fue posible cargar la información de la base de datos.", "error")
        lista_proyectos, lista_resenas = [], []
    return render_template(
        "admin.html", title="Panel administrativo", proyectos=lista_proyectos, referencias=lista_resenas
    )


@app.route("/admin/proyectos/crear", methods=["POST"])
@login_requerido
def admin_crear_proyecto():
    titulo = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    fecha = request.form.get("fecha", "").strip() or date.today().isoformat()

    if not titulo or len(titulo) > 150:
        flash("El título es obligatorio (máximo 150 caracteres).", "error")
        return redirect(url_for("admin", vista="vista-crear-proyecto"))
    try:
        imagen_url = leer_imagen(request.files.get("imagen"))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin", vista="vista-crear-proyecto"))
    if not imagen_url:
        flash("Selecciona una imagen para el proyecto.", "error")
        return redirect(url_for("admin", vista="vista-crear-proyecto"))

    try:
        ejecutar(
            "INSERT INTO proyectos (titulo, descripcion, fecha, imagen_url) VALUES (%s, %s, %s, %s)",
            (titulo, descripcion, fecha, imagen_url),
        )
        flash("Proyecto publicado correctamente.", "success")
    except Exception as e:
        app.logger.error("Error al crear el proyecto: %s", e)
        flash("No se pudo guardar el proyecto. Revisa los datos e intenta de nuevo.", "error")
        return redirect(url_for("admin", vista="vista-crear-proyecto"))
    return redirect(url_for("admin", vista="vista-editar-lista"))


@app.route("/admin/proyectos/editar/<int:id>", methods=["POST"])
@login_requerido
def editar_proyecto(id):
    titulo = request.form.get("titulo", "").strip()
    fecha = request.form.get("fecha", "").strip()
    descripcion = request.form.get("descripcion", "").strip()

    if not titulo or len(titulo) > 150 or not fecha:
        flash("El título y la fecha son obligatorios.", "error")
        return redirect(url_for("admin", vista="vista-editar-lista"))
    try:
        imagen_url = leer_imagen(request.files.get("imagen"))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin", vista="vista-editar-lista"))

    try:
        if imagen_url:
            afectadas = ejecutar(
                "UPDATE proyectos SET titulo = %s, fecha = %s, descripcion = %s, imagen_url = %s, "
                "actualizado = NOW() WHERE id = %s",
                (titulo, fecha, descripcion, imagen_url, id),
            )
        else:
            # Sin imagen nueva se conserva la actual y solo se actualizan los textos.
            afectadas = ejecutar(
                "UPDATE proyectos SET titulo = %s, fecha = %s, descripcion = %s WHERE id = %s",
                (titulo, fecha, descripcion, id),
            )
        if afectadas:
            flash("Proyecto actualizado correctamente.", "success")
        else:
            flash("El proyecto ya no existe.", "error")
    except Exception as e:
        app.logger.error("Error al editar el proyecto: %s", e)
        flash("No se pudo actualizar el proyecto.", "error")
    return redirect(url_for("admin", vista="vista-editar-lista"))


@app.route("/admin/proyectos/eliminar/<int:id>", methods=["POST"])
@login_requerido
def eliminar_proyecto(id):
    try:
        if ejecutar("DELETE FROM proyectos WHERE id = %s", (id,)):
            flash("Proyecto eliminado.", "success")
        else:
            flash("El proyecto ya no existe.", "error")
    except Exception as e:
        app.logger.error("Error al eliminar el proyecto: %s", e)
        flash("No se pudo eliminar el proyecto.", "error")
    return redirect(url_for("admin", vista="vista-eliminar-proyecto"))


@app.route("/admin/referencias/eliminar/<int:id>", methods=["POST"])
@login_requerido
def eliminar_referencia(id):
    try:
        if ejecutar("DELETE FROM reviews WHERE id = %s", (id,)):
            flash("Reseña eliminada.", "success")
        else:
            flash("La reseña ya no existe.", "error")
    except Exception as e:
        app.logger.error("Error al eliminar la reseña: %s", e)
        flash("No se pudo eliminar la reseña.", "error")
    return redirect(url_for("admin", vista="vista-lista-referencias"))


# ---- Errores ----
@app.errorhandler(404)
def page_not_found(_error):
    return render_template("404.html", title="Página no encontrada"), 404


@app.errorhandler(RequestEntityTooLarge)
def archivo_muy_grande(_error):
    flash("El archivo es demasiado grande. El máximo permitido es 4 MB.", "error")
    return volver()


# ---- Comandos de mantenimiento (flask --app app ...) ----
@app.cli.command("init-db")
def init_db_command():
    """Crea las tablas definidas en schema.sql."""
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        sql = f.read()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(sql)
    click.echo("Tablas creadas o ya existentes.")


@app.cli.command("crear-admin")
@click.argument("usuario")
@click.password_option(prompt="Contraseña")
def crear_admin_command(usuario, password):
    """Crea un usuario administrador o cambia su contraseña."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "INSERT INTO usuarios (usuario, password) VALUES (%s, %s) "
            "ON CONFLICT (usuario) DO UPDATE SET password = EXCLUDED.password",
            (usuario, generate_password_hash(password)),
        )
    click.echo(f"Usuario '{usuario}' listo.")


if __name__ == "__main__":
    app.run(debug=True)
