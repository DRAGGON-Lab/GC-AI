"""Storing designs in an SBOL DB registry.

Thin helpers over the `sbol-db` client. They carry the two facts about a
GC-AI document that every call needs: it is RDF/XML, and it is SBOL3.

    from sbol_db import SbolDbClient
    from gcai.storage import publish, to_sbol2

    with SbolDbClient("http://localhost:8888") as registry:
        report = publish(registry, result.sbol3,
                         document_iri="https://example.org/designs/mine")
        sbol2 = to_sbol2(registry, "https://example.org/designs/mine")

Needs the db extra: pip install 'gc-ai-client[db]'
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gcai.errors import GCAIError

if TYPE_CHECKING:  # pragma: no cover
    from sbol_db import ImportReport, SbolDbClient

RDF_XML = "rdfxml"
"""The format the GC-AI service writes."""

SBOL3 = "sbol3"
SBOL2 = "sbol2"


def _text(document: bytes | str) -> str:
    return document.decode() if isinstance(document, bytes) else document


def client(url: str, **kwargs: Any) -> "SbolDbClient":
    """An `SbolDbClient`, with a clear error when the db extra is missing."""
    try:
        from sbol_db import SbolDbClient
    except ImportError as exc:  # pragma: no cover - depends on the installation
        raise GCAIError("this needs the SBOL DB client: pip install 'gc-ai-client[db]'") from exc
    return SbolDbClient(url, **kwargs)


def publish(
    registry: "SbolDbClient",
    document: bytes | str,
    *,
    document_iri: str,
    name: str | None = None,
    description: str | None = None,
    namespace: str | None = None,
    overwrite: int = 0,
) -> "ImportReport":
    """Import a generated document into the registry.

    `overwrite` says what happens when `document_iri` is already there: 0
    fails, 1 replaces, 2 merges. The report carries the registry's validation
    result, which it runs on every import.
    """
    return registry.create_graph(
        _text(document),
        format=RDF_XML,
        document_iri=document_iri,
        name=name,
        description=description,
        namespace=namespace,
        overwrite=overwrite,
        version=SBOL3,
    )


def fetch(registry: "SbolDbClient", iri: str, *, version: str = SBOL3) -> str:
    """Read an object and everything it references back out, as RDF/XML."""
    rdf: str = registry.export_rdf(iri, format=RDF_XML, version=version)
    return rdf


def to_sbol2(registry: "SbolDbClient", iri: str) -> str:
    """The SBOL2 form of an object the registry holds.

    The registry does the conversion.
    """
    return fetch(registry, iri, version=SBOL2)
