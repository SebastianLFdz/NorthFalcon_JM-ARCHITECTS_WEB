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
from unittest import mock

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if not TEST_DB:
    sys.exit("Define TEST_DATABASE_URL con una base de datos de pruebas.")
os.environ["DATABASE_URL"] = TEST_DB
os.environ["RESEND_API_KEY"] = ""  # vacía: impide que un .env local envíe correos reales

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg  # noqa: E402
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


def token(cliente, ruta="/contacto"):
    html = cliente.get(ruta).get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def limpiar():
    sql("DELETE FROM proyectos WHERE titulo LIKE %s", (MARCA + "%",))
    sql("DELETE FROM reviews WHERE nombre LIKE %s", (MARCA + "%",))
    sql("DELETE FROM usuarios WHERE usuario IN (%s, %s)", (USUARIO, USUARIO_PLANO))


def main():
    runner = app.test_cli_runner()
    r = runner.invoke(args=["init-db"])
    check("CLI init-db crea las tablas", r.exit_code == 0, r.output)
    limpiar()
    r = runner.invoke(args=["crear-admin", USUARIO, "--password", CLAVE])
    check("CLI crear-admin guarda el usuario", r.exit_code == 0, r.output)
    guardada = sql("SELECT password FROM usuarios WHERE usuario = %s", (USUARIO,), uno=True)[0]
    check("La contraseña se guarda cifrada", guardada.startswith(("scrypt:", "pbkdf2:")))

    c = app.test_client()

    # ---- Páginas públicas ----
    for ruta in ["/", "/nosotros", "/servicios", "/proyectos", "/blog", "/blog/dividir-terreno-nuevo-leon",
                 "/preguntas", "/resenas", "/reseñas", "/referencias", "/contacto", "/login"]:
        resp = c.get(ruta)
        check(f"GET {ruta} -> 200", resp.status_code == 200, resp.status_code)
    check("Página inexistente -> 404", c.get("/no-existe").status_code == 404)
    check("Blog inexistente -> 404", c.get("/blog/no-existe").status_code == 404)
    resp = c.get("/Nosotros.html")
    check("Enlace del prototipo redirige (301)", resp.status_code == 301 and resp.location.endswith("/nosotros"))
    resp = c.get("/index.html")
    check("/index.html redirige a /", resp.status_code == 301 and resp.location.endswith("/"))
    check("Enlace Inicio apunta a /", 'href="/" class="activo">Inicio' in c.get("/").get_data(as_text=True))
    check("Estáticos: fondo de contacto", c.get("/static/IMG/fondo-herramientas.jpg").status_code == 200)
    check("Estáticos: estilos.css", c.get("/static/CSS/estilos.css").status_code == 200)
    check("Estáticos: funciones.css", c.get("/static/CSS/funciones.css").status_code == 200)
    check("Estáticos: logo", c.get("/static/IMG/logo_jm_blanco.png").status_code == 200)
    check("Contacto preselecciona servicio", 'value="Avalúos" selected' in c.get("/contacto?servicio=Avalúos").get_data(as_text=True))

    # ---- Acceso ----
    resp = c.get("/admin")
    check("/admin sin sesión redirige a /login", resp.status_code == 302 and "/login" in resp.location)
    resp = c.post("/login", data={"usuario": USUARIO, "password": CLAVE}, follow_redirects=True)
    check("Login sin token CSRF es rechazado", "El formulario expiró" in resp.get_data(as_text=True))
    resp = c.post("/login", data={"usuario": USUARIO, "password": "mala", "csrf_token": token(c, "/login")})
    check("Login con contraseña incorrecta", "Credenciales incorrectas" in resp.get_data(as_text=True))
    resp = c.post("/login", data={"usuario": USUARIO, "password": CLAVE, "csrf_token": token(c, "/login")})
    check("Login correcto redirige a /admin", resp.status_code == 302 and resp.location.endswith("/admin"))
    html = c.get("/admin").get_data(as_text=True)
    check("Panel muestra al usuario en la barra", f"</i> {USUARIO}</summary>" in html)
    check("Login ya iniciado redirige al panel", c.get("/login").status_code == 302)

    # ---- Proyectos ----
    t = token(c, "/admin")
    resp = c.post("/admin/proyectos/crear", data={
        "csrf_token": t, "titulo": f"{MARCA} Lotificación", "descripcion": "Línea 1\nLínea <b>2</b>",
        "fecha": "2026-09-15", "imagen": (io.BytesIO(PNG), "foto.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Crear proyecto", "Proyecto publicado correctamente" in resp.get_data(as_text=True))
    fila = sql("SELECT id, imagen_url, actualizado FROM proyectos WHERE titulo = %s", (f"{MARCA} Lotificación",), uno=True)
    check("Proyecto guardado en la base de datos", fila is not None)
    pid = fila[0]
    check("Imagen guardada como data URL PNG", fila[1].startswith("data:image/png;base64,"))

    resp = c.post("/admin/proyectos/crear", data={
        "csrf_token": t, "titulo": f"{MARCA} Malo", "imagen": (io.BytesIO(b"<script>hola</script>"), "x.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Rechaza archivo que no es imagen", "La imagen debe ser JPG" in resp.get_data(as_text=True))
    resp = c.post("/admin/proyectos/crear", data={"csrf_token": t, "titulo": f"{MARCA} Sin imagen"},
                  content_type="multipart/form-data", follow_redirects=True)
    check("Rechaza proyecto sin imagen", "Selecciona una imagen" in resp.get_data(as_text=True))
    check("Los proyectos inválidos no se guardan",
          sql("SELECT COUNT(*) FROM proyectos WHERE titulo IN (%s, %s)", (f"{MARCA} Malo", f"{MARCA} Sin imagen"), uno=True)[0] == 0)

    publico = app.test_client()
    html = publico.get("/proyectos").get_data(as_text=True)
    check("Proyecto visible en /proyectos", f"{MARCA} Lotificación" in html)
    check("Fecha en español", "15 de septiembre de 2026" in html)
    check("Descripción escapada (sin HTML inyectado)", "&lt;b&gt;2&lt;/b&gt;" in html)
    img = publico.get(f"/proyectos/{pid}/imagen?v=1")
    check("Imagen servida como image/png", img.status_code == 200 and img.mimetype == "image/png" and img.data == PNG)
    check("Imagen con caché larga", "immutable" in img.headers.get("Cache-Control", ""))
    check("Imagen inexistente -> 404", publico.get("/proyectos/999999999/imagen").status_code == 404)

    resp = c.post(f"/admin/proyectos/editar/{pid}", data={
        "csrf_token": t, "titulo": f"{MARCA} Lotificación editada", "fecha": "2026-09-20", "descripcion": "Nueva",
        "imagen": (io.BytesIO(b""), ""),
    }, content_type="multipart/form-data", follow_redirects=True)
    check("Editar solo textos", "Proyecto actualizado correctamente" in resp.get_data(as_text=True))
    fila2 = sql("SELECT titulo, imagen_url, actualizado FROM proyectos WHERE id = %s", (pid,), uno=True)
    check("Editar textos conserva la imagen", fila2[0].endswith("editada") and fila2[1] == fila[1] and fila2[2] == fila[2])
    resp = c.post(f"/admin/proyectos/editar/{pid}", data={
        "csrf_token": t, "titulo": f"{MARCA} Lotificación editada", "fecha": "2026-09-20", "descripcion": "Nueva",
        "imagen": (io.BytesIO(JPG), "nueva.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)
    fila3 = sql("SELECT imagen_url, actualizado FROM proyectos WHERE id = %s", (pid,), uno=True)
    check("Editar con imagen nueva la reemplaza", fila3[0].startswith("data:image/jpeg") and fila3[1] > fila[2])
    resp = c.post("/admin/proyectos/editar/999999999", data={"csrf_token": t, "titulo": "x", "fecha": "2026-01-01"},
                  content_type="multipart/form-data", follow_redirects=True)
    check("Editar proyecto inexistente avisa", "El proyecto ya no existe" in resp.get_data(as_text=True))

    grande = io.BytesIO(b"\xff\xd8\xff" + b"0" * (4 * 1024 * 1024 + 10))
    resp = c.post("/admin/proyectos/crear", data={"csrf_token": t, "titulo": f"{MARCA} Grande", "imagen": (grande, "g.jpg")},
                  content_type="multipart/form-data", headers={"Referer": "http://localhost/admin"}, follow_redirects=True)
    check("Archivo de más de 4 MB rechazado con mensaje", "demasiado grande" in resp.get_data(as_text=True))

    # ---- Reseñas ----
    tp = token(publico, "/resenas")
    resp = publico.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Ana", "comentario": "Excelente trabajo",
                                          "calificacion": "4.5"}, follow_redirects=True)
    check("Publicar reseña", "Gracias por compartir" in resp.get_data(as_text=True))
    publico.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Luis", "comentario": "Bien", "calificacion": "3"})
    publico.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} Bot", "comentario": "spam", "calificacion": "5",
                                   "sitio_web": "http://spam"})
    check("Campo trampa bloquea bots", sql("SELECT COUNT(*) FROM reviews WHERE nombre = %s", (f"{MARCA} Bot",), uno=True)[0] == 0)
    resp = publico.post("/resenas", data={"csrf_token": tp, "nombre": f"{MARCA} X", "comentario": "x", "calificacion": "9"},
                        follow_redirects=True)
    check("Rechaza calificación fuera de rango", "Selecciona una calificación" in resp.get_data(as_text=True))
    html = publico.get("/resenas?stars=4").get_data(as_text=True)
    check("Filtro 4 estrellas incluye la de 4.5", f"{MARCA} Ana" in html and f"{MARCA} Luis" not in html)
    html = publico.get("/resenas?stars=5").get_data(as_text=True)
    check("Filtro 5 estrellas excluye la de 4.5", f"{MARCA} Ana" not in html)
    html = publico.get("/resenas").get_data(as_text=True)
    check("Media estrella dibujada", "fa-star-half-stroke" in html)
    check("Barras de porcentaje con ancho válido", re.search(r'class="barra-relleno" style="width: [\d.]+%;"', html) is not None)
    check("Filtro inválido se ignora", publico.get("/resenas?stars=abc").status_code == 200)

    rid = sql("SELECT id FROM reviews WHERE nombre = %s", (f"{MARCA} Ana",), uno=True)[0]
    html = c.get("/admin").get_data(as_text=True)
    check("Panel lista proyectos y reseñas", f"{MARCA} Lotificación editada" in html and f"{MARCA} Ana" in html)
    resp = c.post(f"/admin/referencias/eliminar/{rid}", data={"csrf_token": t}, follow_redirects=True)
    check("Eliminar reseña", "Reseña eliminada" in resp.get_data(as_text=True)
          and sql("SELECT COUNT(*) FROM reviews WHERE id = %s", (rid,), uno=True)[0] == 0)
    resp = c.post(f"/admin/proyectos/eliminar/{pid}", data={"csrf_token": t}, follow_redirects=True)
    check("Eliminar proyecto", "Proyecto eliminado" in resp.get_data(as_text=True)
          and sql("SELECT COUNT(*) FROM proyectos WHERE id = %s", (pid,), uno=True)[0] == 0)
    check("Acciones del panel exigen sesión",
          publico.post(f"/admin/proyectos/eliminar/{pid}", data={"csrf_token": tp}).status_code == 302)

    # ---- Contacto ----
    datos = {"csrf_token": tp, "nombre": "Juan <b>", "correo": "juan@example.com", "telefono": "8281234567",
             "servicio": "Avalúos", "mensaje": "Hola\nquiero un avalúo"}
    resp = publico.post("/contacto", data=datos, follow_redirects=True)
    check("Contacto sin RESEND_API_KEY muestra aviso", "aún no está disponible" in resp.get_data(as_text=True))
    resp = publico.post("/contacto", data={**datos, "correo": "sin-arroba"}, follow_redirects=True)
    check("Contacto valida el correo", "correo electrónico válido" in resp.get_data(as_text=True))
    with mock.patch.dict(os.environ, {"RESEND_API_KEY": "re_prueba", "RECEIVER_EMAIL": "destino@example.com"}), \
            mock.patch("resend.Emails.send") as enviar:
        resp = publico.post("/contacto", data={**datos, "archivo": (io.BytesIO(b"%PDF-1.4"), "plano.pdf")},
                            content_type="multipart/form-data")
        check("Contacto con Resend redirige con ?exito=1", resp.status_code == 302 and "exito=1" in resp.location)
        params = enviar.call_args[0][0] if enviar.called else {}
        check("Correo dirigido a RECEIVER_EMAIL", params.get("to") == ["destino@example.com"])
        check("Correo con reply_to del cliente", params.get("reply_to") == "juan@example.com")
        check("Correo escapa HTML del usuario", "Juan &lt;b&gt;" in params.get("html", ""))
        check("Correo incluye adjunto", params.get("attachments", [{}])[0].get("filename") == "plano.pdf")
        enviar.side_effect = Exception("fallo simulado")
        resp = publico.post("/contacto", data=datos, follow_redirects=True)
        check("Error de Resend muestra aviso", "Ocurrió un problema" in resp.get_data(as_text=True))

    # ---- Contraseña en texto plano (insertada a mano en Neon) ----
    sql("INSERT INTO usuarios (usuario, password) VALUES (%s, %s)", (USUARIO_PLANO, "plana123"))
    c2 = app.test_client()
    resp = c2.post("/login", data={"usuario": USUARIO_PLANO, "password": "plana123", "csrf_token": token(c2, "/login")})
    check("Login con contraseña en texto plano", resp.status_code == 302)
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
