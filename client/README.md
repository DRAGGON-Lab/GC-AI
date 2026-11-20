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

`design.validate()` catches what the service will not tell you about. Names
that are not valid SBOL displayIds. Part URIs that do not end in a separator.
A participation role that does not belong to its interaction type. A species
URI with whitespace in it. Errors stop `build` unless you pass
`validate=False`.

`build()` hides the file handoff. `POST /file/create` returns the path of a
second document in a response header and `POST /file/convert` wants that path,
so `build()` does both calls and hands back the bytes.

## Service behaviour that will catch you out

- **`/healthcheck/` always answers 500.** It closes its database cursor without
  reading the result of its test query. `client.health()` calls
  `GET /component/names` instead, which proves the application is serving, the
  model has loaded and the database answers.
- **Send a namespace on every request.** The service applies it process-wide, so
  a request without one is built under whatever namespace the previous request
  set. `validate` reports a missing namespace as an error.
- **A registry part ignores what you send.** With `new=False` the description
  and sequence come from the service's bundled registry, and a name that is not
  in it fails the request. Use `new=True` to supply your own, in lower case.
- **Participation roles are not enforced.** The service accepts any of the ten
  on any interaction type and writes the matching term, so a mismatch produces a
  document that is structurally valid and semantically wrong.
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

The tool is `design_from_image`. Call it with just an image and it returns the
glyphs the detector found, left to right, with the role of each, and the image
with the detections drawn on it. Call it again with `part_names` and it builds
the SBOL3.

The image arrives one of two ways. `image_path` when the server shares a
filesystem with the caller, which is the stdio case. `image_base64` when it
does not. Give exactly one.

The two calls are separate because detection finds roles, not names, and it
misses parts. A photograph of a hand-drawn circuit here gives 2 glyphs for an
8-part design. Whoever is driving has to look at the picture and decide what
the design really is.

`output_dir` writes the documents there and returns the paths. Without it the
SBOL3 comes back in the result, which is tens of thousands of tokens for a
real design. `--allow-root` bounds which directories the server will read
images from or write files to; it defaults to the working directory.

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
