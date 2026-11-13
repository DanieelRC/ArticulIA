"""Pruebas del control de gasto: límite por IP, presupuesto diario, caché y concurrencia."""

import pytest

from articulia.api.limits import (
    AlmacenMemoria,
    Guardia,
    LimiteExcedido,
    LimiteIP,
    Ocupado,
    clave_cache,
)
from articulia.config import Settings


def _guardia(**kw: object) -> Guardia:
    base = {
        "daily_budget_usd": 1.0,
        "rate_limit_per_minute": 100,
        "rate_limit_per_day": 1000,
        "max_concurrent_agents": 2,
    }
    return Guardia(Settings(_env_file=None, **(base | kw)), AlmacenMemoria())


# --- Límite por IP ----------------------------------------------------------------------------


def test_limite_por_minuto_y_ventana_deslizante() -> None:
    lim = LimiteIP(por_minuto=2, por_dia=100)
    lim.registrar("1.1.1.1", ahora=1000.0)
    lim.registrar("1.1.1.1", ahora=1010.0)
    with pytest.raises(LimiteExcedido) as exc:
        lim.registrar("1.1.1.1", ahora=1020.0)
    assert exc.value.reintentar_en == 41  # la primera petición sale de la ventana en 40 s
    lim.registrar("2.2.2.2", ahora=1020.0)  # otra IP no se ve afectada
    lim.registrar("1.1.1.1", ahora=1061.0)  # ya pasó un minuto desde la primera


def test_limite_por_dia() -> None:
    lim = LimiteIP(por_minuto=100, por_dia=3)
    for i in range(3):
        lim.registrar("1.1.1.1", ahora=1000.0 + i)
    with pytest.raises(LimiteExcedido, match="por hoy"):
        lim.registrar("1.1.1.1", ahora=2000.0)
    lim.registrar("1.1.1.1", ahora=1000.0 + 86_400)  # al día siguiente se reinicia


# --- Caché ------------------------------------------------------------------------------------


def test_clave_de_cache_ignora_forma_pero_no_fondo() -> None:
    a = clave_cache("¿Cuál es la jornada máxima?", ["LFT"], "xai/grok", "v1")
    assert a == clave_cache("  cual es la JORNADA   maxima ", ["LFT"], "xai/grok", "v1")
    assert a != clave_cache("¿Cuál es la jornada mínima?", ["LFT"], "xai/grok", "v1")
    assert a != clave_cache("¿Cuál es la jornada máxima?", None, "xai/grok", "v1")
    assert a != clave_cache("¿Cuál es la jornada máxima?", ["LFT"], "gemini/flash", "v1")
    assert a != clave_cache("¿Cuál es la jornada máxima?", ["LFT"], "xai/grok", "v2")


def test_respuesta_guardada_no_consume_presupuesto_ni_cupo() -> None:
    g = _guardia(max_concurrent_agents=1)
    primera = g.admitir("1.1.1.1", "¿Cuál es la jornada máxima?", ["LFT"])
    assert primera.en_cache is None
    g.cerrar(primera, 1000, 500, {"respuesta": "Cuarenta horas [LFT, art. 59].", "citas": []})

    segunda = g.admitir("2.2.2.2", "cual es la jornada maxima", ["LFT"])
    assert segunda.en_cache == {"respuesta": "Cuarenta horas [LFT, art. 59].", "citas": []}
    # No tomó cupo: otra consulta distinta todavía puede entrar.
    tercera = g.admitir("3.3.3.3", "¿Cuánto dura la garantía?", None)
    assert tercera.en_cache is None


def test_cache_desactivable() -> None:
    g = _guardia(answer_cache_ttl_hours=0)
    g.cerrar(g.admitir("1.1.1.1", "¿Jornada máxima?", None), 10, 10, {"respuesta": "x"})
    assert g.admitir("1.1.1.1", "¿Jornada máxima?", None).en_cache is None


# --- Presupuesto ------------------------------------------------------------------------------


def test_costo_segun_precios_configurados() -> None:
    g = _guardia(llm_price_in_per_m=1.0, llm_price_out_per_m=2.0)
    assert g.costo(5227, 5624) == pytest.approx(0.016475)  # consulta real medida con Grok


def test_presupuesto_diario_agotado_devuelve_limite() -> None:
    g = _guardia(daily_budget_usd=0.02)
    a = g.admitir("1.1.1.1", "pregunta uno", None)
    g.cerrar(a, 5227, 5624, None)  # 0.0165 USD: todavía hay presupuesto
    b = g.admitir("1.1.1.1", "pregunta dos", None)
    g.cerrar(b, 5227, 5624, None)  # 0.033 USD: se pasó del tope
    with pytest.raises(LimiteExcedido, match="tope de consultas por hoy"):
        g.admitir("1.1.1.1", "pregunta tres", None)


def test_el_gasto_se_registra_aunque_no_haya_respuesta() -> None:
    g = _guardia()
    g.cerrar(g.admitir("1.1.1.1", "pregunta", None), 100, 200, None)
    assert g.almacen.gasto_hoy() == pytest.approx((100 * 1.0 + 200 * 2.0) / 1e6)


# --- Concurrencia -----------------------------------------------------------------------------


def test_cupos_de_concurrencia() -> None:
    g = _guardia(max_concurrent_agents=1)
    a = g.admitir("1.1.1.1", "pregunta uno", None)
    with pytest.raises(Ocupado):
        g.admitir("2.2.2.2", "pregunta dos", None)
    a.liberar()
    a.liberar()  # liberar dos veces no rompe el semáforo
    g.admitir("2.2.2.2", "pregunta dos", None)
