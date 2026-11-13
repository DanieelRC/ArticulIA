"""Esquemas de entrada y salida de la API."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from articulia.ingest.loader import LEYES

MAX_PREGUNTA = 500

Ley = StrEnum("Ley", {k: k for k in LEYES})  # type: ignore[misc]


class AskRequest(BaseModel):
    """Pregunta del usuario."""

    pregunta: str = Field(
        min_length=3,
        max_length=MAX_PREGUNTA,
        examples=["¿Cuántos días de vacaciones me tocan en mi primer año?"],
    )
    leyes: list[Ley] | None = Field(
        default=None, description="Limitar la búsqueda a estas leyes.", examples=[["LFT"]]
    )

    @field_validator("pregunta")
    @classmethod
    def _sin_espacios_vacios(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("La pregunta está vacía.")
        return v


class CitaOut(BaseModel):
    """Cita resuelta contra el corpus, con enlace al artículo."""

    id: str = Field(examples=["LFT-76"])
    ley: str
    numero: str
    etiqueta: str = Field(examples=["[LFT, art. 76]"])
    url: str = Field(description="Ruta de la API para obtener el artículo completo.")


class AskResponse(BaseModel):
    """Respuesta final del agente."""

    respuesta: str
    citas: list[CitaOut]
    sin_evidencia: bool


class LawOut(BaseModel):
    """Ley disponible en el corpus."""

    clave: str
    nombre: str
    articulos: int = Field(description="Artículos permanentes vigentes (sin derogados).")
    fecha_ultima_reforma: str | None
    url: str = Field(description="PDF oficial en la Cámara de Diputados.")


class ArticleOut(BaseModel):
    """Texto completo de un artículo."""

    id: str
    ley: str
    ley_nombre: str
    numero: str
    tipo: Literal["articulo", "transitorio"]
    derogado: bool
    titulo: str | None
    capitulo: str | None
    seccion: str | None = None
    texto: str
    reformas: list[str] = []
    fecha_ultima_reforma: str | None
    url: str


class HealthOut(BaseModel):
    """Estado del servicio."""

    status: Literal["ok", "degradado"]
    db: bool


class ErrorOut(BaseModel):
    """Error con mensaje legible."""

    detail: str
