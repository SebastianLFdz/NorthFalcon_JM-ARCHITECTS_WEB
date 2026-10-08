# JM Architects

Sitio web de JM Architects en Flask, con base de datos PostgreSQL (Neon), correo con Resend y despliegue en Vercel.

## Funciones

- **Páginas públicas:** Inicio, Nosotros, Servicios, Proyectos, Blog, Reseñas, Preguntas frecuentes, Contacto y Aviso de privacidad.
- **Proyectos:** feed público paginado (6 por página) que se administra desde el panel.
- **Blog:** artículos administrables desde el panel (borradores, publicación, imagen, subtítulos con `## `).
- **Reseñas con moderación:** los visitantes envían reseñas de 1 a 5 estrellas; se publican solo cuando el administrador las aprueba.
- **Contacto:** cada mensaje se guarda en la base de datos y además se envía por correo con Resend (con adjunto opcional). Si el correo falla, el mensaje no se pierde: queda en el panel.
- **Panel administrativo** (`/admin`): proyectos, blog, reseñas, mensajes y cambio de contraseña.
- **Seguridad:** contraseñas cifradas, protección CSRF, bloqueo de 15 min tras 5 intentos fallidos de login, límites anti-spam por IP (5 mensajes y 3 reseñas por hora), campo trampa para bots, validación de imágenes y adjuntos, captcha opcional (Cloudflare Turnstile).
- **SEO:** descripción por página, Open Graph (vista previa en WhatsApp/Facebook), datos estructurados de negocio local, `sitemap.xml`, `robots.txt` y favicon.

## Estructura

- `app.py`: aplicación Flask (rutas, validaciones, base de datos, correo y comandos de mantenimiento). Los datos del negocio (teléfono, redes, razón social) están en el diccionario `SITIO`.
- `api/index.py`: punto de entrada que usa Vercel.
- `schema.sql`: tablas (`usuarios`, `proyectos`, `reviews`, `articulos`, `mensajes`, `intentos_login`). Se puede ejecutar varias veces sin perder datos.
- `templates/`: plantillas Jinja; todas heredan de `base.html`.
- `static/CSS/estilos.css`: estilos originales del sitio (depurados de reglas sin uso, sin cambios visuales).
- `static/CSS/funciones.css`: estilos de las funciones nuevas con la misma paleta, y la adaptación a celular.
- `static/js/site.js`: menú móvil, preguntas, slider, diálogos y reducción de fotos antes de subirlas.
- `tests/prueba_funcional.py`: prueba de punta a punta (125 verificaciones) contra una base de datos de pruebas.

Las imágenes de proyectos y artículos se guardan en la base de datos (Vercel no conserva archivos subidos) y el CDN de Vercel las guarda en caché.

## 1. Conectar Neon

1. Crea un proyecto en [Neon](https://neon.tech) y copia la cadena de conexión *pooled*.
2. Abre el **SQL Editor** de Neon, pega el contenido de `schema.sql` y ejecútalo (o usa `flask --app app init-db`).
3. Crea el usuario administrador (con el `.env` configurado):

   ```bash
   flask --app app crear-admin admin
   ```

## 2. Ejecutar localmente

```bash
python -m venv .venv
source .venv/bin/activate      # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # En Windows: copy .env.example .env
flask --app app run --debug
```

## 3. Desplegar en Vercel

1. Importa el repositorio en Vercel (*Framework Preset*: Other).
2. En **Settings → Environment Variables** agrega:
   - `DATABASE_URL` (Neon), `SECRET_KEY` (**obligatoria**), `RESEND_API_KEY`, `RECEIVER_EMAIL`, `RESEND_FROM`.
   - `SITE_URL` con el dominio final, por ejemplo `https://www.tudominio.com`.
   - Opcional: `TURNSTILE_SITE_KEY` y `TURNSTILE_SECRET_KEY` para activar el captcha.
3. Despliega. Después de cambiar variables de entorno hay que volver a desplegar (**Deployments → ⋯ → Redeploy**).

## Datos pendientes de capturar en `app.py` (diccionario `SITIO`)

- `facebook`: URL de la página de Facebook (mientras esté vacía, el ícono no aparece).
- `razon_social`: nombre legal del responsable para el aviso de privacidad.

## Prueba funcional

Con una base de datos **de pruebas** (nunca la de producción; por ejemplo una *branch* de Neon):

```bash
export TEST_DATABASE_URL=postgresql://...   # En Windows: set TEST_DATABASE_URL=...
python tests/prueba_funcional.py
```
