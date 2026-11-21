"""An HTTP client for the GC-AI service."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Any, Mapping

import httpx

from gcai.constants import InteractionType, ParticipationRole, Role
from gcai.design import Design
from gcai.errors import DesignValidationError, GCAIConnectionError, GCAIError, GCAIResponseError
from gcai.models import BuildResult, CreateResult, Detection, PartDetails

DEFAULT_URL = "http://localhost:5001"
USER_AGENT = "gcai-client/0.1.0"


class GCAIClient:
    """Calls the GC-AI service.

    The service has no authentication. Every method raises `GCAIResponseError`
    when the service answers with a failure, and `GCAIConnectionError` when it
    cannot be reached.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("GCAI_URL") or DEFAULT_URL).rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )

    def __enter__(self) -> "GCAIClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------- transport

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise GCAIConnectionError(f"cannot reach the GC-AI service at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise _as_error(response)
        return response

    # ---------------------------------------------------------------- health

    def health(self) -> bool:
        """Whether the service is usable.

        This calls `GET /component/names`, not `/healthcheck/`: that endpoint
        closes its database cursor without reading the result of its test
        query, so it answers 500 whatever the state of the service. A
        successful part lookup proves the application is serving, the detection
        model has loaded, and the database answers.
        """
        try:
            self.part_names(Role.PROMOTER)
        except GCAIResponseError:
            return False
        return True

    # ------------------------------------------------------------- inference

    def detect(self, image: bytes | str | os.PathLike[str], *, filename: str = "image.png") -> Detection:
        """Detect glyphs in an image."""
        if isinstance(image, (str, os.PathLike)):
            path = Path(image)
            data, filename = path.read_bytes(), path.name
        else:
            data = image
        response = self._request("POST", "/inference/", files={"image": (filename, data, "image/png")})
        return Detection.from_response(response.json())

    # ------------------------------------------------------------ components

    def part_names(self, role: Role) -> list[str]:
        """Every registry part name for a role.

        The service does not paginate, and some roles hold several thousand
        parts.
        """
        response = self._request("GET", "/component/names", params={"role": Role(role).value})
        return list(response.json())

    def part_details(self, name: str, role: Role | None = None) -> PartDetails:
        """One registry part."""
        params: dict[str, str] = {"component_name": name}
        if role is not None:
            params["role"] = Role(role).value
        return PartDetails.from_response(self._request("GET", "/component/details", params=params).json())

    def participations(self, interaction_type: InteractionType) -> list[ParticipationRole]:
        """The participation roles an interaction type expects.

        The service and `Design.validate` enforce these combinations.
        """
        response = self._request(
            "GET", "/component/interactions", params={"interaction_type": InteractionType(interaction_type).value}
        )
        return [ParticipationRole(role) for role in response.json()]

    def fill_parts(self, design: Design) -> None:
        """Fill in description and sequence for every registry part in `design`."""
        for part in design.parts:
            if part.new or not part.name:
                continue
            details = self.part_details(part.name, part.role)
            part.description = details.description or part.description
            part.sequence = (details.sequence or part.sequence).lower()

    # ----------------------------------------------------------------- files

    def create(self, design: Design | Mapping[str, Any], *, validate: bool = True) -> CreateResult:
        """Generate SBOL3 documents for a design.

        A `Mapping` is sent as it is, so a request captured from the web
        interface can be replayed unchanged.
        """
        payload = _payload(design, validate=validate)
        response = self._request("POST", "/file/create", json=payload)
        structural = response.headers.get("X-GCAI-Structural-Handle")
        if not structural:
            raise GCAIError(
                "the service did not return a X-GCAI-Structural-Handle header, so the structural "
                "document cannot be converted"
            )
        return CreateResult(sbol3=response.content, structural_handle=structural)

    def convert(self, structural_handle: str, *, genbank: bool = True, fasta: bool = True) -> dict[str, bytes]:
        """Convert a generated document, keyed by format.

        `structural_handle` is the `X-GCAI-Structural-Handle` header from `create`.
        The service deletes the file 24 hours after writing it.
        """
        response = self._request(
            "POST",
            "/file/convert",
            json={"structural_handle": structural_handle, "genbank": genbank, "fasta": fasta},
        )
        out: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for member in archive.namelist():
                if member.endswith(".gb"):
                    out["genbank"] = archive.read(member)
                elif member.endswith(".fasta"):
                    out["fasta"] = archive.read(member)
        return out

    def build(
        self,
        design: Design | Mapping[str, Any],
        *,
        genbank: bool = True,
        fasta: bool = True,
        validate: bool = True,
    ) -> BuildResult:
        """Generate a design and convert it in one call.

        The SBOL3 returned is the full document; the conversions are of the
        structural one, which is what the web interface offers.
        """
        created = self.create(design, validate=validate)
        converted: dict[str, bytes] = {}
        if genbank or fasta:
            converted = self.convert(created.structural_handle, genbank=genbank, fasta=fasta)
        return BuildResult(
            sbol3=created.sbol3,
            structural_handle=created.structural_handle,
            genbank=converted.get("genbank"),
            fasta=converted.get("fasta"),
        )


def _payload(design: Design | Mapping[str, Any], *, validate: bool) -> dict[str, Any]:
    if isinstance(design, Design):
        if validate:
            issues = design.validate()
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                raise DesignValidationError(errors)
        return design.to_payload()
    return dict(design)


def _as_error(response: httpx.Response) -> GCAIResponseError:
    """Turn a failed response into an error, reading the service's envelope."""
    text = response.text
    message = text
    code = None
    issues = []
    try:
        body = response.json()
    except ValueError:
        pass
    else:
        if isinstance(body, dict):
            message = str(body.get("error") or text)
            code = body.get("code") if isinstance(body.get("code"), str) else None
            if isinstance(body.get("issues"), list):
                issues = [issue for issue in body["issues"] if isinstance(issue, dict)]
    return GCAIResponseError(status_code=response.status_code, message=message, body=text, code=code, issues=issues)
