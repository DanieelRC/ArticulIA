"""Dobles de prueba compartidos: corpus en memoria con texto real de la LFT y LLM guionizado."""

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk

from articulia.agent.state import Respuesta, Verificacion


def _art(numero: str, texto: str) -> dict:
    return {
        "id": f"LFT-{numero}",
        "ley": "LFT",
        "ley_nombre": "Ley Federal del Trabajo",
        "numero": numero,
        "tipo": "articulo",
        "titulo": "Título TERCERO. Condiciones de Trabajo",
        "capitulo": "Capítulo II. Jornada de trabajo",
        "texto": texto,
        "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf",
    }


LFT_59 = _art(
    "59", "La duración máxima de la jornada ordinaria de trabajo será de cuarenta horas\nsemanales."
)
LFT_61 = _art(
    "61",
    "La duración de la jornada diaria será de ocho horas la diurna, siete la nocturna y siete\n"
    "horas y media la mixta.",
)


class FakeCorpus:
    """Corpus en memoria: `buscar` devuelve todo lo de la ley pedida."""

    def __init__(self, articulos: list[dict]) -> None:
        self.articulos = articulos
        self.llamadas: list[tuple[str, Any]] = []

    def buscar(self, consulta: str, leyes: list[str] | None, top_k: int) -> list[dict]:
        self.llamadas.append(("buscar", (consulta, leyes)))
        return [a for a in self.articulos if not leyes or a["ley"] in leyes][:top_k]

    def obtener(self, ley: str, numero: str) -> dict | None:
        self.llamadas.append(("obtener", (ley, numero)))
        return next((a for a in self.articulos if a["id"] == f"{ley}-{numero}"), None)


class _Script:
    def __init__(self, salidas: list[Any]) -> None:
        self.salidas = list(salidas)

    def invoke(self, _mensajes: Any, *_: Any, **__: Any) -> Any:
        assert self.salidas, "El LLM simulado se quedó sin respuestas"
        return self.salidas.pop(0)


class FakeLLM:
    """LLM con respuestas guionizadas para razonar, generar y verificar."""

    def __init__(
        self,
        razonar: list[AIMessage],
        respuestas: list[Respuesta] = (),
        verificaciones: list[Verificacion] = (),
    ) -> None:
        self.razonar = _Script(razonar)
        self.estructurado = {Respuesta: _Script(respuestas), Verificacion: _Script(verificaciones)}

    def bind_tools(self, _tools: Any) -> _Script:
        return self.razonar

    def with_structured_output(self, schema: type) -> _Script:
        return self.estructurado[schema]

    def stream(self, _mensajes: Any, *_: Any, **__: Any) -> Any:
        """La generación es texto libre en trozos; la abstención va con su prefijo."""
        resp: Respuesta = self.estructurado[Respuesta].invoke(None)
        texto = f"SIN_EVIDENCIA: {resp.respuesta}" if resp.sin_evidencia else resp.respuesta
        mitad = len(texto) // 2
        for trozo in (texto[:5], texto[5:mitad], texto[mitad:]):
            yield AIMessageChunk(trozo)

    def pendientes(self) -> int:
        return len(self.razonar.salidas) + sum(len(s.salidas) for s in self.estructurado.values())


def _tool_call(name: str, args: dict, id_: str = "c1") -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": id_}])
