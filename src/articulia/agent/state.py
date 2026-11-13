"""Estado del grafo y esquemas de salida estructurada."""

import re
from operator import add
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

MAX_ITERACIONES = 5
# Rondas de búsqueda tras las cuales, si ya hay artículos, se redacta con lo que se tiene.
MAX_RONDAS_BUSQUEDA = 3
MAX_REINTENTOS_VERIFICACION = 1

# "[LFT, art. 61]", "[LFT, art. 47 Bis]", "[LFT, art. 39-A]", "[CPEUM, transitorio Primero]"
CITA_RE = re.compile(r"\[(?P<ley>[A-Z]+),\s*(?P<tipo>art\.|transitorio)\s*(?P<numero>[^\]]+?)\]")


class Cita(BaseModel):
    """Referencia a un artículo del corpus."""

    ley: str = Field(description="Clave de la ley, p. ej. LFT o CPEUM")
    numero: str = Field(description="Número del artículo tal como aparece en el corpus, p. ej. 61")
    transitorio: bool = False

    @property
    def article_id(self) -> str:
        """Id en la base: 'LFT-61', 'LFT-47_Bis', 'CPEUM-T-Primero'."""
        prefijo = f"{self.ley}-T" if self.transitorio else self.ley
        return f"{prefijo}-{self.numero.strip().replace(' ', '_')}"

    def etiqueta(self) -> str:
        """Formato de cita en el texto: '[LFT, art. 61]'."""
        tipo = "transitorio" if self.transitorio else "art."
        return f"[{self.ley}, {tipo} {self.numero}]"


def extraer_citas(texto: str) -> list[Cita]:
    """Citas en formato `[LEY, art. N]` presentes en un texto, sin repetir."""
    vistas: dict[str, Cita] = {}
    for m in CITA_RE.finditer(texto):
        cita = Cita(ley=m["ley"], numero=m["numero"], transitorio=m["tipo"] == "transitorio")
        vistas.setdefault(cita.article_id, cita)
    return list(vistas.values())


class Respuesta(BaseModel):
    """Salida final del agente."""

    respuesta: str = Field(
        description="Respuesta en español con una cita [LEY, art. N] tras cada afirmación."
    )
    citas: list[Cita] = Field(default_factory=list, description="Artículos citados.")
    sin_evidencia: bool = Field(
        default=False,
        description="True si los artículos recuperados no bastan para responder.",
    )


class Verificacion(BaseModel):
    """Juicio del verificador sobre un borrador."""

    respaldada: bool = Field(
        description="True si cada afirmación está respaldada por los artículos que cita."
    )
    problemas: list[str] = Field(
        default_factory=list, description="Afirmaciones sin respaldo o citas incorrectas."
    )


def _merge_articulos(a: dict[str, dict], b: dict[str, dict]) -> dict[str, dict]:
    return a | b


class AgentState(TypedDict, total=False):
    """Estado compartido por los nodos del grafo."""

    pregunta: str
    leyes: list[str] | None  # filtro opcional por ley
    messages: Annotated[list[AnyMessage], add_messages]
    articulos: Annotated[dict[str, dict], _merge_articulos]  # id -> artículo recuperado
    consultas: Annotated[list[str], add]  # firmas de llamadas a herramientas ya hechas
    borrador: Respuesta | None
    problemas: Annotated[list[str], add]  # historial de fallos del verificador
    iteraciones: int  # vueltas por el nodo de razonamiento
    reintentos: int  # veces que el verificador mandó de regreso
    faltan_articulos: bool  # el último fallo fue por una cita a un artículo no recuperado
    respuesta: Respuesta | None  # salida final
