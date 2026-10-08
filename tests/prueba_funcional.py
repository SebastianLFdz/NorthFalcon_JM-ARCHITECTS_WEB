"""Prueba funcional de punta a punta de JM Architects.

Usa SOLO la base de datos indicada en TEST_DATABASE_URL (nunca la de producción).
Crea sus propios registros marcados con "[PRUEBA]" y los elimina al terminar.

    python tests/prueba_funcional.py
"""
import base64
import io
import os
import re
import sys
from datetime import datetime, timezone
from unittest import mock

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if not TEST_DB:
    sys.exit("Define TEST_DATABASE_URL con una base de datos de pruebas.")
os.environ["DATABASE_URL"] = TEST_DB
os.environ["RESEND_API_KEY"] = ""  # vacía: impide que un .env local envíe correos reales
os.environ["TURNSTILE_SITE_KEY"] = ""
os.environ["TURNSTILE_SECRET_KEY"] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg  # noqa: E402
import app as modulo  # noqa: E402
from app import app  # noqa: E402

MARCA = "[PRUEBA]"
USUARIO = "prueba_auto"
CLAVE = "Clave-Prueba-123"
USUARIO_PLANO = "prueba_plano"

# PNG de 1x1 px y JPEG mínimo válidos
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"

resultados = []
_ip = [0]


def check(nombre, condicion, detalle=""):
    resultados.append((nombre, bool(condicion)))
    estado = "OK  " if condicion else "FALLA"
    print(f"[{estado}] {nombre}" + (f" -> {detalle}" if detalle and not condicion else ""))


def sql(query, params=(), uno=False):
    with psycopg.connect(TEST_DB) as conn:
        cur = conn.execute(query, params)
        if cur.description is None:
            return None
        return cur.fetchone() if uno else cur.fetchall()


def cliente():
    """Cliente con una IP distinta, para que los límites anti-abuso no se mezclen entre pruebas."""
    _ip[0] += 1
    c = app.test_client()
    c.environ_base["HTTP_X_FORWARDED_FOR"] = f"10.99.0.{_ip[0]}"
    return c


def token(c, ruta="/contacto"):
    html = c.get(ruta).get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def texto(resp):
    return resp.get_data(as_text=True)


def limpiar():
    sql("DELETE FROM proyectos WHERE titulo LIKE %s", (MARCA + "%",))
    sql("DELETE FROM reviews WHERE nombre LIKE %s", (MARCA + "%",))
    sql("DELETE FROM mensajes WHERE nombre LIKE %s", (MARCA + "%",))
    sql("DELETE FROM articulos WHERE titulo LIKE %s", (MARCA + "%",))
    sql("DELETE FROM usuarios WHERE usuario IN (%s, %s)", (USUARIO, USUARIO_PLANO))
    sql("DELETE FROM intentos_login WHERE usuario LIKE 'prueba%%' OR usuario LIKE %s", (MARCA + "%",))


def login(c, usuario=USUARIO, clave=CLAVE):
    return c.post("/login", data={"usuario": usuario, "password": clave, "csrf_token": token(c, "/login")})


def main():
    runner = app.test_cli_runner()
    r = runner.invoke(args=["init-db"])
    check("CLI init-db crea las tablas", r.exit_code == 0, r.output)
    r = runner.invoke(args=["init-db"])
    check("CLI init-db se puede ejecutar dos veces", r.exit_code == 0, r.output)
    limpiar()
    r = runner.invoke(args=["crear-admin", USUARIO, "--password", CLAVE])
    check("CLI crear-admin guarda el usuario", r.exit_code == 0, r.output)
    guardada = sql("SELECT password FROM usuarios WHERE usuario = %s", (USUARIO,), uno=True)[0]
    check("La contraseña se guarda cifrada", guardada.startswith(("scrypt:", "pbkdf2:")))

    publico = cliente()

    # ---- Páginas públicas, SEO y estáticos ----
    for ruta in ["/", "/nosotros", "/servicios", "/proyectos", "/blog", "/blog/dividir-terreno-nuevo-leon",
                 "/preguntas", "/resenas", "/reseñas", "/referencias", "/contacto", "/login", "/aviso-de-privacidad"]:
        resp = publico.get(ruta)
        check(f"GET {ruta} -> 200", resp.status_code == 200, resp.status_code)
    check("Página inexistente -> 404", publico.get("/no-existe").status_code == 404)
    check("Blog inexistente -> 404", publico.get("/blog/no-existe").status_code == 404)
    resp = publico.get("/Nosotros.html")
    check("Enlace del prototipo redirige (301)", resp.status_code == 301 and resp.location.endswith("/nosotros"))
    resp = publico.get("/index.html")
    check("/index.html redirige a /", resp.status_code == 301 and resp.location.endswith("/"))
    resp = publico.get("/nota_1.html")
    check("/nota_1.html redirige al artículo", resp.status_code == 301 and "dividir-terreno-nuevo-leon" in resp.location)
    html = texto(publico.get("/"))
    check("Enlace Inicio apunta a / y está marcado", 'href="/" class="activo" aria-current="page">Inicio' in html)
    check("Carga la fuente Montserrat", "family=Montserrat" in html and "Poppins" not in html)
    check("Favicon enlazado", 'rel="icon"' in html and "apple-touch-icon" in html)
    check("Etiquetas Open Graph", 'property="og:title"' in html and 'property="og:image"' in html)
    check("Datos estructurados de negocio local", '"@type": "ProfessionalService"' in html)
    check("Enlace al aviso de privacidad en el pie", "/aviso-de-privacidad" in html)
    check("Facebook oculto mientras no haya URL", "fa-facebook-f" not in html)
    check("CSS con versión para caché", re.search(r'CSS/estilos\.css\?v=\d+', html) is not None)
    check("Descripción propia por página", "Preguntas frecuentes sobre subdivisión" in texto(publico.get("/preguntas")))
    fav = publico.get("/favicon.ico")
    check("favicon.ico", fav.status_code == 200 and fav.mimetype == "image/x-icon")
    rob = texto(publico.get("/robots.txt"))
    check("robots.txt bloquea /admin e indica sitemap", "Disallow: /admin" in rob and "sitemap.xml" in rob)
    sm = texto(publico.get("/sitemap.xml"))
    check("sitemap.xml incluye páginas y artículos", "<loc>http://localhost/servicios</loc>" in sm and "dividir-terreno-nuevo-leon" in sm)
    est = publico.get("/static/CSS/estilos.css?v=1")
    check("Estáticos versionados con caché larga", "immutable" in est.headers.get("Cache-Control", ""))
    check("Estáticos: fondo de contacto", publico.get("/static/IMG/fondo-herramientas.jpg").status_code == 200)
    check("Contacto preselecciona servicio", 'value="Avalúos" selected' in texto(publico.get("/contacto?servicio=Avalúos")))
    check("Login marcado como noindex", 'name="robots" content="noindex"' in texto(publico.get("/login")))

    # ---- Zona horaria (Monterrey) ----
    with app.test_request_context():
        tarde = datetime(2026, 10, 9, 2, 30, tzinfo=timezone.utc)  # 8:30 pm del 8 de octubre en Monterrey
        check("Fechas en hora de Monterrey", modulo.fecha_corta(tarde) == "08/10/2026", modulo.fecha_corta(tarde))
        check("Fecha larga en español", modulo.fecha_larga(tarde) == "8 de octubre de 2026")

    # ---- Acceso ----
    c = cliente()
    resp = c.get("/admin")
    check("/admin sin sesión redirige a /login", resp.status_code == 302 and "/login" in resp.location)
    resp = c.post("/login", data={"usuario": USUARIO, "password": CLAVE}, follow_redirects=True)
    check("Login sin token CSRF es rechazado (visitante sin sesión)", "El formulario expiró" in texto(resp)
          and c.get("/admin").status_code == 302)
    c.get("/login")
    resp = c.post("/login", data={"usuario": USUARIO, "password": CLAVE}, follow_redirects=True)
    check("Login sin token CSRF es rechazado (con sesión)", "El formulario expiró" in texto(resp))
    resp = login(c, clave="mala")
    check("Login con contraseña incorrecta", "Credenciales incorrectas" in texto(resp))
    resp = login(c)
    check("Login correcto redirige a /admin", resp.status_code == 302 and resp.location.endswith("/admin"))
    html = texto(c.get("/admin"))
    check("Panel muestra al usuario en la barra", f"</i> {USUARIO}</summary>" in html)
    check("Login ya iniciado redirige al panel", c.get("/login").status_code == 302)

    atacante = cliente()
    for _ in range(5):
        login(atacante, clave="incorrecta")
    resp = login(atacante)
    check("Bloqueo tras 5 intentos fallidos (aun con la clave correcta)", "Demasiados intentos" in texto(resp))
    otro = cliente()
    check("El bloqueo es solo para esa IP", login(otro).status_code == 302)

    # ---- Proyectos ----
    t = token(c, "/admin")
    resp = c.post("/admin/proyectos/crear", data={
        "csrf_token": t, "titulo": f"{MARCA} Lotificación", "descripcion": "Línea 1\nLínea <b>2</b>",
        "fecha": "2026-09-15", "imagen": (io.BytesIO(PNG), "foto.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Crear proyecto", "Proyecto publicado correctamente" in texto(resp))
    fila = sql("SELECT id, imagen_url, actualizado FROM proyectos WHERE titulo = %s", (f"{MARCA} Lotificación",), uno=True)
    check("Proyecto guardado en la base de datos", fila is not None)
    pid = fila[0]
    check("Imagen guardada como data URL PNG", fila[1].startswith("data:image/png;base64,"))

    resp = c.post("/admin/proyectos/crear", data={
        "csrf_token": t, "titulo": f"{MARCA} Malo", "imagen": (io.BytesIO(b"<script>hola</script>"), "x.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Rechaza archivo que no es imagen", "La imagen debe ser JPG" in texto(resp))
    resp = c.post("/admin/proyectos/crear", data={
        "csrf_token": t, "titulo": f"{MARCA} Heic", "imagen": (io.BytesIO(b"\x00\x00\x00 ftypheic"), "IMG_0001.HEIC"),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Mensaje claro para fotos HEIC", "HEIC" in texto(resp))
    resp = c.post("/admin/proyectos/crear", data={"csrf_token": t, "titulo": f"{MARCA} Sin imagen"},
                  content_type="multipart/form-data", follow_redirects=True)
    check("Rechaza proyecto sin imagen", "Selecciona una imagen" in texto(resp))
    check("Los proyectos inválidos no se guardan",
          sql("SELECT COUNT(*) FROM proyectos WHERE titulo IN (%s, %s, %s)",
              (f"{MARCA} Malo", f"{MARCA} Sin imagen", f"{MARCA} Heic"), uno=True)[0] == 0)

    html = texto(publico.get("/proyectos"))
    check("Proyecto visible en /proyectos", f"{MARCA} Lotificación" in html)
    check("Fecha en español", "15 de septiembre de 2026" in html)
    check("Descripción escapada (sin HTML inyectado)", "&lt;b&gt;2&lt;/b&gt;" in html)
    img = publico.get(f"/proyectos/{pid}/imagen?v=1")
    check("Imagen servida como image/png", img.status_code == 200 and img.mimetype == "image/png" and img.data == PNG)
    check("Imagen cacheable por el CDN de Vercel (s-maxage)", "s-maxage=31536000" in img.headers.get("Cache-Control", ""))
    check("Imagen inexistente -> 404", publico.get("/proyectos/999999999/imagen").status_code == 404)

    # Paginación: 6 por página
    for n in range(7):
        c.post("/admin/proyectos/crear", data={"csrf_token": t, "titulo": f"{MARCA} Pag {n}", "fecha": "2000-01-01",
                                              "imagen": (io.BytesIO(PNG), "p.png")}, content_type="multipart/form-data")
    total = sql("SELECT COUNT(*) FROM proyectos", uno=True)[0]
    html = texto(publico.get("/proyectos"))
    check("Página 1 muestra 6 proyectos", html.count('class="post-card"') == 6, html.count('class="post-card"'))
    check("Paginación visible", 'class="paginacion"' in html and "?pagina=2" in html)
    ultima = (total + 5) // 6
    html = texto(publico.get(f"/proyectos?pagina={ultima}"))
    check("Última página con el resto", html.count('class="post-card"') == total - 6 * (ultima - 1))
    check("Página fuera de rango no falla", publico.get("/proyectos?pagina=999").status_code == 200)

    resp = c.post(f"/admin/proyectos/editar/{pid}", data={
        "csrf_token": t, "titulo": f"{MARCA} Lotificación editada", "fecha": "2026-09-20", "descripcion": "Nueva",
        "imagen": (io.BytesIO(b""), ""),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Editar solo textos", "Proyecto actualizado correctamente" in texto(resp))
    fila2 = sql("SELECT titulo, imagen_url, actualizado FROM proyectos WHERE id = %s", (pid,), uno=True)
    check("Editar textos conserva la imagen", fila2[0].endswith("editada") and fila2[1] == fila[1] and fila2[2] == fila[2])
    c.post(f"/admin/proyectos/editar/{pid}", data={
        "csrf_token": t, "titulo": f"{MARCA} Lotificación editada", "fecha": "2026-09-20", "descripcion": "Nueva",
        "imagen": (io.BytesIO(JPG), "nueva.jpg"),
    }, content_type="multipart/form-data")
    fila3 = sql("SELECT imagen_url, actualizado FROM proyectos WHERE id = %s", (pid,), uno=True)
    check("Editar con imagen nueva la reemplaza", fila3[0].startswith("data:image/jpeg") and fila3[1] > fila[2])
    resp = c.post("/admin/proyectos/editar/999999999", data={"csrf_token": t, "titulo": "x", "fecha": "2026-01-01"},
                  content_type="multipart/form-data", follow_redirects=True)
    check("Editar proyecto inexistente avisa", "El proyecto ya no existe" in texto(resp))

    grande = io.BytesIO(b"\xff\xd8\xff" + b"0" * (4 * 1024 * 1024 + 10))
    resp = c.post("/admin/proyectos/crear", data={"csrf_token": t, "titulo": f"{MARCA} Grande", "imagen": (grande, "g.jpg")},
                  content_type="multipart/form-data", headers={"Referer": "http://localhost/admin"}, follow_redirects=True)
    check("Archivo de más de 4 MB rechazado con mensaje", "demasiado grande" in texto(resp))

    # ---- Blog ----
    html = texto(publico.get("/blog/dividir-terreno-nuevo-leon"))
    check("Artículo original migrado a la base de datos", "Lo que dice la Ley antes de firmar" in html)
    check("Subtítulos del artículo (##) como <h3>", "<h3>El respaldo legal" in html)
    check("Imagen del artículo original", publico.get(re.search(r'src="(/articulos/\d+/imagen\?v=\d+)"', html).group(1)).status_code in (200, 302))
    resp = c.post("/admin/articulos/crear", data={
        "csrf_token": t, "titulo": f"{MARCA} ¿Qué es un avalúo?", "extracto": "Resumen corto",
        "contenido": "Primer párrafo <script>x</script>\n\n## Requisitos\n\nSegundo párrafo", "fecha": "2026-10-02",
        "imagen": (io.BytesIO(PNG), "a.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Crear artículo borrador", "guardado como borrador" in texto(resp))
    art = sql("SELECT id, slug, publicado FROM articulos WHERE titulo = %s", (f"{MARCA} ¿Qué es un avalúo?",), uno=True)
    check("Slug generado sin acentos", art and art[1] == "prueba-que-es-un-avaluo", art)
    check("Borrador no es público", publico.get(f"/blog/{art[1]}").status_code == 404
          and f"{MARCA} ¿Qué es un avalúo?" not in texto(publico.get("/blog")))
    c.post("/admin/articulos/crear", data={"csrf_token": t, "titulo": f"{MARCA} ¿Qué es un avalúo?",
                                           "contenido": "Otro", "publicado": "1"}, content_type="multipart/form-data")
    dup = sql("SELECT slug FROM articulos WHERE titulo = %s ORDER BY id", (f"{MARCA} ¿Qué es un avalúo?",))
    check("Títulos repetidos generan slug distinto", len(dup) == 2 and dup[1][0] == "prueba-que-es-un-avaluo-2")
    resp = c.post(f"/admin/articulos/editar/{art[0]}", data={
        "csrf_token": t, "titulo": f"{MARCA} ¿Qué es un avalúo?", "extracto": "Resumen corto",
        "contenido": "Primer párrafo <script>x</script>\n\n## Requisitos\n\nSegundo párrafo",
        "fecha": "2026-10-02", "publicado": "1",
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Publicar artículo editándolo", "Artículo actualizado" in texto(resp))
    html = texto(publico.get(f"/blog/{art[1]}"))
    check("Artículo publicado visible", f"{MARCA} ¿Qué es un avalúo?" in html)
    check("Contenido del artículo escapado", "&lt;script&gt;" in html and "<script>x" not in html)
    check("Subtítulo creado con ##", "<h3>Requisitos</h3>" in html)
    check("Artículo en la lista del blog", f"{MARCA} ¿Qué es un avalúo?" in texto(publico.get("/blog")))
    check("Artículo en el sitemap", art[1] in texto(publico.get("/sitemap.xml")))
    resp = c.post(f"/admin/articulos/eliminar/{art[0]}", data={"csrf_token": t}, follow_redirects=True)
    check("Eliminar artículo", "Artículo eliminado" in texto(resp) and publico.get(f"/blog/{art[1]}").status_code == 404)

    # ---- Reseñas (con moderación) ----
    rc = cliente()
    tp = token(rc, "/resenas")
    resp = rc.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Ana", "comentario": "Excelente trabajo",
                                     "calificacion": "4.5"}, follow_redirects=True)
    check("Enviar reseña avisa que será revisada", "se publicará en cuanto la revisemos" in texto(resp))
    check("Reseña nueva queda pendiente (no es pública)", f"{MARCA} Ana" not in texto(publico.get("/resenas")))
    rc.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Luis", "comentario": "Bien", "calificacion": "3"})
    rc.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Bot", "comentario": "spam", "calificacion": "5",
                              "sitio_web": "http://spam"})
    check("Campo trampa bloquea bots", sql("SELECT COUNT(*) FROM reviews WHERE nombre = %s", (f"{MARCA} Bot",), uno=True)[0] == 0)
    resp = rc.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} X", "comentario": "x", "calificacion": "9"},
                   follow_redirects=True)
    check("Rechaza calificación fuera de rango", "Selecciona una calificación" in texto(resp))
    rc.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Eva", "comentario": "Ok", "calificacion": "4"})
    resp = rc.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Spam4", "comentario": "Otra", "calificacion": "5"},
                   follow_redirects=True)
    check("Límite de 3 reseñas por hora por IP", "Ya recibimos tus reseñas recientes" in texto(resp)
          and sql("SELECT COUNT(*) FROM reviews WHERE nombre = %s", (f"{MARCA} Spam4",), uno=True)[0] == 0)

    html = texto(c.get("/admin"))
    check("Panel muestra reseñas pendientes", "Pendiente" in html and f"{MARCA} Ana" in html and 'class="insignia"' in html)
    for nombre in ("Ana", "Luis"):
        rid = sql("SELECT id FROM reviews WHERE nombre = %s", (f"{MARCA} {nombre}",), uno=True)[0]
        resp = c.post(f"/admin/referencias/aprobar/{rid}", data={"csrf_token": t}, follow_redirects=True)
    check("Aprobar reseña", "Reseña publicada en el sitio" in texto(resp))
    html = texto(publico.get("/resenas"))
    check("Reseña aprobada es pública", f"{MARCA} Ana" in html and f"{MARCA} Eva" not in html)
    html = texto(publico.get("/resenas?stars=4"))
    check("Filtro 4 estrellas incluye la de 4.5", f"{MARCA} Ana" in html and f"{MARCA} Luis" not in html)
    check("Filtro 5 estrellas excluye la de 4.5", f"{MARCA} Ana" not in texto(publico.get("/resenas?stars=5")))
    html = texto(publico.get("/resenas"))
    check("Media estrella dibujada", "fa-star-half-stroke" in html)
    check("Barras de porcentaje con ancho válido", re.search(r'class="barra-relleno" style="width: [\d.]+%;"', html) is not None)
    check("Filtro inválido se ignora", publico.get("/resenas?stars=abc").status_code == 200)
    rid = sql("SELECT id FROM reviews WHERE nombre = %s", (f"{MARCA} Ana",), uno=True)[0]
    resp = c.post(f"/admin/referencias/aprobar/{rid}", data={"csrf_token": t}, follow_redirects=True)
    check("Ocultar reseña publicada", "Reseña ocultada" in texto(resp) and f"{MARCA} Ana" not in texto(publico.get("/resenas")))
    resp = c.post(f"/admin/referencias/eliminar/{rid}", data={"csrf_token": t}, follow_redirects=True)
    check("Eliminar reseña", "Reseña eliminada" in texto(resp)
          and sql("SELECT COUNT(*) FROM reviews WHERE id = %s", (rid,), uno=True)[0] == 0)
    resp = c.post(f"/admin/proyectos/eliminar/{pid}", data={"csrf_token": t}, follow_redirects=True)
    check("Eliminar proyecto", "Proyecto eliminado" in texto(resp)
          and sql("SELECT COUNT(*) FROM proyectos WHERE id = %s", (pid,), uno=True)[0] == 0)
    check("Acciones del panel exigen sesión",
          publico.post(f"/admin/proyectos/eliminar/{pid}", data={"csrf_token": token(publico)}).status_code == 302)

    # ---- Contacto ----
    cc = cliente()
    tc = token(cc)
    datos = {"csrf_token": tc, "nombre": f"{MARCA} Juan <b>", "correo": "juan@example.com", "telefono": "8281234567",
             "servicio": "Avalúos", "mensaje": "Hola\nquiero un avalúo", "acepto_privacidad": "1"}
    resp = cc.post("/contacto", data={k: v for k, v in datos.items() if k != "acepto_privacidad"}, follow_redirects=True)
    check("Contacto exige aceptar el aviso de privacidad", "debes aceptar el aviso de privacidad" in texto(resp))
    resp = cc.post("/contacto", data={**datos, "correo": "sin-arroba"}, follow_redirects=True)
    check("Contacto valida el correo", "correo electrónico válido" in texto(resp))
    resp = cc.post("/contacto", data={**datos, "archivo": (io.BytesIO(b"MZ"), "virus.exe")},
                   content_type="multipart/form-data", follow_redirects=True)
    check("Contacto rechaza adjuntos no permitidos", "El archivo adjunto debe ser PDF" in texto(resp))
    resp = cc.post("/contacto", data=datos)
    check("Sin Resend el mensaje igual se recibe", resp.status_code == 302 and "exito=1" in resp.location)
    msg = sql("SELECT id, enviado, leido FROM mensajes WHERE nombre = %s ORDER BY id DESC", (f"{MARCA} Juan <b>",), uno=True)
    check("Mensaje guardado en la base de datos (no enviado)", msg is not None and msg[1] is False)

    with mock.patch.dict(os.environ, {"RESEND_API_KEY": "re_prueba", "RECEIVER_EMAIL": "destino@example.com"}), \
            mock.patch("resend.Emails.send") as enviar:
        resp = cc.post("/contacto", data={**datos, "archivo": (io.BytesIO(b"%PDF-1.4"), "Plano Terreno.pdf")},
                       content_type="multipart/form-data")
        check("Contacto con Resend redirige con ?exito=1", resp.status_code == 302 and "exito=1" in resp.location)
        params = enviar.call_args[0][0] if enviar.called else {}
        check("Correo dirigido a RECEIVER_EMAIL", params.get("to") == ["destino@example.com"])
        check("Correo con reply_to del cliente", params.get("reply_to") == "juan@example.com")
        check("Correo escapa HTML del usuario", "Juan &lt;b&gt;" in params.get("html", ""))
        check("Correo incluye adjunto con nombre seguro", params.get("attachments", [{}])[0].get("filename") == "Plano_Terreno.pdf")
        check("Mensaje marcado como enviado",
              sql("SELECT enviado FROM mensajes WHERE nombre = %s ORDER BY id DESC", (datos["nombre"],), uno=True)[0] is True)
        enviar.side_effect = Exception("fallo simulado")
        resp = cc.post("/contacto", data=datos)
        check("Si Resend falla, el mensaje no se pierde", resp.status_code == 302 and "exito=1" in resp.location)
        guardados = sql("SELECT COUNT(*) FROM mensajes WHERE nombre = %s", (datos["nombre"],), uno=True)[0]
        for _ in range(5 - guardados):
            cc.post("/contacto", data=datos)
        resp = cc.post("/contacto", data=datos, follow_redirects=True)
        check("Límite de 5 mensajes por hora por IP", "Recibimos varios mensajes" in texto(resp)
              and sql("SELECT COUNT(*) FROM mensajes WHERE nombre = %s", (datos["nombre"],), uno=True)[0] == 5)

    html = texto(c.get("/admin"))
    check("Panel muestra los mensajes", "Mensajes de contacto" in html and "juan@example.com" in html and "Solo guardado" in html)
    resp = c.post(f"/admin/mensajes/leido/{msg[0]}", data={"csrf_token": t})
    check("Marcar mensaje como leído", sql("SELECT leido FROM mensajes WHERE id = %s", (msg[0],), uno=True)[0] is True)
    resp = c.post(f"/admin/mensajes/eliminar/{msg[0]}", data={"csrf_token": t}, follow_redirects=True)
    check("Eliminar mensaje", "Mensaje eliminado" in texto(resp))

    # ---- Cambiar contraseña ----
    resp = c.post("/admin/cuenta/password", data={"csrf_token": t, "actual": "mala", "nueva": "NuevaClave-9", "confirmar": "NuevaClave-9"},
                  follow_redirects=True)
    check("Cambio de contraseña valida la actual", "La contraseña actual no es correcta" in texto(resp))
    resp = c.post("/admin/cuenta/password", data={"csrf_token": t, "actual": CLAVE, "nueva": "corta", "confirmar": "corta"},
                  follow_redirects=True)
    check("Cambio de contraseña exige 8 caracteres", "al menos 8 caracteres" in texto(resp))
    resp = c.post("/admin/cuenta/password", data={"csrf_token": t, "actual": CLAVE, "nueva": "NuevaClave-9", "confirmar": "NuevaClave-9"},
                  follow_redirects=True)
    check("Cambio de contraseña correcto", "Contraseña actualizada" in texto(resp))
    check("La nueva contraseña funciona", login(cliente(), clave="NuevaClave-9").status_code == 302)

    # ---- Contraseña en texto plano (insertada a mano en Neon) ----
    sql("INSERT INTO usuarios (usuario, password) VALUES (%s, %s)", (USUARIO_PLANO, "plana123"))
    check("Login con contraseña en texto plano", login(cliente(), USUARIO_PLANO, "plana123").status_code == 302)
    nueva = sql("SELECT password FROM usuarios WHERE usuario = %s", (USUARIO_PLANO,), uno=True)[0]
    check("Contraseña en texto plano se cifra al iniciar sesión", nueva.startswith(("scrypt:", "pbkdf2:")))

    # ---- Cerrar sesión ----
    c.get("/logout")
    check("Logout cierra la sesión", c.get("/admin").status_code == 302)

    limpiar()
    fallas = [n for n, ok in resultados if not ok]
    print(f"\n{len(resultados) - len(fallas)}/{len(resultados)} pruebas correctas.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
