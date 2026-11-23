"""An MCP server over the GC-AI service.

One tool, one call. It takes a diagram, as a path when the caller shares a
filesystem with the server and as base64 when it does not, and gives back the
SBOL3 for the design in it.

A diagram says what the parts are and what order they come in. It does not say
which registry parts they are, so by default each part is named after its role
and carries no sequence. Pass part_names to bind them to parts the service
knows, which fills in the sequences.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Callable

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from gcai.client import MAX_IMAGE_BYTES, GCAIClient, read_image
from gcai.design import Design, Operon, name_parts
from gcai.errors import GCAIConnectionError, GCAIError, GCAIResponseError
from gcai.mcp.schemas import Glyph, Result
from gcai.validation import normalize_namespace

logger = logging.getLogger("gcai.mcp")

MAX_BASE64 = ((MAX_IMAGE_BYTES + 2) // 3) * 4

INSTRUCTIONS = """\
GC-AI reads a picture of an SBOL Visual diagram and writes the SBOL3 for it.

design_from_image is the only tool, and one call gives you a document. A
diagram says what the parts are and what order they come in, so the document
records the roles and the order, with each part named after its role and
carrying no sequence.

Pass part_names, one name per part in 5' to 3' order, to bind them to parts
the service knows and fill in the sequences. Detection misses parts, so check
the annotated image that comes back against the glyph list.
"""


@dataclass
class App:
    service: GCAIClient
    allowed_roots: tuple[Path, ...]


def build_server(
    *,
    base_url: str | None = None,
    allowed_roots: tuple[Path, ...] = (),
    service_factory: Callable[[], GCAIClient] | None = None,
) -> MCPServer:
    """The server, with its dependencies supplied rather than discovered."""
    roots = allowed_roots or (Path.cwd().resolve(),)

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[App]:
        service = service_factory() if service_factory else GCAIClient(base_url)
        try:
            yield App(service=service, allowed_roots=roots)
        finally:
            service.close()

    mcp = MCPServer("gc-ai", instructions=INSTRUCTIONS, lifespan=lifespan, version="0.2.0")
    _register(mcp)
    return mcp


def _in_roots(raw: str, app: App, *, must_be_file: bool) -> Path:
    path = Path(raw).expanduser().resolve()
    if not any(path.is_relative_to(root) for root in app.allowed_roots):
        allowed = ", ".join(str(root) for root in app.allowed_roots)
        raise ToolError(f"{raw!r} is outside the directories this server may touch ({allowed})")
    if must_be_file and not path.is_file():
        raise ToolError(f"{raw!r} is not a file")
    return path


def _image_bytes(app: App, image_path: str | None, image_base64: str | None) -> bytes:
    if bool(image_path) == bool(image_base64):
        raise ToolError("give exactly one of image_path or image_base64")
    if image_path:
        try:
            return read_image(_in_roots(image_path, app, must_be_file=True))
        except GCAIError as exc:
            raise ToolError(str(exc)) from exc
    if len(image_base64 or "") > MAX_BASE64:
        raise ToolError("that image is too large to send inline; write it to disk and pass image_path")
    try:
        data = base64.b64decode(image_base64 or "", validate=True)
        if len(data) > MAX_IMAGE_BYTES:
            raise ToolError("image exceeds the 10 MiB limit")
        return data
    except Exception as exc:
        raise ToolError(f"image_base64 is not valid base64: {exc}") from exc


def _fail(exc: Exception) -> ToolError:
    if isinstance(exc, GCAIConnectionError):
        return ToolError(f"{exc}. The GC-AI service is not answering.")
    if isinstance(exc, GCAIResponseError):
        return ToolError(f"the GC-AI service returned {exc.status_code}: {exc.message}")
    if isinstance(exc, GCAIError):
        return ToolError(str(exc))
    logger.error("Unhandled tool failure (%s)", type(exc).__name__)
    return ToolError(f"internal error: {type(exc).__name__}")


def _register(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Design from a diagram",
        annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=False, open_world_hint=False),
    )
    def design_from_image(
        ctx: Context[App],
        name: Annotated[str, Field(description="Name for the design. Letters, digits and _ only.")],
        namespace: Annotated[str, Field(description="An http(s) URL the design lives under")],
        image_path: Annotated[
            str | None, Field(description="Path to the image, when the server shares your filesystem")
        ] = None,
        image_base64: Annotated[
            str | None, Field(description="The image itself, base64 encoded, when it does not")
        ] = None,
        part_names: Annotated[
            list[str] | None,
            Field(
                description="One registry part name per part, 5' to 3'. Leave an entry empty to "
                "name that one after its role instead. Omit it entirely and every part is."
            ),
        ] = None,
        description: str = "",
        output_dir: Annotated[
            str | None, Field(description="Write the documents here instead of returning them")
        ] = None,
        genbank: bool = False,
        fasta: bool = False,
    ) -> Annotated[CallToolResult, Result]:
        """Read a diagram and write the SBOL3 for the design in it.

        Returns the document, the glyphs that were found left to right, and
        the image with the detections drawn on it.

        A diagram says what the parts are and what order they come in, so by
        default each part is named after its role and carries no sequence.
        Pass part_names to bind them to parts the service knows, which fills in
        the sequences; every name has to be one the service has.

        Detection misses parts. Check the annotated image against the glyph
        list, and call again with the parts it missed if you need them.

        Without output_dir the SBOL3 comes back in the result, which is large.
        """
        try:
            namespace = normalize_namespace(namespace)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        app = ctx.request_context.lifespan_context
        data = _image_bytes(app, image_path, image_base64)

        try:
            detection = app.service.detect(data)
        except Exception as exc:
            raise _fail(exc) from exc

        ordered = detection.ordered()
        glyphs = [
            Glyph(
                index=index,
                glyph_class=glyph.glyph_class.value,
                role=glyph.role.value if glyph.role else None,
                box=glyph.box.as_list(),
            )
            for index, glyph in enumerate(ordered)
        ]
        roles = [glyph.role for glyph in ordered if glyph.role is not None]
        unmapped = sorted({g.glyph_class.value for g in ordered if g.role is None})
        picture = (
            [Image(data=detection.annotated_png, format="png").to_image_content()] if detection.annotated_png else []
        )

        def answer(result: Result, summary: str) -> CallToolResult:
            return CallToolResult(
                content=[*picture, TextContent(type="text", text=summary)],
                structured_content=result.model_dump(),
            )

        if not roles:
            return answer(
                Result(
                    detected=glyphs,
                    unmapped=unmapped,
                    problems=["no glyphs with a known role were found in that image"],
                    next_step="check the image is an SBOL Visual diagram",
                ),
                "nothing to build from",
            )

        if part_names and len(part_names) != len(roles):
            return answer(
                Result(
                    detected=glyphs,
                    unmapped=unmapped,
                    problems=[
                        f"{len(part_names)} names given for {len(roles)} detected parts. Give one "
                        "per part in 5' to 3' order, or leave part_names out and every part is "
                        "named after its role."
                    ],
                    next_step="call again with one name per part",
                ),
                "the number of names does not match the number of parts",
            )

        design = Design.from_detection(detection, name=name, namespace=namespace, description=description)
        name_parts(design, part_names)
        design.operons.append(Operon(name=f"{name}_operon", parts=list(design.parts)).chain())

        errors = [issue for issue in design.validate() if issue.severity == "error"]
        if errors:
            return answer(
                Result(
                    detected=glyphs,
                    unmapped=unmapped,
                    problems=[f"{issue.path}: {issue.message}" for issue in errors],
                    next_step="fix those and call again",
                ),
                "the design is not valid",
            )

        # GenBank and FASTA require a fully sequenced DNA assembly.
        bases = all(part.sequence or not part.new for part in design.parts)
        try:
            built = app.service.build(design, genbank=genbank and bases, fasta=fasta and bases, validate=False)
        except Exception as exc:
            raise _fail(exc) from exc

        result = Result(
            detected=glyphs,
            unmapped=unmapped,
            built=True,
            parts=[part.name for part in design.parts],
            named_from_registry=[part.name for part in design.parts if not part.new],
        )
        if any(part.new for part in design.parts):
            result.notes.append(
                "parts named after their role carry no sequence, so the document records their "
                "role and their place in the order. No parent sequence or coordinates are invented. "
                "Pass part_names to bind them to registry parts."
            )
        if (genbank or fasta) and not bases:
            result.notes.append(
                "GenBank and FASTA were not produced: they need every part to carry bases, and "
                "parts named after their role carry none."
            )

        if output_dir:
            target = _in_roots(output_dir, app, must_be_file=False)
            target.mkdir(parents=True, exist_ok=True)
            result.written = [str(path) for path in built.write(target, name)]
            result.next_step = "the documents are on disk"
            return answer(result, f"built {name}: {', '.join(result.written)}")

        result.sbol3 = built.sbol3.decode()
        result.genbank = built.genbank.decode() if built.genbank else None
        result.fasta = built.fasta.decode() if built.fasta else None
        result.next_step = "the SBOL3 is in this result"
        return answer(result, f"built {name} from {len(design.parts)} parts")


__all__ = ["App", "build_server"]
