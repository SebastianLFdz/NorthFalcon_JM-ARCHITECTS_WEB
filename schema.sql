-- Esquema de base de datos de JM Architects (PostgreSQL / Neon).
-- Puedes pegarlo en el SQL Editor de Neon o ejecutarlo con:  flask --app app init-db
-- Es seguro ejecutarlo varias veces: solo crea o agrega lo que falte.

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(80) NOT NULL UNIQUE,
    password TEXT NOT NULL,
    creado TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS proyectos (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    descripcion TEXT,
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    imagen_url TEXT NOT NULL,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    comentario TEXT NOT NULL,
    calificacion REAL NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    fecha TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Las reseñas nuevas quedan pendientes hasta que se aprueban desde el panel.
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS aprobada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS ip_hash VARCHAR(64);

CREATE TABLE IF NOT EXISTS mensajes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    correo VARCHAR(120) NOT NULL,
    telefono VARCHAR(30),
    servicio VARCHAR(80),
    mensaje TEXT NOT NULL,
    archivo_nombre VARCHAR(255),
    enviado BOOLEAN NOT NULL DEFAULT FALSE,
    leido BOOLEAN NOT NULL DEFAULT FALSE,
    ip_hash VARCHAR(64),
    fecha TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS intentos_login (
    id SERIAL PRIMARY KEY,
    ip_hash VARCHAR(64) NOT NULL,
    usuario VARCHAR(80),
    fecha TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS articulos (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    titulo VARCHAR(200) NOT NULL,
    extracto VARCHAR(300),
    contenido TEXT NOT NULL,
    imagen_url TEXT,
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    publicado BOOLEAN NOT NULL DEFAULT TRUE,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proyectos_fecha ON proyectos (fecha DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_reviews_fecha ON reviews (fecha DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_reviews_ip ON reviews (ip_hash, fecha);
CREATE INDEX IF NOT EXISTS idx_mensajes_ip ON mensajes (ip_hash, fecha);
CREATE INDEX IF NOT EXISTS idx_intentos_ip ON intentos_login (ip_hash, fecha);
CREATE INDEX IF NOT EXISTS idx_articulos_fecha ON articulos (fecha DESC, id DESC);

-- Artículo que ya existía en el sitio (no se duplica si ya está).
INSERT INTO articulos (slug, titulo, extracto, contenido, imagen_url, fecha)
VALUES (
    'dividir-terreno-nuevo-leon',
    '¿Quieres dividir un terreno en Nuevo León? Lo que dice la Ley antes de firmar',
    'El problema: La historia del "terreno desaparecido" y la trampa del cálculo a ojo',
    'Es una escena clásica en muchas familias: un propietario decide heredar o vender una parte de su propiedad creyendo que tiene, por ejemplo, 500m2 disponibles. Todo se planea sobre la marcha basándose en cercas antiguas, referencias de vecinos o documentos viejos. Sin embargo, al momento de realizar la medición técnica previa al diseño o al trámite formal, la realidad aparece: el terreno mide 430m2.

Esta diferencia no solo genera desacuerdos familiares o contratiempos con los compradores, sino que altera por completo cualquier proyecto. Confiar en "medidas estimadas" o asumir que un terreno se puede dividir simplemente tirando una barda a la mitad es uno de los errores más costosos al gestionar un patrimonio. Sin precisión técnica, surgen problemas de retiros obligatorios, áreas de construcción reducidas y la imposibilidad de escriturar de forma independiente.

## El respaldo legal: Lo que establece la Ley de Asentamientos Humanos de Nuevo León

Para realizar cualquier división de manera válida, la costumbre no basta; es indispensable cumplir con el marco legal vigente en el estado. La Ley de Asentamientos Humanos, Ordenamiento Territorial y Desarrollo Urbano para el Estado de Nuevo León regula estrictamente este tipo de procedimientos:

Definición legal de subdivisión (Artículo 230, Fracción II): La ley define la subdivisión como la partición de un predio ubicado dentro del límite de un centro de población en dos o más fracciones, siempre y cuando dicha partición no requiera la apertura de nuevas vías públicas. Si el proyecto exige la creación de calles o infraestructura pública, se trata entonces de un fraccionamiento, el cual contempla normativas y obligaciones distintas.',
    '/static/IMG/front-view-blurry-lawyer-working.jpg',
    '2026-10-01'
)
ON CONFLICT (slug) DO NOTHING;

-- Para crear el usuario administrador usa:  flask --app app crear-admin <usuario>
-- (guarda la contraseña cifrada). Si lo insertas a mano desde Neon con la contraseña en
-- texto plano, el sistema la cifrará automáticamente la primera vez que inicies sesión:
-- INSERT INTO usuarios (usuario, password) VALUES ('admin', 'cambia-esta-contraseña');
