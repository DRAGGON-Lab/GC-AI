# gc-ai-client

A Python client for the [GC-AI](https://github.com/DRAGGON-Lab/GC-AI) service:
detect SBOL Visual glyphs in an image, assemble a design, and generate SBOL3,
GenBank and FASTA.

```python
from gcai import GCAIClient, Design, Part, Operon, Role

with GCAIClient("http://localhost:5001") as client:
    detection = client.detect("circuit.png")

    design = Design.from_detection(detection, name="MY_CIRCUIT",
                                   namespace="https://example.org/designs/")
    for part, name in zip(design.parts, ["BBa_R0010", "BBa_B0034"]):
        part.name = name
    client.fill_parts(design)

    design.operons.append(Operon(name="Operon 1", parts=list(design.parts)).chain())

    for issue in design.validate():
        print(issue)

    result = client.build(design)
    result.write("out", stem="my_circuit")
```

Two runnable scripts using it, from a diagram through to a registry, are in
[`../examples/`](../examples/).

## Install

```sh
pip install -e client              # the client and its CLI
pip install -e "client[db]"        # also storing designs in SBOL DB
pip install -e "client[mcp]"       # also the MCP server
```

## What it handles

`Design.to_payload()` produces what `POST /file/create` expects: the parent
component first, parts in 5'-to-3' order, instance numbers worked out for
parts that share a name, and operon and interaction members written as the
`{name}_{instance}` references the service reads. Parts are linked by object
identity, so two parts can share a name and still be told apart.

`design.validate()` reports invalid input before a request is sent. Names
that are not valid SBOL displayIds. Part URIs that do not end in a separator.
A participation role that does not belong to its interaction type. A species
URI with whitespace in it. Errors stop `build` unless you pass
`validate=False`; server validation always applies.

`build()` hides the file handoff. `POST /file/create` returns the path of a
second document in a response header and `POST /file/convert` wants that path,
so `build()` does both calls and hands back the bytes.

## Service behaviour that will catch you out

- **Readiness:** `health()` calls `/healthcheck/`, which returns 200 when the detector and database are usable and sanitized 503 otherwise. `/livez` checks only application liveness.

- **Send a namespace for reproducible identities.** Local validation requires an
  absolute namespace.
- **A registry part ignores what you send.** With `new=False` the description
  and sequence come from the service's bundled registry, and a name that is not
  in it fails the request. Use `new=True` to supply your own, in lower case.
- **Participation roles are enforced.** Invalid type/role combinations and
  unresolved participants fail with actionable HTTP 422 findings.
- **Functional species need no operon.** DNA, RNA, proteins and chemicals can
  participate in the functional system independently of the physical DNA assembly.
  An empty definition URI creates a typed local feature; a valid URI creates an
  externally defined feature.
- **Order means relative position.** Order emits `precedes`; Regulate remains a
  deprecated positional alias. Use typed interactions for functional regulation.
- **Generated files are deleted after 24 hours**, so a structural path is only
  good for that long.

## Storing designs in SBOL DB

`gcai.storage` is a few helpers over the [sbol-db](https://pypi.org/project/sbol-db/)
client. They carry the two facts about a GC-AI document that every call needs:
it is RDF/XML, and it is SBOL3. Needs the `db` extra.

```python
from sbol_db import SbolDbClient
from gcai.storage import publish, fetch, to_sbol2

with SbolDbClient("http://localhost:8888") as registry:
    report = publish(
        registry,
        result.sbol3,
        document_iri="https://example.org/designs/my-circuit",
        name="My circuit",
        description="built from a photo of a whiteboard",
    )
    print(report.object_count, report.triple_count, report.validation_status)

    sbol2 = to_sbol2(registry, "https://example.org/designs/my-circuit")
```

`publish` POSTs the document and returns sbol-db's `ImportReport`: the graph
id, the object and triple counts, and the registry's validation result. The
registry validates every import.

`overwrite` says what a second publish to the same `document_iri` does. 0
fails, 1 replaces, 2 merges.

`fetch` pulls an object and everything it references back out as SBOL3.
`to_sbol2` pulls the SBOL2 version; the registry does that conversion.

Anything else is a direct call on `SbolDbClient`: `search`, `sequence_search`,
`sparql`, `delete_graph_by_document_iri`, `healthz`. `storage.client(url)` is
the same constructor with a clearer error when the `db` extra is missing.

Health is on a different port. The registry serves `/healthz` on a loopback
operations listener, 9090 by default, not on the registry's own address.

## Command line

```sh
gcai health
gcai detect circuit.png --json
gcai publish design.xml --iri https://example.org/designs/mine --name Mine --yes
gcai fetch https://example.org/designs/mine -o mine-sbol2.xml --sbol2
gcai parts Promoter --grep R0010
gcai part BBa_R0010
gcai check "docs/examples/YES GATE/request.json"
gcai build "docs/examples/YES GATE/request.json" -o out
```

`--url` or `GCAI_URL` points at a service other than `http://localhost:5001`.
`--registry` or `SBOL_DB_URL` points at a registry; `publish` also needs
`--yes`, because it writes somewhere other people can read.

## MCP server

`gcai-mcp` serves the GC-AI service over MCP, with one tool. Needs the `mcp`
extra.

```sh
claude mcp add --transport stdio gc-ai --scope project -- \
  uv run --with "gc-ai-client[mcp]" gcai-mcp --url http://localhost:5001 --allow-root .
```

The tool is `design_from_image`, and one call gives you a document. It returns
the SBOL3, the glyphs the detector found left to right, and the image with the
detections drawn on it.

The image arrives one of two ways, and exactly one has to be given.
`image_path` when the server shares a filesystem with the caller, which is the
stdio case. `image_base64` when it does not.

A diagram says what the parts are and what order they come in. It does not say
which registry parts they are, so each part is named after its role, like
`promoter_1`, and carries no sequence: the document records the role and the
place in the order. No parent sequence or coordinates are invented until every part has bases.

Pass `part_names`, one per part in 5' to 3' order, to bind them to parts the
service knows, which fills in the sequences. Leave an entry empty to name that
one after its role instead.

Detection misses parts. On a photograph of a hand-drawn circuit here it finds
2 glyphs for an 8-part design, so check the annotated image against the glyph
list.

`output_dir` writes the documents there and returns the paths. Without it the
SBOL3 comes back in the result, which is 11 KB for two parts and 56 to 121 KB
for the designs in `docs/examples`. `--allow-root` bounds which directories the
server reads images from and writes files to, and defaults to the working
directory.

`--http` serves streamable HTTP instead of stdio. On a non-loopback address it
requires `--allowed-host`, without which every request is rejected.

## Tests

Run them from `client/`, so pytest reads the configuration in its
`pyproject.toml`:

```sh
cd client
uv run --extra dev pytest        # unit tests, no services needed

# Against a running GC-AI service, and an SBOL DB registry for the storage tests.
GCAI_URL=http://localhost:5001 SBOL_DB_URL=http://localhost:8888 \
  uv run --extra dev --extra db pytest -m integration
```

Hosted access uses TLS Basic authentication:

```python
with GCAIClient("https://gcai.example/api", auth=(username, password)) as client:
    created = client.create(design)
    converted = client.convert(created.structural_handle)
```

CLI and MCP read `GCAI_USERNAME` and `GCAI_PASSWORD_FILE` (a private file containing the password). Do not put credentials in URLs, arguments or build variables. Generated results carry `structural_handle`; server filesystem paths are no longer accepted. Handles expire after 24 hours. Incomplete conversion archives raise `GCAIError`. SDK and MCP limit image reads to 10 MiB; hosted operators must coordinate any changed limits across clients and server.
