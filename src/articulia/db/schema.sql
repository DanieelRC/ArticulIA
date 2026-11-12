-- Esquema de ArticulIA. Idempotente: se puede aplicar en cada ejecución de la indexación.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Configuración de texto completo en español que además ignora acentos,
-- para que "jornada maxima" encuentre "jornada máxima".
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'es') THEN
        CREATE TEXT SEARCH CONFIGURATION es (COPY = spanish);
        ALTER TEXT SEARCH CONFIGURATION es
            ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem;
    END IF;
END $$;

-- Un renglón por artículo: es la unidad que se cita.
CREATE TABLE IF NOT EXISTS articles (
    id                   text PRIMARY KEY,          -- 'LFT-61'
    ley                  text NOT NULL,             -- 'LFT'
    ley_nombre           text NOT NULL,
    numero               text NOT NULL,             -- '61', '123 Bis', '39-A', 'Primero'
    numero_base          integer,
    tipo                 text NOT NULL CHECK (tipo IN ('articulo', 'transitorio')),
    derogado             boolean NOT NULL DEFAULT false,
    libro                text,
    titulo               text,
    capitulo             text,
    seccion              text,
    texto                text NOT NULL,
    reformas             text[] NOT NULL DEFAULT '{}',
    fecha_ultima_reforma date,
    url                  text NOT NULL,
    content_hash         text NOT NULL,             -- evita recalcular embeddings sin cambios
    tsv                  tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('es', texto), 'A') ||
        setweight(to_tsvector('es', coalesce(capitulo, '') || ' ' || coalesce(titulo, '')), 'B')
    ) STORED
);

CREATE INDEX IF NOT EXISTS articles_tsv_idx ON articles USING gin (tsv);
CREATE INDEX IF NOT EXISTS articles_ley_idx ON articles (ley);

-- Fragmentos de artículo para embeddings: bge-m3 se trunca a 512 tokens y hay artículos
-- de decenas de miles de caracteres (CPEUM 123, LFT 513). Cada fragmento apunta a su artículo.
CREATE TABLE IF NOT EXISTS chunks (
    article_id text    NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    idx        integer NOT NULL,
    ley        text    NOT NULL,                    -- copiado para filtrar sin JOIN
    texto      text    NOT NULL,
    embedding  vector(1024) NOT NULL,
    PRIMARY KEY (article_id, idx)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
