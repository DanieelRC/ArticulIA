"""Topes que acotan el costo del agente: rondas de búsqueda y texto enviado al LLM."""

from fakes import LFT_59, LFT_61, FakeCorpus, FakeLLM, _art, _tool_call

from articulia.agent.graph import build_graph, responder
from articulia.agent.state import Respuesta, Verificacion
from articulia.agent.tools import MAX_CHARS_ARTICULO, formatear_articulo, texto_para_llm

PREGUNTA = "¿Cuántas horas puedo trabajar como máximo?"
BUENA = Respuesta(
    respuesta="La jornada ordinaria no puede pasar de cuarenta horas a la semana [LFT, art. 59]."
)


def _busquedas(n: int) -> list:
    return [_tool_call("buscar_articulos", {"consulta": f"q{i}"}, f"c{i}") for i in range(n)]


def test_sin_articulos_busca_hasta_el_limite_y_se_abstiene() -> None:
    llm = FakeLLM(razonar=_busquedas(5))
    resp = responder(PREGUNTA, graph=build_graph(llm, FakeCorpus([])))
    assert resp.sin_evidencia
    assert llm.pendientes() == 0


def test_tras_tres_rondas_con_articulos_redacta_sin_mas_busquedas() -> None:
    # El modelo quiere seguir buscando, pero ya hay artículos: la cuarta vuelta no llama al LLM.
    llm = FakeLLM(
        razonar=_busquedas(4),
        respuestas=[BUENA],
        verificaciones=[Verificacion(respaldada=True)],
    )
    corpus = FakeCorpus([LFT_59, LFT_61])
    resp = responder(PREGUNTA, graph=build_graph(llm, corpus))
    assert not resp.sin_evidencia
    assert len(corpus.llamadas) == 3
    assert len(llm.razonar.salidas) == 1  # la cuarta búsqueda guionizada nunca se pidió


def test_articulo_corto_va_completo() -> None:
    texto, recortado = texto_para_llm(LFT_61)
    assert texto == LFT_61["texto"]
    assert not recortado
    assert "recortado" not in formatear_articulo(LFT_61)


def test_articulo_largo_se_recorta_al_fragmento_relevante() -> None:
    relleno = (LFT_59["texto"] + " ") * 200  # ~18 mil caracteres de texto real repetido
    fragmento = "Ley Federal del Trabajo, artículo 61\n" + LFT_61["texto"]
    largo = _art("61", relleno) | {"fragmento": fragmento}

    texto, recortado = texto_para_llm(largo)
    assert recortado
    assert LFT_61["texto"] in texto
    assert "Ley Federal del Trabajo, artículo 61" not in texto  # sin la línea de contexto
    assert len(texto) < MAX_CHARS_ARTICULO
    assert 'recortado="si"' in formatear_articulo(largo)


def test_articulo_largo_sin_fragmento_va_el_inicio() -> None:
    relleno = (LFT_59["texto"] + " ") * 200
    texto, recortado = texto_para_llm(_art("59", relleno))
    assert recortado
    assert texto.startswith(LFT_59["texto"])
    assert len(texto) <= MAX_CHARS_ARTICULO + 5
