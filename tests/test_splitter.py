"""Pruebas del divisor por artículo.

Todos los fragmentos son texto literal de los PDFs del corpus (LeyesBiblio, Cámara de Diputados),
con los saltos de línea originales. Por eso este archivo ignora E501.
"""

from datetime import date

import pytest

from articulia.ingest.loader import LawDocument, clean_text
from articulia.ingest.splitter import Article, is_annotation, parse_article_heading, split_law


def _split(texto: str, clave: str = "CPEUM") -> list[Article]:
    doc = LawDocument(
        clave=clave,
        nombre=clave,
        fecha_ultima_reforma=date(2026, 10, 7),
        url=f"https://www.diputados.gob.mx/LeyesBiblio/pdf/{clave}.pdf",
        texto=clean_text(texto),
    )
    return split_law(doc)


# CPEUM art. 136 (último permanente), contexto previo a los transitorios.
ARTICULO_136 = """Artículo 136. Esta Constitución no perderá su fuerza y vigor, aun cuando por alguna rebelión se
interrumpa su observancia. En caso de que por cualquier trastorno público, se establezca un gobierno
contrario a los principios que ella sanciona, tan luego como el pueblo recobre su libertad, se restablecerá
su observancia, y con arreglo a ella y a las leyes que en su virtud se hubieren expedido, serán juzgados,
así los que hubieren figurado en el gobierno emanado de la rebelión, como los que hubieren cooperado a
ésta.
Artículo original DOF 05-02-1917
"""


# --- Encabezados -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("linea", "numero", "base"),
    [
        # Terminador "." / ".-" y ordinal o, º, °
        (
            "Artículo 1o. En los Estados Unidos Mexicanos todas las personas gozarán de los derechos humanos",
            "1",
            1,
        ),  # CPEUM
        (
            "Artículo 14. A ninguna ley se dará efecto retroactivo en perjuicio de persona alguna.",
            "14",
            14,
        ),  # CPEUM
        (
            "Artículo 1º.- Esta Ley entrará en vigor el día 1o. de mayo de 1970, con excepción de los artículos 71 y",
            "1",
            1,
        ),  # LFT
        (
            "ARTICULO 1°.- Se deroga el artículo 390 del Código Civil para el Distrito y Territorios Federales en",
            "1",
            1,
        ),  # CCF
        # Sufijos
        (
            "Artículo 103-Bis.- La celebración conjunta de matrimonios no exime al Juez del cumplimiento estricto",
            "103 Bis",
            103,
        ),  # CCF
        (
            "Artículo 323 bis.- Los integrantes de la familia, en particular niñas, niños y adolescentes, tienen",
            "323 Bis",
            323,
        ),  # CCF
        (
            "Artículo 114 Quinquies.- No se considerará como violación a esta Ley, la conducta sancionada en el",
            "114 Quinquies",
            114,
        ),  # LFDA
        (
            "ARTÍCULO 65 Bis 7. La Procuraduría podrá celebrar convenios de colaboración o concertación con",
            "65 Bis 7",
            65,
        ),  # LFPC
        (
            "ARTÍCULO 65 Ter 1.- Las disposiciones relativas a derechos de los pasajeros contenidas en la Ley",
            "65 Ter 1",
            65,
        ),  # LFPC
        (
            "Artículo 39-A. En las relaciones de trabajo por tiempo indeterminado o cuando excedan de ciento",
            "39-A",
            39,
        ),  # LFT
        (
            "Artículo 410 A.- El adoptado bajo la forma de adopción plena se equipara al hijo consanguíneo para",
            "410-A",
            410,
        ),  # CCF
        # Errata del PDF (plural)
        (
            "Artículos 135.- Se considera videograma a la fijación de imágenes asociadas, con o sin sonido",
            "135",
            135,
        ),  # LFDA
    ],
)
def test_reconoce_encabezados_reales(linea: str, numero: str, base: int) -> None:
    resultado = parse_article_heading(linea)
    assert resultado is not None
    assert resultado[:2] == (numero, base)


def test_letra_despues_del_terminador_es_texto() -> None:
    resultado = parse_article_heading(
        "Artículo 14. A ninguna ley se dará efecto retroactivo en perjuicio de persona alguna."
    )
    assert resultado is not None
    assert resultado[2].startswith("A ninguna ley")


@pytest.mark.parametrize(
    "linea",
    [
        "artículo 28, párrafo cuarto de la Constitución, manteniendo siempre el Gobierno Federal la propiedad y el",  # CPEUM
        "Artículo vinculado con artículo transitorio DOF 23-02-1946",  # CCF
    ],
)
def test_no_son_encabezados(linea: str) -> None:
    assert parse_article_heading(linea) is None


# --- División --------------------------------------------------------------------------------


def test_estructura_y_notas_de_reforma() -> None:
    texto = """Título Primero

Capítulo I
De los Derechos Humanos y sus Garantías
Denominación del Capítulo reformada DOF 10-06-2011

Artículo 1o. En los Estados Unidos Mexicanos todas las personas gozarán de los derechos humanos
reconocidos en esta Constitución y en los tratados internacionales de los que el Estado Mexicano sea
parte, así como de las garantías para su protección, cuyo ejercicio no podrá restringirse ni suspenderse,
salvo en los casos y bajo las condiciones que esta Constitución establece.
Párrafo reformado DOF 10-06-2011
"""
    [art] = _split(texto)
    assert art.id == "CPEUM-1"
    assert art.titulo == "Título Primero"
    assert art.capitulo == "Capítulo I. De los Derechos Humanos y sus Garantías"
    assert art.texto.startswith("En los Estados Unidos Mexicanos")
    assert "DOF" not in art.texto
    assert art.reformas == ["Párrafo reformado DOF 10-06-2011"]


def test_fraccion_y_nota_de_reforma_partida_en_dos_lineas() -> None:
    # CPEUM art. 73: "X." solo en su línea y lista de fechas que no cabe en una línea.
    texto = """Artículo 73. El Congreso tiene facultad:

X.
Para legislar en toda la República sobre hidrocarburos, minería, sustancias químicas,
explosivos, pirotecnia, industria cinematográfica, comercio, juegos con apuestas y sorteos,
intermediación y servicios financieros, energía eléctrica y nuclear y para expedir las leyes del
trabajo reglamentarias del artículo 123;
Fracción reformada DOF 06-09-1929, 27-04-1933, 18-01-1934, 18-01-1935, 14-12-1940, 24-10-1942, 18-11-1942, 29-12-1947, 06-02-1975,
17-11-1982, 20-08-1993, 20-07-2007

XI.
Para crear y suprimir empleos públicos de la Federación y señalar, aumentar o disminuir sus
"""
    [art] = _split(texto)
    assert "X. Para legislar en toda la República" in art.texto
    assert "XI. Para crear y suprimir empleos" in art.texto
    assert "DOF" not in art.texto
    assert "17-11-1982" not in art.texto
    assert len(art.reformas) == 2


def test_referencia_en_minuscula_no_inicia_articulo() -> None:
    texto = """Artículo 25. Corresponde al Estado la rectoría del desarrollo nacional para garantizar que éste sea
integral y sustentable, que fortalezca la Soberanía de la Nación y su régimen democrático y que,

El sector público tendrá a su cargo, de manera exclusiva, las áreas estratégicas que se señalan en el
artículo 28, párrafo cuarto de la Constitución, manteniendo siempre el Gobierno Federal la propiedad y el
control sobre los organismos y empresas públicas del Estado que en su caso se establezcan.
"""
    [art] = _split(texto)
    assert art.numero == "25"
    assert "artículo 28, párrafo cuarto" in art.texto


def test_referencia_partida_con_mayuscula_no_inicia_articulo() -> None:
    # Transitorio de un decreto de reforma a la CPEUM: "Artículo 123" cae al inicio de línea,
    # pero la línea anterior ("...apartado B del") no cierra oración.
    texto = """Transitorios

Tercero.- A la entrada en vigor de la Ley a que se refiere el apartado B del Artículo 26 de esta
Constitución, los recursos financieros y materiales, así como los trabajadores adscritos al Instituto
Nacional de Estadística, Geografía e Informática, órgano desconcentrado de la Secretaría de Hacienda y
Crédito Público, se transferirán al organismo creado en los términos del presente Decreto. Los
trabajadores que pasen a formar parte del nuevo organismo se seguirán rigiendo por el apartado B del
Artículo 123 de esta Constitución y de ninguna forma resultarán afectados en sus derechos laborales y de
seguridad social.
"""
    arts = _split(ARTICULO_136 + "\n" + texto)
    assert [a.numero for a in arts] == ["136", "Tercero"]
    assert "Artículo 123 de esta Constitución" in arts[1].texto


@pytest.mark.parametrize(
    ("texto", "reforma"),
    [
        (
            "Artículo 169.- (Se deroga).\nArtículo derogado DOF 31-12-1974\n",
            "Artículo derogado DOF 31-12-1974",
        ),
        (
            "Artículo 338.- Se deroga.\nArtículo reformado DOF 01-05-2019. Derogado DOF 02-07-2019\n",
            "Artículo reformado DOF 01-05-2019. Derogado DOF 02-07-2019",
        ),
    ],
)
def test_derogados(texto: str, reforma: str) -> None:
    [art] = _split(texto, clave="LFT")
    assert art.derogado
    assert art.reformas == [reforma]


def test_articulo_vigente_no_es_derogado() -> None:
    [art] = _split(
        "Artículo 170.- Las madres trabajadoras tendrán los siguientes derechos:\n", "LFT"
    )
    assert not art.derogado


def test_articulo_citado_en_nota_editorial_no_es_nuevo() -> None:
    # CCF: dentro del art. 1777 se cita el art. 54 de la Ley del Notariado de 1946.
    texto = """Artículo 1777.- La partición constará en escritura pública, siempre que en la herencia haya bienes
cuya enajenación deba hacerse con esa formalidad.
Artículo vinculado con artículo transitorio DOF 23-02-1946

Nota: El Artículo 14 Transitorio de la Ley del Notariado para el Distrito Federal y Territorios, publicada en
el DOF 23-02-1946, estableció que el artículo 1777, entre otros, del entonces Código Civil para el Distrito y
Territorios Federales, “se modifican (…) en los términos del artículo 54 de la presente Ley”. A su vez, el artículo 54
de la citada Ley, a la letra señalaba:

Artículo 54.- Las enajenaciones de bienes inmuebles cuyo valor convencional sea mayor de quinientos pesos y
la constitución o transmisión de derechos reales estimados en más de quinientos pesos o que garanticen un
crédito por mayor cantidad que la mencionada, para su validez deberán constar en escritura ante Notario.

Artículo 1778.- Los gastos de la partición, se rebajarán del fondo común; los que se hagan por interés
particular de alguno de los herederos o legatarios, se imputarán a su haber.
"""
    arts = _split(texto, clave="CCF")
    assert [a.numero for a in arts] == ["1777", "1778"]
    assert "Nota:" not in arts[0].texto
    assert "enajenaciones" not in arts[0].texto


def test_transitorios_originales_cierre_y_decretos_de_reforma() -> None:
    # Final del CCF: último artículo, transitorios numéricos, fórmula de promulgación y el inicio
    # de los transitorios de decretos de reforma, que se descartan.
    texto = """Artículo 3074.- Las inscripciones que se practiquen en los folios relativos a bienes muebles y
personas morales no producirán más efectos que los señalados en los artículo 2310, fracción II; 2312,
2673, 2694 y 2859 de este Código, y les serán aplicables a los registros las disposiciones relativas a los
bienes inmuebles, en cuanto sean compatibles con la naturaleza de los actos o contratos materia de éste
y del anterior capítulo y con los efectos que las inscripciones producen.
Artículo adicionado DOF 03-01-1979
ARTICULOS TRANSITORIOS
Artículo 1o.- Este Código comenzará a regir el 1o. de octubre de 1932.
Artículo reformado DOF 01-09-1932
Artículo 2o.- Sus disposiciones regirán los efectos jurídicos de los actos anteriores a su vigencia, si
con su aplicación no se violan derechos adquiridos.
Por tanto, mando se imprima, publique, circule y se le dé el debido cumplimiento.
Dado en el Palacio del Poder Ejecutivo Federal, en México, a los treinta días del mes de agosto de mil
novecientos veintiocho. - P. Elías Calles.- Rúbrica.- El Secretario de Estado y del Despacho de
Gobernación, Emilio Portes Gil.- Rúbrica.

ARTÍCULOS TRANSITORIOS DE DECRETOS DE REFORMA

ACLARACION a la publicación del Código Civil para el Distrito y Territorios Federales en
materia común, y para toda la República en materia federal.
"""
    arts = _split(texto, clave="CCF")
    assert [(a.id, a.tipo) for a in arts] == [
        ("CCF-3074", "articulo"),
        ("CCF-T-1", "transitorio"),
        ("CCF-T-2", "transitorio"),
    ]
    assert arts[1].reformas == ["Artículo reformado DOF 01-09-1932"]
    assert "Por tanto" not in arts[2].texto
    assert "Calles" not in arts[2].texto
    assert "ACLARACION" not in arts[2].texto


@pytest.mark.parametrize(
    ("encabezado", "numero"),
    [
        (
            "PRIMERO.- La presente Ley entrará en vigor a los noventa días siguientes a su publicación en el",
            "Primero",
        ),  # LFDA
        (
            "Artículo Decimoprimero. Entre tanto el Congreso de la Unión y los de los",
            "Decimoprimero",
        ),  # CPEUM
        ("Artículo Decimoctavo. Derogado.", "Decimoctavo"),  # CPEUM
        (
            "Décimo Primero.- Los municipios podrán cumplir con las obligaciones a su cargo en materia de",
            "Décimo primero",
        ),  # LFPDPPP
    ],
)
def test_transitorios_con_ordinal(encabezado: str, numero: str) -> None:
    arts = _split(ARTICULO_136 + "\nTransitorios\n\n" + encabezado + "\n")
    assert arts[-1].tipo == "transitorio"
    assert arts[-1].numero == numero


def test_transitorio_derogado() -> None:
    arts = _split(ARTICULO_136 + "\nArtículos Transitorios\n\nArtículo Decimoctavo. Derogado.\n")
    assert arts[-1].derogado


def test_ids_y_metadatos_de_la_ley() -> None:
    texto = """Artículo 61.- La duración de la jornada diaria será de ocho horas la diurna, siete la nocturna y siete
horas y media la mixta.
"""
    [art] = _split(texto, "LFT")
    assert art.id == "LFT-61"
    assert art.numero_base == 61
    assert (
        art.texto
        == "La duración de la jornada diaria será de ocho horas la diurna, siete la nocturna y siete\nhoras y media la mixta."
    )
    assert art.fecha_ultima_reforma == date(2026, 10, 7)
    assert art.url.endswith("/LFT.pdf")


def test_is_annotation() -> None:
    assert is_annotation("Párrafo reformado DOF 04-12-2006, 10-06-2011")
    assert is_annotation("Artículo reformado DOF 01-05-2019. Derogado DOF 02-07-2019")
    assert not is_annotation(
        "Artículo 14. A ninguna ley se dará efecto retroactivo en perjuicio de persona alguna."
    )
