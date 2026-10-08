# app.py — JM Architects
# Flask + PostgreSQL (Neon) + Resend, desplegable en Vercel mediante api/index.py.
import base64
import binascii
import hashlib
import json
import math
import os
import re
import secrets
import unicodedata
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup, escape
from psycopg.rows import dict_row
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# Cargar variables locales desde .env; en Vercel se usan las variables configuradas en el proyecto.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

EN_VERCEL = bool(os.environ.get("VERCEL"))
ZONA = ZoneInfo("America/Monterrey")

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


# ---- Datos del negocio ----
SITIO = {
    "nombre": "JM Architects",
    "telefono": "+52 828 131 1613",
    "whatsapp": "528281311613",
    "correo": "jmarchitects.proyectos@gmail.com",
    "direccion": "Ignacio Comonfort 232, Lázaro Cárdenas 1er Sector",
    "ciudad": "Cadereyta Jiménez",
    "estado": "Nuevo León",
    "cp": "67483",
    "instagram": "https://www.instagram.com/architects.jm/",
    # Pon aquí la URL de la página de Facebook del cliente; mientras esté vacía no se muestra el ícono.
    "facebook": "",
    # Nombre legal del responsable (persona física o razón social) para el aviso de privacidad.
    "razon_social": "",
    "aviso_actualizado": "8 de octubre de 2026",
}

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

PROYECTOS_POR_PAGINA = 6
ARTICULOS_POR_PAGINA = 9
IMAGEN_ARTICULO_DEFAULT = "IMG/front-view-blurry-lawyer-working.jpg"

# Límites anti-abuso (por IP)
LOGIN_MAX_FALLOS, LOGIN_VENTANA_MIN = 5, 15
MENSAJES_MAX, MENSAJES_VENTANA_MIN = 5, 60
RESENAS_MAX, RESENAS_VENTANA_MIN = 3, 60

EXTENSIONES_ADJUNTO = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".dwg", ".dxf", ".doc", ".docx"}


def hoy():
    return datetime.now(ZONA).date()


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


def insertar(sql, params=()):
    """Ejecuta un INSERT ... RETURNING id y devuelve el id."""
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        nuevo = cursor.fetchone()["id"]
    db.commit()
    return nuevo


# ---- Seguridad: sesión, CSRF, límites ----
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


def ip_cliente():
    # Vercel reemplaza X-Forwarded-For con la IP real del visitante.
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


def ip_hash():
    """Huella de la IP (no se guarda la IP en claro)."""
    return hashlib.sha256((app.secret_key + "|" + ip_cliente()).encode()).hexdigest()[:32]


def turnstile_activo():
    return bool(os.environ.get("TURNSTILE_SITE_KEY") and os.environ.get("TURNSTILE_SECRET_KEY"))


def verificar_turnstile():
    """Valida el captcha de Cloudflare Turnstile si está configurado."""
    if not turnstile_activo():
        return True
    token = request.form.get("cf-turnstile-response", "")
    if not token:
        return False
    datos = urlencode({
        "secret": os.environ["TURNSTILE_SECRET_KEY"],
        "response": token,
        "remoteip": ip_cliente(),
    }).encode()
    try:
        peticion = Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=datos)
        with urlopen(peticion, timeout=8) as respuesta:
            return bool(json.load(respuesta).get("success"))
    except Exception as e:
        app.logger.error("Error verificando Turnstile: %s", e)
        return False


@app.before_request
def proteger_formularios():
    if request.method == "POST":
        token = request.form.get("csrf_token", "")
        esperado = session.get("_csrf", "")
        # Ambos deben existir: dos valores vacíos no cuentan como coincidencia.
        if not token or not esperado or not secrets.compare_digest(token, esperado):
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
def cabeceras(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.path.startswith("/static/") and response.status_code == 200:
        if request.args.get("v"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=86400, s-maxage=604800"
    return response


# ---- Utilidades de plantillas ----
def static_v(filename):
    """URL de un archivo estático con versión, para poder cachearlo mucho tiempo."""
    try:
        version = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
    except OSError:
        version = 0
    return url_for("static", filename=filename, v=version)


def url_sitio():
    return (os.environ.get("SITE_URL") or request.url_root).rstrip("/")


@app.context_processor
def inyectar_globales():
    return {
        "year": hoy().year,
        "csrf_token": csrf_token,
        "static_v": static_v,
        "sitio": SITIO,
        "url_sitio": url_sitio,
        "turnstile_site_key": os.environ.get("TURNSTILE_SITE_KEY") if turnstile_activo() else None,
    }


def en_zona(valor):
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            valor = valor.astimezone(ZONA)
        return valor.date()
    return valor


@app.template_filter("fecha_larga")
def fecha_larga(valor):
    if not valor:
        return ""
    valor = en_zona(valor)
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


@app.template_filter("fecha_corta")
def fecha_corta(valor):
    return en_zona(valor).strftime("%d/%m/%Y") if valor else ""


@app.template_filter("contenido_articulo")
def contenido_articulo(texto):
    """Convierte el texto del artículo en párrafos; las líneas que empiezan con '## ' son subtítulos."""
    partes = []
    for bloque in re.split(r"\n\s*\n", (texto or "").strip()):
        bloque = bloque.strip()
        if not bloque:
            continue
        if bloque.startswith("## "):
            partes.append(Markup("<h3>{}</h3>").format(bloque[3:].strip()))
        else:
            lineas = Markup("<br>").join(escape(l.strip()) for l in bloque.splitlines())
            partes.append(Markup("<p>{}</p>").format(lineas))
    return Markup("").join(partes)


def version_imagen(registro):
    actualizado = registro.get("actualizado")
    return int(actualizado.timestamp()) if actualizado else 0


app.jinja_env.globals["version_imagen"] = version_imagen


def paginar(total, por_pagina):
    paginas = max(1, math.ceil(total / por_pagina))
    pagina = min(max(1, request.args.get("pagina", 1, type=int)), paginas)
    return pagina, paginas, (pagina - 1) * por_pagina


def slugify(texto):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")
    return texto[:80].strip("-") or "articulo"


def slug_unico(titulo):
    base = slugify(titulo)
    slug, n = base, 2
    while consultar("SELECT 1 FROM articulos WHERE slug = %s", (slug,), uno=True):
        slug, n = f"{base}-{n}", n + 1
    return slug


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
        if archivo.filename.lower().endswith((".heic", ".heif")):
            raise ValueError("Las fotos HEIC de iPhone no son compatibles. Conviértelas a JPG o súbelas desde el iPhone (se convierten solas).")
        raise ValueError("La imagen debe ser JPG, PNG, WEBP o GIF.")
    return f"data:{tipo};base64,{base64.b64encode(datos).decode('ascii')}"


def servir_imagen(imagen):
    if not imagen:
        abort(404)
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
        # s-maxage permite que el CDN de Vercel la guarde y no se consulte Neon en cada visita.
        respuesta.headers["Cache-Control"] = "public, max-age=31536000, s-maxage=31536000, immutable"
    else:
        respuesta.headers["Cache-Control"] = "public, max-age=300, s-maxage=300"
    return respuesta


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


@app.route("/preguntas")
def questions():
    return render_template("questions.html", title="Preguntas frecuentes", faqs=PREGUNTAS)


@app.route("/aviso-de-privacidad")
def privacidad():
    return render_template("privacidad.html", title="Aviso de privacidad")


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
    return redirect(url_for("article", slug="dividir-terreno-nuevo-leon"), code=301)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/x-icon", max_age=604800)


@app.route("/robots.txt")
def robots():
    contenido = f"User-agent: *\nDisallow: /admin\nDisallow: /login\nSitemap: {url_sitio()}/sitemap.xml\n"
    return Response(contenido, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    urls = [(url_for(e), None) for e in ("home", "about", "services", "proyectos", "blog", "reviews_page", "questions", "contact")]
    try:
        for a in consultar("SELECT slug, actualizado FROM articulos WHERE publicado ORDER BY fecha DESC"):
            urls.append((url_for("article", slug=a["slug"]), en_zona(a["actualizado"])))
    except Exception as e:
        app.logger.error("Error al generar sitemap: %s", e)
    base = url_sitio()
    entradas = "".join(
        f"<url><loc>{escape(base + ruta)}</loc>" + (f"<lastmod>{fecha.isoformat()}</lastmod>" if fecha else "") + "</url>"
        for ruta, fecha in urls
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entradas}</urlset>'
    return Response(xml, mimetype="application/xml")


# ---- Proyectos (publicaciones) ----
@app.route("/proyectos")
def proyectos():
    try:
        total = consultar("SELECT COUNT(*) AS n FROM proyectos", uno=True)["n"]
        pagina, paginas, desde = paginar(total, PROYECTOS_POR_PAGINA)
        lista = consultar(
            "SELECT id, titulo, descripcion, fecha, actualizado FROM proyectos "
            "ORDER BY fecha DESC, id DESC LIMIT %s OFFSET %s",
            (PROYECTOS_POR_PAGINA, desde),
        )
        error_db = False
    except Exception as e:
        app.logger.error("Error al consultar proyectos: %s", e)
        lista, error_db, pagina, paginas = [], True, 1, 1
    return render_template("proyectos.html", title="Proyectos", proyectos=lista, error_db=error_db,
                           pagina=pagina, paginas=paginas)


@app.route("/proyectos/<int:proyecto_id>/imagen")
def imagen_proyecto(proyecto_id):
    try:
        fila = consultar("SELECT imagen_url FROM proyectos WHERE id = %s", (proyecto_id,), uno=True)
    except Exception as e:
        app.logger.error("Error al consultar la imagen del proyecto %s: %s", proyecto_id, e)
        abort(503)
    return servir_imagen(fila["imagen_url"] if fila else None)


# ---- Blog ----
@app.route("/blog")
def blog():
    try:
        total = consultar("SELECT COUNT(*) AS n FROM articulos WHERE publicado", uno=True)["n"]
        pagina, paginas, desde = paginar(total, ARTICULOS_POR_PAGINA)
        lista = consultar(
            "SELECT id, slug, titulo, extracto, fecha, actualizado FROM articulos WHERE publicado "
            "ORDER BY fecha DESC, id DESC LIMIT %s OFFSET %s",
            (ARTICULOS_POR_PAGINA, desde),
        )
        error_db = False
    except Exception as e:
        app.logger.error("Error al consultar artículos: %s", e)
        lista, error_db, pagina, paginas = [], True, 1, 1
    return render_template("blog.html", title="Blog", articulos=lista, error_db=error_db,
                           pagina=pagina, paginas=paginas)


@app.route("/blog/<slug>")
def article(slug):
    try:
        articulo = consultar(
            "SELECT id, slug, titulo, extracto, contenido, fecha, actualizado FROM articulos "
            "WHERE slug = %s AND publicado",
            (slug,), uno=True,
        )
    except Exception as e:
        app.logger.error("Error al consultar el artículo %s: %s", slug, e)
        abort(503)
    if articulo is None:
        abort(404)
    return render_template("article.html", title=articulo["titulo"], articulo=articulo)


@app.route("/articulos/<int:articulo_id>/imagen")
def imagen_articulo(articulo_id):
    try:
        fila = consultar("SELECT imagen_url FROM articulos WHERE id = %s", (articulo_id,), uno=True)
    except Exception as e:
        app.logger.error("Error al consultar la imagen del artículo %s: %s", articulo_id, e)
        abort(503)
    if fila is None:
        abort(404)
    if not fila["imagen_url"]:
        return redirect(url_for("static", filename=IMAGEN_ARTICULO_DEFAULT))
    return servir_imagen(fila["imagen_url"])


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
        elif not verificar_turnstile():
            flash("No pudimos verificar que no eres un robot. Intenta de nuevo.", "error")
        else:
            try:
                huella = ip_hash()
                recientes = consultar(
                    "SELECT COUNT(*) AS n FROM reviews WHERE ip_hash = %s "
                    "AND fecha > NOW() - make_interval(mins => %s)",
                    (huella, RESENAS_VENTANA_MIN), uno=True,
                )["n"]
                if recientes >= RESENAS_MAX:
                    flash("Ya recibimos tus reseñas recientes. Intenta de nuevo más tarde.", "error")
                else:
                    ejecutar(
                        "INSERT INTO reviews (nombre, comentario, calificacion, ip_hash) VALUES (%s, %s, %s, %s)",
                        (nombre, comentario, calificacion, huella),
                    )
                    flash("¡Gracias por compartir tu experiencia! Tu reseña se publicará en cuanto la revisemos.", "success")
            except Exception as e:
                app.logger.error("Error al guardar reseña: %s", e)
                flash("No pudimos guardar tu reseña en este momento. Intenta más tarde.", "error")
        return redirect(url_for("reviews_page"))

    filtro = request.args.get("stars", type=int)
    if filtro not in (1, 2, 3, 4, 5):
        filtro = None

    try:
        todas = consultar("SELECT calificacion FROM reviews WHERE aprobada")
        if filtro:
            # FLOOR coincide con las barras: 4.5 cuenta como 4 estrellas.
            resenas = consultar(
                "SELECT id, nombre, comentario, calificacion, fecha FROM reviews "
                "WHERE aprobada AND FLOOR(calificacion) = %s ORDER BY fecha DESC, id DESC",
                (filtro,),
            )
        else:
            resenas = consultar(
                "SELECT id, nombre, comentario, calificacion, fecha FROM reviews "
                "WHERE aprobada ORDER BY fecha DESC, id DESC"
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


# ---- Contacto (se guarda en la base de datos y se envía por correo con Resend) ----
def enviar_correo_contacto(datos, adjunto):
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if not resend_api_key:
        app.logger.warning("RESEND_API_KEY no está configurada; el mensaje solo se guardó en la base de datos.")
        return False

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
        <p style="font-size:12px;color:#777;margin-top:18px;">Enviado automáticamente desde el formulario de contacto — JM Architects. También puedes consultarlo en el panel administrativo.</p>
      </div>
    </body>
    </html>
    """.format(
        NOMBRE=escape(datos["nombre"]),
        CORREO=escape(datos["correo"]),
        TELEFONO=escape(datos["telefono"] or "—"),
        SERVICIO=escape(datos["servicio"] or "—"),
        MENSAJE=escape(datos["mensaje"]).replace("\n", "<br>"),
    )

    resend.api_key = resend_api_key
    email_params = {
        "from": os.environ.get("RESEND_FROM", "JM Architects <onboarding@resend.dev>"),
        "to": [os.environ.get("RECEIVER_EMAIL", SITIO["correo"])],
        "subject": f"Solicitud de contacto - {datos['nombre']}",
        "html": html_content,
        "reply_to": datos["correo"],
    }
    if adjunto:
        email_params["attachments"] = [{"filename": adjunto[0], "content": list(adjunto[1])}]

    try:
        resend.Emails.send(email_params)
        return True
    except Exception as e:
        app.logger.error("Error enviando correo con Resend: %s %s", type(e).__name__, e)
        return False


@app.route("/contacto", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        datos = {
            "nombre": request.form.get("nombre", "").strip(),
            "correo": request.form.get("correo", "").strip(),
            "telefono": request.form.get("telefono", "").strip()[:30],
            "servicio": request.form.get("servicio", "").strip()[:80],
            "mensaje": request.form.get("mensaje", "").strip(),
        }

        error = None
        if not datos["nombre"] or len(datos["nombre"]) > 80:
            error = "Escribe tu nombre para poder contactarte."
        elif "@" not in datos["correo"] or len(datos["correo"]) > 120:
            error = "Escribe un correo electrónico válido."
        elif not datos["mensaje"] or len(datos["mensaje"]) > 2000:
            error = "Cuéntanos brevemente qué necesitas, en un máximo de 2000 caracteres."
        elif not request.form.get("acepto_privacidad"):
            error = "Para enviar tu mensaje debes aceptar el aviso de privacidad."
        elif not verificar_turnstile():
            error = "No pudimos verificar que no eres un robot. Intenta de nuevo."

        adjunto = None
        archivo = request.files.get("archivo")
        if not error and archivo and archivo.filename:
            nombre_archivo = secure_filename(archivo.filename) or "adjunto"
            extension = os.path.splitext(archivo.filename)[1].lower()
            if extension not in EXTENSIONES_ADJUNTO:
                error = "El archivo adjunto debe ser PDF, imagen (JPG, PNG, WEBP), DWG, DXF o Word."
            else:
                contenido = archivo.read()
                if contenido:
                    if not nombre_archivo.lower().endswith(extension):
                        nombre_archivo += extension
                    adjunto = (nombre_archivo, contenido)

        if error:
            flash(error, "error")
            return volver("contact")

        guardado = False
        huella = ip_hash()
        try:
            recientes = consultar(
                "SELECT COUNT(*) AS n FROM mensajes WHERE ip_hash = %s "
                "AND fecha > NOW() - make_interval(mins => %s)",
                (huella, MENSAJES_VENTANA_MIN), uno=True,
            )["n"]
            if recientes >= MENSAJES_MAX:
                flash("Recibimos varios mensajes tuyos recientemente. Intenta de nuevo en una hora o escríbenos por WhatsApp.", "error")
                return volver("contact")
            mensaje_id = insertar(
                "INSERT INTO mensajes (nombre, correo, telefono, servicio, mensaje, archivo_nombre, ip_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (datos["nombre"], datos["correo"], datos["telefono"], datos["servicio"], datos["mensaje"],
                 adjunto[0] if adjunto else None, huella),
            )
            guardado = True
        except Exception as e:
            app.logger.error("Error al guardar el mensaje de contacto: %s", e)

        enviado = enviar_correo_contacto(datos, adjunto)
        if guardado and enviado:
            try:
                ejecutar("UPDATE mensajes SET enviado = TRUE WHERE id = %s", (mensaje_id,))
            except Exception as e:
                app.logger.error("Error al marcar el mensaje como enviado: %s", e)

        if not guardado and not enviado:
            flash("Ocurrió un problema al enviar tu mensaje. Intenta de nuevo más tarde o escríbenos por WhatsApp.", "error")
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
            huella = ip_hash()
            ejecutar("DELETE FROM intentos_login WHERE fecha < NOW() - INTERVAL '1 day'")
            fallos = consultar(
                "SELECT COUNT(*) AS n FROM intentos_login WHERE ip_hash = %s "
                "AND fecha > NOW() - make_interval(mins => %s)",
                (huella, LOGIN_VENTANA_MIN), uno=True,
            )["n"]
            if fallos >= LOGIN_MAX_FALLOS:
                error = f"Demasiados intentos fallidos. Espera {LOGIN_VENTANA_MIN} minutos e intenta de nuevo."
            else:
                user = consultar(
                    "SELECT id, usuario, password FROM usuarios WHERE usuario = %s",
                    (usuario_input,), uno=True,
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
                    ejecutar("DELETE FROM intentos_login WHERE ip_hash = %s", (huella,))
                    session.clear()
                    session["usuario"] = user["usuario"]
                    return redirect(url_for("admin"))
                ejecutar(
                    "INSERT INTO intentos_login (ip_hash, usuario) VALUES (%s, %s)",
                    (huella, usuario_input[:80]),
                )
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
    datos = {"proyectos": [], "referencias": [], "articulos": [], "mensajes": []}
    try:
        datos["proyectos"] = consultar(
            "SELECT id, titulo, descripcion, fecha, actualizado FROM proyectos ORDER BY fecha DESC, id DESC"
        )
        datos["referencias"] = consultar(
            "SELECT id, nombre, comentario, calificacion, fecha, aprobada FROM reviews "
            "ORDER BY aprobada ASC, fecha DESC, id DESC"
        )
        datos["articulos"] = consultar(
            "SELECT id, slug, titulo, extracto, contenido, fecha, publicado, actualizado, "
            "(imagen_url IS NOT NULL) AS tiene_imagen FROM articulos ORDER BY fecha DESC, id DESC"
        )
        datos["mensajes"] = consultar(
            "SELECT id, nombre, correo, telefono, servicio, mensaje, archivo_nombre, enviado, leido, fecha "
            "FROM mensajes ORDER BY leido ASC, fecha DESC, id DESC"
        )
    except Exception as e:
        app.logger.error("Error al consultar la base de datos: %s", e)
        flash("No fue posible cargar la información de la base de datos.", "error")
    return render_template("admin.html", title="Panel administrativo", hoy=hoy(), **datos)


# -- Proyectos --
@app.route("/admin/proyectos/crear", methods=["POST"])
@login_requerido
def admin_crear_proyecto():
    titulo = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    fecha = request.form.get("fecha", "").strip() or hoy().isoformat()

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


# -- Blog --
def datos_articulo():
    return {
        "titulo": request.form.get("titulo", "").strip(),
        "extracto": request.form.get("extracto", "").strip(),
        "contenido": request.form.get("contenido", "").strip(),
        "fecha": request.form.get("fecha", "").strip() or hoy().isoformat(),
        "publicado": bool(request.form.get("publicado")),
    }


def validar_articulo(a):
    if not a["titulo"] or len(a["titulo"]) > 200:
        return "El título es obligatorio (máximo 200 caracteres)."
    if len(a["extracto"]) > 300:
        return "El resumen debe tener como máximo 300 caracteres."
    if not a["contenido"]:
        return "El contenido del artículo es obligatorio."
    return None


@app.route("/admin/articulos/crear", methods=["POST"])
@login_requerido
def admin_crear_articulo():
    a = datos_articulo()
    error = validar_articulo(a)
    try:
        imagen_url = None if error else leer_imagen(request.files.get("imagen"))
    except ValueError as e:
        error = str(e)
    if error:
        flash(error, "error")
        return redirect(url_for("admin", vista="vista-crear-articulo"))
    try:
        ejecutar(
            "INSERT INTO articulos (slug, titulo, extracto, contenido, fecha, publicado, imagen_url) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (slug_unico(a["titulo"]), a["titulo"], a["extracto"], a["contenido"], a["fecha"], a["publicado"], imagen_url),
        )
        flash("Artículo guardado correctamente." if a["publicado"] else "Artículo guardado como borrador.", "success")
    except Exception as e:
        app.logger.error("Error al crear el artículo: %s", e)
        flash("No se pudo guardar el artículo.", "error")
        return redirect(url_for("admin", vista="vista-crear-articulo"))
    return redirect(url_for("admin", vista="vista-lista-articulos"))


@app.route("/admin/articulos/editar/<int:id>", methods=["POST"])
@login_requerido
def editar_articulo(id):
    a = datos_articulo()
    error = validar_articulo(a)
    try:
        imagen_url = None if error else leer_imagen(request.files.get("imagen"))
    except ValueError as e:
        error = str(e)
    if error:
        flash(error, "error")
        return redirect(url_for("admin", vista="vista-lista-articulos"))
    try:
        campos = "titulo = %s, extracto = %s, contenido = %s, fecha = %s, publicado = %s, actualizado = NOW()"
        params = [a["titulo"], a["extracto"], a["contenido"], a["fecha"], a["publicado"]]
        if imagen_url:
            campos += ", imagen_url = %s"
            params.append(imagen_url)
        # El slug no cambia al editar para no romper enlaces ya compartidos.
        afectadas = ejecutar(f"UPDATE articulos SET {campos} WHERE id = %s", (*params, id))
        flash("Artículo actualizado correctamente." if afectadas else "El artículo ya no existe.",
              "success" if afectadas else "error")
    except Exception as e:
        app.logger.error("Error al editar el artículo: %s", e)
        flash("No se pudo actualizar el artículo.", "error")
    return redirect(url_for("admin", vista="vista-lista-articulos"))


@app.route("/admin/articulos/eliminar/<int:id>", methods=["POST"])
@login_requerido
def eliminar_articulo(id):
    try:
        if ejecutar("DELETE FROM articulos WHERE id = %s", (id,)):
            flash("Artículo eliminado.", "success")
        else:
            flash("El artículo ya no existe.", "error")
    except Exception as e:
        app.logger.error("Error al eliminar el artículo: %s", e)
        flash("No se pudo eliminar el artículo.", "error")
    return redirect(url_for("admin", vista="vista-lista-articulos"))


# -- Reseñas --
@app.route("/admin/referencias/aprobar/<int:id>", methods=["POST"])
@login_requerido
def aprobar_referencia(id):
    try:
        fila = consultar("UPDATE reviews SET aprobada = NOT aprobada WHERE id = %s RETURNING aprobada", (id,), uno=True)
        get_db().commit()
        if fila is None:
            flash("La reseña ya no existe.", "error")
        else:
            flash("Reseña publicada en el sitio." if fila["aprobada"] else "Reseña ocultada del sitio.", "success")
    except Exception as e:
        app.logger.error("Error al aprobar la reseña: %s", e)
        flash("No se pudo actualizar la reseña.", "error")
    return redirect(url_for("admin", vista="vista-lista-referencias"))


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


# -- Mensajes de contacto --
@app.route("/admin/mensajes/leido/<int:id>", methods=["POST"])
@login_requerido
def marcar_mensaje(id):
    try:
        if not ejecutar("UPDATE mensajes SET leido = NOT leido WHERE id = %s", (id,)):
            flash("El mensaje ya no existe.", "error")
    except Exception as e:
        app.logger.error("Error al actualizar el mensaje: %s", e)
        flash("No se pudo actualizar el mensaje.", "error")
    return redirect(url_for("admin", vista="vista-mensajes"))


@app.route("/admin/mensajes/eliminar/<int:id>", methods=["POST"])
@login_requerido
def eliminar_mensaje(id):
    try:
        if ejecutar("DELETE FROM mensajes WHERE id = %s", (id,)):
            flash("Mensaje eliminado.", "success")
        else:
            flash("El mensaje ya no existe.", "error")
    except Exception as e:
        app.logger.error("Error al eliminar el mensaje: %s", e)
        flash("No se pudo eliminar el mensaje.", "error")
    return redirect(url_for("admin", vista="vista-mensajes"))


# -- Mi cuenta --
@app.route("/admin/cuenta/password", methods=["POST"])
@login_requerido
def cambiar_password():
    actual = request.form.get("actual", "")
    nueva = request.form.get("nueva", "")
    confirmar = request.form.get("confirmar", "")
    destino = redirect(url_for("admin", vista="vista-cuenta"))

    if len(nueva) < 8:
        flash("La nueva contraseña debe tener al menos 8 caracteres.", "error")
        return destino
    if nueva != confirmar:
        flash("La confirmación no coincide con la nueva contraseña.", "error")
        return destino
    try:
        user = consultar("SELECT id, password FROM usuarios WHERE usuario = %s", (session["usuario"],), uno=True)
        guardada = user["password"] if user else ""
        correcta = (check_password_hash(guardada, actual) if guardada.startswith(("scrypt:", "pbkdf2:"))
                    else bool(guardada) and secrets.compare_digest(guardada, actual))
        if not correcta:
            flash("La contraseña actual no es correcta.", "error")
            return destino
        ejecutar("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash(nueva), user["id"]))
        flash("Contraseña actualizada correctamente.", "success")
    except Exception as e:
        app.logger.error("Error al cambiar la contraseña: %s", e)
        flash("No se pudo cambiar la contraseña.", "error")
    return destino


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
    """Crea o actualiza las tablas definidas en schema.sql."""
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        sql = f.read()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(sql)
    click.echo("Tablas creadas o actualizadas.")


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
