from datetime import date

from articulia.ingest.loader import clean_text, parse_last_reform, strip_page_header

# Encabezado y primeras líneas reales de la página 2 de CPEUM.pdf
PAGINA_CPEUM = "\n".join(
    [
        " ",
        "CONSTITUCIÓN POLÍTICA DE LOS ESTADOS UNIDOS MEXICANOS ",
        " ",
        "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN ",
        "Secretaría General ",
        "Secretaría de Servicios Parlamentarios ",
        "Última Reforma DOF 07-10-2026 ",
        " ",
        " ",
        "2 de 416 ",
        "sexuales, el estado civil o cualquier otra que atente contra la dignidad humana y tenga "
        "por objeto anular o ",
        "menoscabar los derechos y libertades de las personas. ",
    ]
)


def test_quita_encabezado_de_pagina() -> None:
    limpio = strip_page_header(PAGINA_CPEUM)
    assert "CÁMARA DE DIPUTADOS" not in limpio
    assert "2 de 416" not in limpio
    assert limpio.lstrip().startswith("sexuales, el estado civil")


def test_pagina_sin_encabezado_queda_igual() -> None:
    texto = "Artículo 61.- La duración de la jornada diaria será de ocho horas la diurna"
    assert strip_page_header(texto) == texto


def test_fecha_de_ultima_reforma() -> None:
    assert parse_last_reform(PAGINA_CPEUM) == date(2026, 10, 7)
    assert parse_last_reform("sin fecha") is None


def test_une_numeral_de_fraccion_con_su_texto() -> None:
    # CPEUM art. 2o., apartado A: el PDF pone "I." solo en su línea.
    texto = "I. \nDecidir, conforme a sus sistemas normativos y de acuerdo con esta Constitución\n"
    assert clean_text(texto).startswith("I. Decidir, conforme a sus sistemas normativos")


def test_colapsa_lineas_vacias_y_espacios() -> None:
    texto = "Artículo 136. Esta Constitución  \n\n\n\nno perderá su fuerza y vigor  \n"
    assert clean_text(texto) == "Artículo 136. Esta Constitución\n\nno perderá su fuerza y vigor\n"
