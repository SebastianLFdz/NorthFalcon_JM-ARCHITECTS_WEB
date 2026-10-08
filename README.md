# JM Architects

Sitio web de JM Architects en Flask, con base de datos PostgreSQL (Neon), correo con Resend y despliegue en Vercel.

## Funciones

- **Páginas públicas:** Inicio, Nosotros, Servicios, Proyectos, Blog, Reseñas, Preguntas frecuentes y Contacto.
- **Proyectos (publicaciones):** feed público alimentado desde la base de datos; cada publicación muestra imagen, fecha y un desplegable con los detalles.
- **Reseñas:** cualquier visitante puede dejar una reseña de 1 a 5 estrellas (con medias estrellas). Se muestran el promedio, el total, el porcentaje por estrellas y un filtro por calificación.
- **Contacto:** el formulario envía un correo con Resend, con archivo adjunto opcional (plano, escritura o imagen).
- **Inicio de sesión:** acceso para el personal autorizado (`/login`).
- **Panel administrativo** (`/admin`): crear, editar y eliminar proyectos, y consultar o eliminar reseñas.

## Estructura

- `app.py`: aplicación Flask (rutas, validaciones, base de datos, correo y comandos de mantenimiento).
- `api/index.py`: punto de entrada que usa Vercel.
- `schema.sql`: tablas de la base de datos (`usuarios`, `proyectos`, `reviews`).
- `templates/`: plantillas Jinja; todas heredan de `base.html`.
- `static/CSS/estilos.css`: estilos originales del sitio.
- `static/CSS/funciones.css`: estilos de las funciones nuevas (panel, reseñas, proyectos, menú móvil), con la misma paleta.
- `static/js/site.js`: menú móvil, preguntas frecuentes, slider, ventanas de diálogo y reducción de fotos antes de subirlas.
- `tests/prueba_funcional.py`: prueba de punta a punta contra una base de datos de pruebas.

Las imágenes de los proyectos se guardan en la base de datos (Vercel no conserva archivos subidos) y se sirven desde `/proyectos/<id>/imagen`.

## 1. Conectar Neon

1. Crea un proyecto en [Neon](https://neon.tech) y copia la cadena de conexión *pooled*.
2. Abre el **SQL Editor** de Neon, pega el contenido de `schema.sql` y ejecútalo.
3. Crea el usuario administrador. Desde tu computadora (con el `.env` configurado):

   ```bash
   flask --app app crear-admin admin
   ```

   Te pedirá la contraseña y la guardará cifrada. También puedes insertarlo directamente desde Neon con la contraseña en texto plano; el sistema la cifrará automáticamente la primera vez que inicies sesión.

## 2. Ejecutar localmente

```bash
python -m venv .venv
.venv\Scripts\activate        # En macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # En macOS/Linux: cp .env.example .env
flask --app app run --debug
```

Edita `.env` con tus datos antes de arrancar. La aplicación queda disponible en `http://127.0.0.1:5000`.

## 3. Desplegar en Vercel

1. Sube el repositorio a GitHub e impórtalo en Vercel (deja el *Framework Preset* en *Other*).
2. En **Settings → Environment Variables** agrega:
   - `DATABASE_URL`: cadena de conexión de Neon (también puedes usar la integración de Neon en Vercel, que la crea por ti).
   - `SECRET_KEY`: clave aleatoria (`python -c "import secrets; print(secrets.token_hex(32))"`). **Es obligatoria**: sin ella la aplicación no arranca en Vercel.
   - `RESEND_API_KEY`: API key de Resend.
   - `RECEIVER_EMAIL`: correo que recibe los mensajes de contacto.
   - `RESEND_FROM`: remitente de un dominio verificado en Resend (por ejemplo `JM Architects <contacto@tudominio.com>`).
3. Despliega. `vercel.json` y `api/index.py` le indican a Vercel cómo ejecutar Flask.

## Límites a tener en cuenta

- Vercel acepta peticiones de hasta 4.5 MB. Las fotos de proyectos se reducen automáticamente en el navegador (máx. 1920 px) antes de subirse, y el servidor rechaza archivos de más de 4 MB con un mensaje claro.
- El plan gratuito de Neon incluye 0.5 GB de almacenamiento; con fotos reducidas (~300-600 KB) caben cientos de proyectos.

## Prueba funcional

Con una base de datos **de pruebas** (nunca la de producción; por ejemplo una *branch* de Neon):

```bash
set TEST_DATABASE_URL=postgresql://...      # En macOS/Linux: export TEST_DATABASE_URL=...
python tests/prueba_funcional.py
```

La prueba crea las tablas, un usuario de prueba, publica/edita/elimina proyectos y reseñas, y verifica todas las páginas.
