"""Publishing designs to an SBOL DB registry.

An SBOL DB registry holds SBOL3 and serves either SBOL vocabulary. The GC-AI
service writes SBOL3, so `publish` sends a generated document as it stands and
`to_sbol2` asks the registry for the SBOL2 form of an object it holds.

Everything here needs the db extra: pip install 'gc-ai-client[db]'
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, Literal

from gcai.constants import SO_TO_ROLE, Role
from gcai.errors import GCAIError
from gcai.interop._doc import term

if TYPE_CHECKING:  # pragma: no cover
    import httpx

EXTRA_HINT = "this needs the SBOL DB client: pip install 'gc-ai-client[db]'"

RDF_XML = "rdfxml"
"""What the GC-AI service writes, and what SBOL DB should be told it is given."""


def _module() -> Any:
    try:
        import sbol_db
    except ImportError as exc:  # pragma: no cover - depends on the installation
        raise GCAIError(EXTRA_HINT) from exc
    return sbol_db


@dataclass(frozen=True)
class PublishResult:
    """What the registry made of a published document."""

    graph_id: str
    document_iri: str
    object_count: int
    triple_count: int
    validation_status: str
    validation_issue_count: int

    @property
    def valid(self) -> bool:
        """Whether the registry's own validation found nothing to report.

        The registry validates on import, which the GC-AI service does not do,
        so this is a real check rather than a restatement.
        """
        return self.validation_issue_count == 0 and self.validation_status.lower() in {
            "valid",
            "ok",
            "passed",
            "success",
        }

    def __str__(self) -> str:
        state = "valid" if self.valid else f"{self.validation_status} ({self.validation_issue_count} issues)"
        return f"{self.document_iri}: {self.object_count} objects, " f"{self.triple_count} triples, {state}"


@dataclass(frozen=True)
class FoundObject:
    """One object a registry search returned."""

    iri: str
    sbol_class: str
    display_id: str | None
    name: str | None
    description: str | None
    roles: tuple[str, ...]

    @property
    def role(self) -> Role | None:
        """The GC-AI role this object's Sequence Ontology term maps to."""
        for candidate in self.roles:
            mapped = SO_TO_ROLE.get(term(candidate))
            if mapped is not None:
                return mapped
        return None


class SbolDb:
    """One SBOL DB registry.

    Wraps the official `sbol_db` client so that failures arrive as `GCAIError`
    and results in GC-AI's own shapes.
    """

    def __init__(
        self,
        url: str,
        *,
        user: str | None = None,
        password: str = "",
        operations_url: str | None = None,
        timeout: float = 60.0,
        transport: "httpx.BaseTransport | None" = None,
    ) -> None:
        client_class = _module().SbolDbClient
        self.url = url.rstrip("/")
        # Health and readiness are served on a separate loopback listener,
        # which defaults to port 9090, and not on the public one.
        self.operations_url = (operations_url or url).rstrip("/")
        self._timeout = timeout
        self._transport = transport
        self._client = client_class(self.url, user=user, password=password, timeout=timeout, transport=transport)

    def __enter__(self) -> "SbolDb":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @classmethod
    def from_env(cls, **kwargs: Any) -> "SbolDb":
        """Build a registry from SBOL_DB_URL, SBOL_DB_USER and SBOL_DB_PASSWORD."""
        url = os.environ.get("SBOL_DB_URL")
        if not url:
            raise GCAIError("set SBOL_DB_URL to the registry you want to use")
        return cls(
            url,
            user=os.environ.get("SBOL_DB_USER"),
            password=os.environ.get("SBOL_DB_PASSWORD", ""),
            operations_url=os.environ.get("SBOL_DB_OPERATIONS_URL"),
            **kwargs,
        )

    def healthy(self) -> bool:
        """Whether the registry answers.

        Health is served on a separate loopback listener, which defaults to
        port 9090, so give `operations_url` when it is not the same host and
        port as the registry itself.

        This asks for it directly rather than through the registry client,
        whose published release does not take an operations URL.
        """
        import httpx

        try:
            with httpx.Client(base_url=self.operations_url, timeout=self._timeout, transport=self._transport) as http:
                response = http.get("/healthz")
        except httpx.TransportError:
            return False
        return response.status_code == 200 and response.text.strip() == "ok"

    def publish(
        self,
        document: bytes | str,
        *,
        document_iri: str,
        name: str | None = None,
        description: str | None = None,
        namespace: str | None = None,
        overwrite: int = 0,
    ) -> PublishResult:
        """Import a generated document into the registry.

        `overwrite` decides what happens when `document_iri` is already there:
        0 fails, 1 replaces, 2 merges.
        """
        rdf = document.decode() if isinstance(document, bytes) else document
        with _as_gcai_error(f"could not publish {document_iri}"):
            report = self._client.create_graph(
                rdf,
                format=RDF_XML,
                document_iri=document_iri,
                name=name,
                description=description,
                namespace=namespace,
                overwrite=overwrite,
                version="sbol3",
            )
        return PublishResult(
            graph_id=str(report.graph_id),
            document_iri=document_iri,
            object_count=int(report.object_count),
            triple_count=int(report.triple_count),
            validation_status=str(report.validation_status),
            validation_issue_count=int(report.validation_issue_count),
        )

    def fetch(self, iri: str, *, version: str = "sbol3", format: str = RDF_XML, recursive: bool = True) -> bytes:
        """Read an object back out of the registry."""
        with _as_gcai_error(f"could not fetch {iri}"):
            text: str = self._client.export_rdf(iri, format=format, recursive=recursive, version=version)
        return text.encode()

    def to_sbol2(self, iri: str, *, format: str = RDF_XML) -> bytes:
        """The SBOL2 form of an object the registry holds.

        The registry serves the conversion.
        """
        return self.fetch(iri, version="sbol2", format=format)

    def search(self, text: str, *, sbol_class: str | None = "Component", limit: int = 25) -> list[FoundObject]:
        """Substring search over the registry's objects."""
        with _as_gcai_error(f"search for {text!r} failed"):
            found = self._client.search(text, object_type=sbol_class, limit=limit)
        return [
            FoundObject(
                iri=str(obj.iri),
                sbol_class=str(obj.sbol_class),
                display_id=obj.display_id,
                name=obj.name,
                description=obj.description,
                roles=tuple(str(role) for role in (obj.roles or ())),
            )
            for obj in found
        ]

    def delete(self, document_iri: str) -> None:
        """Remove a published document.

        This destroys the record the registry holds for that document.
        """
        with _as_gcai_error(f"could not delete {document_iri}"):
            self._client.delete_graph_by_document_iri(document_iri)


class _as_gcai_error:
    """Turn the registry client's errors into this package's."""

    def __init__(self, what: str) -> None:
        self._what = what

    def __enter__(self) -> "_as_gcai_error":
        return self

    def __exit__(self, kind: Any, value: Any, traceback: Any) -> "Literal[False]":
        if value is None:
            return False
        sbol_db = _module()
        if isinstance(value, sbol_db.SbolDbError):
            raise GCAIError(f"{self._what}: {value}") from value
        return False


def iter_roles(objects: list[FoundObject]) -> Iterator[tuple[FoundObject, Role]]:
    """The objects whose role GC-AI recognises, with that role."""
    for obj in objects:
        role = obj.role
        if role is not None:
            yield obj, role
