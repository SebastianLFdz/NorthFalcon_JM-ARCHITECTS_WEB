# JM Architects

Sitio web de JM Architects migrado a Flask, con plantillas Jinja, navegación consistente, diseño responsive y formularios de contacto, agenda y reseñas.

## Ejecutar localmente

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app app run --debug
```

La aplicación queda disponible en `http://127.0.0.1:5000`. Las reseñas y mensajes se guardan en `jm_architects.sqlite3`, archivo que está excluido de Git.

## Estructura

- `app.py`: aplicación Flask, rutas, validaciones y acceso a SQLite.
- `templates/`: layout base y páginas Jinja.
- `static/css/site.css`: sistema visual responsive.
- `static/js/site.js`: menú móvil y mensajes temporales.
- `vercel.json`: configuración del runtime Python de Vercel.

## Despliegue en Vercel

Importa el repositorio en Vercel y deja el framework preset en blanco. Vercel detectará `vercel.json` y usará `app.py` como función Python. Define `SECRET_KEY` como variable de entorno antes de publicar.

SQLite sirve para desarrollo y demostración. En producción serverless, configura `DATABASE_PATH` hacia una base persistente compatible con tu proveedor o sustituye la capa SQLite por Postgres/Supabase, ya que el sistema de archivos local de Vercel no garantiza persistencia entre invocaciones.