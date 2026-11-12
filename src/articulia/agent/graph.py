"""Grafo del agente con LangGraph."""

from collections.abc import Iterator

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from articulia.agent.nodes import make_nodes, ruta_tras_razonar, ruta_tras_verificar
from articulia.agent.state import MAX_ITERACIONES, AgentState, Respuesta
from articulia.agent.tools import Corpus


def build_graph(
    llm: BaseChatModel | None = None, corpus: Corpus | None = None
) -> CompiledStateGraph:
    """Arma y compila el grafo. Sin argumentos usa el LLM configurado y PostgreSQL."""
    from articulia.config import configurar_trazas

    configurar_trazas()
    if llm is None:
        from articulia.llm import get_llm

        llm = get_llm()
    if corpus is None:
        from articulia.agent.tools import PostgresCorpus

        corpus = PostgresCorpus()

    nodes = make_nodes(llm, corpus)
    g = StateGraph(AgentState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.add_edge(START, "razonar")
    g.add_conditional_edges(
        "razonar",
        ruta_tras_razonar,
        {"herramientas": "herramientas", "generar": "generar", "abstenerse": "abstenerse"},
    )
    g.add_edge("herramientas", "razonar")
    g.add_edge("generar", "verificar")
    g.add_conditional_edges(
        "verificar",
        ruta_tras_verificar,
        {"fin": END, "razonar": "razonar", "abstenerse": "abstenerse"},
    )
    g.add_edge("abstenerse", END)
    return g.compile()


def _inicial(pregunta: str, leyes: list[str] | None) -> AgentState:
    return {"pregunta": pregunta, "leyes": leyes, "iteraciones": 0, "reintentos": 0}


# Cada vuelta usa razonar + herramientas; el verificador puede sumar generar + verificar.
_RECURSION_LIMIT = MAX_ITERACIONES * 2 + 8


def responder(
    pregunta: str, leyes: list[str] | None = None, graph: CompiledStateGraph | None = None
) -> Respuesta:
    """Corre el agente y devuelve la respuesta final con sus citas."""
    graph = graph or build_graph()
    final = graph.invoke(_inicial(pregunta, leyes), {"recursion_limit": _RECURSION_LIMIT})
    return final["respuesta"]


def pasos(
    pregunta: str, leyes: list[str] | None = None, graph: CompiledStateGraph | None = None
) -> Iterator[tuple[str, dict]]:
    """Itera (nodo, actualización) a medida que el agente avanza; útil para streaming (Fase 4)."""
    graph = graph or build_graph()
    for chunk in graph.stream(
        _inicial(pregunta, leyes), {"recursion_limit": _RECURSION_LIMIT}, stream_mode="updates"
    ):
        yield from chunk.items()
