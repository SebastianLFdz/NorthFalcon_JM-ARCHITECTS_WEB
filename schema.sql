-- Esquema de base de datos de JM Architects (PostgreSQL / Neon).
-- Puedes pegarlo en el SQL Editor de Neon o ejecutarlo con:  flask --app app init-db

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

CREATE INDEX IF NOT EXISTS idx_proyectos_fecha ON proyectos (fecha DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_reviews_fecha ON reviews (fecha DESC, id DESC);

-- Para crear el usuario administrador usa:  flask --app app crear-admin <usuario>
-- (guarda la contraseña cifrada). Si lo insertas a mano desde Neon con la contraseña en
-- texto plano, el sistema la cifrará automáticamente la primera vez que inicies sesión:
-- INSERT INTO usuarios (usuario, password) VALUES ('admin', 'cambia-esta-contraseña');
