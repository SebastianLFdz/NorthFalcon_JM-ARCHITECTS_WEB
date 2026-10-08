import os
import sqlite3
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "jm_architects.sqlite3"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "jm-architects-dev-key")


ARTISTS = [
    {"name": "Calibre 50", "genre": "Regional mexicano", "initials": "C50", "image": "IMG/Calibre.jpg"},
    {"name": "Cornelio Vega Jr.", "genre": "Norteño y sierreño", "initials": "CV", "image": "IMG/CORNELIO.jpeg"},
    {"name": "Marca Registrada", "genre": "Corridos", "initials": "MR", "image": "IMG/MARCA-REGISTRADA.jpg"},
    {"name": "Gerardo Ortiz", "genre": "Banda", "initials": "GO", "image": "IMG/10-gerardo-ortiz.jpg"},
]

ARTICLES = [
    {"slug": "calibre-50", "title": "Calibre 50: una nueva etapa sonora", "category": "Cultura", "date": "12 sep 2026", "excerpt": "Lo que está marcando el pulso del regional mexicano esta temporada.", "image": "IMG/Calibre.jpg"},
    {"slug": "cornelio-vega", "title": "Cornelio Vega Jr. y la fuerza de contar historias", "category": "Entrevistas", "date": "08 sep 2026", "excerpt": "Canciones que convierten experiencias cotidianas en una conversación cercana.", "image": "IMG/cornelio1.jpeg"},
    {"slug": "marca-registrada", "title": "Marca Registrada: identidad que se escucha", "category": "Escena", "date": "02 sep 2026", "excerpt": "Una mirada a la evolución de una propuesta que no deja de crecer.", "image": "IMG/MARCA-REGISTRADA.jpg"},
    {"slug": "gerardo-ortiz", "title": "Gerardo Ortiz prepara nuevas fechas", "category": "Agenda", "date": "28 ago 2026", "excerpt": "La agenda de conciertos que conectará al público con sus grandes éxitos.", "image": "IMG/10-gerardo-ortiz.jpg"},
    {"slug": "israel", "title": "Israel: tradición y presente en equilibrio", "category": "Cultura", "date": "21 ago 2026", "excerpt": "El talento emergente que está encontrando su propia voz.", "image": "IMG/israel.jpg"},
    {"slug": "julion-alvarez", "title": "Julión Álvarez vuelve a la conversación", "category": "Escena", "date": "14 ago 2026", "excerpt": "Una carrera construida con cercanía, oficio y escenarios memorables.", "image": "IMG/julion-alavrez.png"},
]

FAQS = [
    ("¿Qué servicios ofrece JM Architects?", "Acompañamos proyectos de bienes raíces, levantamientos, subdivisiones, regularización y desarrollo desde el diagnóstico hasta la entrega."),
    ("¿Por qué necesito un levantamiento topográfico?", "Permite conocer las medidas y límites reales del predio, reducir sorpresas y preparar trámites y proyectos con información precisa."),
    ("¿Cuánto tarda una asesoría?", "La primera conversación suele durar entre 30 y 45 minutos. Después revisamos el caso y compartimos una ruta de trabajo clara."),
    ("¿En qué zona trabajan?", "Atendemos principalmente Cadereyta Jiménez y el área metropolitana de Nuevo León. Escríbenos para revisar proyectos fuera de la zona."),
]


def get_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def get_reviews():
    with get_connection() as connection:
        return connection.execute("SELECT * FROM reviews ORDER BY created_at DESC, id DESC").fetchall()


@app.context_processor
def inject_globals():
    return {"year": 2026, "reviews": get_reviews()}


@app.route("/")
def home():
    return render_template("home.html", title="Soluciones que aterrizan", featured_articles=ARTICLES[:3])


@app.route("/nosotros")
def about():
    return render_template("about.html", title="Nosotros")


@app.route("/servicios")
def services():
    return render_template("services.html", title="Servicios")


@app.route("/artistas")
def artists():
    return render_template("artists.html", title="Artistas", artists=ARTISTS)


@app.route("/blog")
def blog():
    return render_template("blog.html", title="Ideas y territorio", articles=ARTICLES)


@app.route("/blog/<slug>")
def article(slug):
    selected = next((item for item in ARTICLES if item["slug"] == slug), None)
    if selected is None:
        return render_template("404.html", title="Página no encontrada"), 404
    return render_template("article.html", title=selected["title"], article=selected)


@app.route("/preguntas")
def questions():
    return render_template("questions.html", title="Preguntas frecuentes", faqs=FAQS)


@app.route("/podcast")
def podcast():
    return render_template("podcast.html", title="Podcast")


@app.route("/boletos", methods=["GET", "POST"])
def tickets():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        if not name or len(name) > 80 or "@" not in email or len(email) > 120 or not message or len(message) > 1000:
            flash("Completa nombre, correo válido y una descripción breve para solicitar la cita.", "error")
        else:
            with get_connection() as connection:
                connection.execute("INSERT INTO messages (name, email, message) VALUES (?, ?, ?)", (name, email, "Solicitud de cita: " + message))
            flash("Tu solicitud fue recibida. Te contactaremos para confirmar disponibilidad.", "success")
            return redirect(url_for("tickets"))
    return render_template("tickets.html", title="Agenda una asesoría")


@app.route("/reseñas", methods=["GET", "POST"])
def reviews_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        comment = request.form.get("comment", "").strip()
        try:
            rating = int(request.form.get("rating", "0"))
        except ValueError:
            rating = 0
        if not name or len(name) > 80:
            flash("Escribe un nombre válido de hasta 80 caracteres.", "error")
        elif not comment or len(comment) > 500:
            flash("La reseña debe tener entre 1 y 500 caracteres.", "error")
        elif rating not in range(1, 6):
            flash("Selecciona una calificación de 1 a 5 estrellas.", "error")
        else:
            with get_connection() as connection:
                connection.execute("INSERT INTO reviews (name, rating, comment) VALUES (?, ?, ?)", (name, rating, comment))
            flash("Gracias por compartir tu experiencia.", "success")
            return redirect(url_for("reviews_page"))
    return render_template("reviews.html", title="Reseñas")


@app.route("/contacto", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        if not name or len(name) > 80:
            flash("Escribe tu nombre para poder contactarte.", "error")
        elif "@" not in email or len(email) > 120:
            flash("Escribe un correo electrónico válido.", "error")
        elif not message or len(message) > 1000:
            flash("Cuéntanos brevemente qué necesitas, en un máximo de 1000 caracteres.", "error")
        else:
            with get_connection() as connection:
                connection.execute("INSERT INTO messages (name, email, message) VALUES (?, ?, ?)", (name, email, message))
            flash("Mensaje enviado. Nos pondremos en contacto contigo pronto.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html", title="Contacto")


@app.errorhandler(404)
def page_not_found(_error):
    return render_template("404.html", title="Página no encontrada"), 404


init_db()

if __name__ == "__main__":
    app.run(debug=True)