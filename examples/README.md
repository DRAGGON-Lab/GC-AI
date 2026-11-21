# Examples

Two scripts, run from the repo root against a running stack.

| File | What it does |
| --- | --- |
| `image_to_sbol.py` | Reads a diagram and writes the SBOL3 for the design in it |
| `publish_to_registry.py` | Puts a document from the first script into an SBOL DB registry |
| `quickstart.ipynb` | Both of them with the detections on screen |

`docs/examples/` holds captured output — the photos, the detections, the
request bodies and the documents. These are the code that produces that kind of
output.

## Before you start

Bring the stack up with
[GC-AI-environment](https://github.com/DRAGGON-Lab/GC-AI-environment), then:

```sh
cd client && uv sync --extra dev --extra db && cd ..
```

Every command below runs from the repo root. `--project client` tells `uv`
where the package is.

## A diagram to SBOL3

```sh
uv run --project client python examples/image_to_sbol.py \
  "docs/examples/YES GATE/YES-GATE-CIRCUIT.png" \
  --name YesGate -o /tmp/yes-gate
```

```
2 glyphs in YES-GATE-CIRCUIT.png
   1. promoter               Promoter               [55, 164, 110, 234]
   2. ribosome-entry-site    RBS                    [115, 186, 163, 230]
wrote /tmp/yes-gate/YesGate.xml
built YesGate from 2 parts: promoter_1, rbs_1
2 of them carry no sequence, so the document records their role and their place
in the order, with no assembled parent sequence or coordinates.
GenBank and FASTA need bases, so only the SBOL3 was written.
```

Two things to read off that.

The circuit in that photograph has eight parts and the detector found two. It
is a photograph of a pen-on-paper drawing, which is the hardest case for the
model; `docs/examples/README.md` has the count for each committed example.
Passing `--annotated out.png` writes the image with the boxes drawn on it,
which is the quickest way to see what was missed.

A diagram says what the parts are and what order they come in. It does not say
which registry parts they are, so each part is named after its role and carries
no sequence. The document records the role and the position, which is what was
drawn.

## Naming the parts

```sh
uv run --project client python examples/image_to_sbol.py \
  "docs/examples/YES GATE/YES-GATE-CIRCUIT.png" \
  --name YesGate --names BBa_R0010,BBa_B0034 -o /tmp/yes-gate
```

One name per part in 5' to 3' order binds them to parts the service's registry
holds, which brings their sequences with them, and GenBank and FASTA follow.
Leave an entry empty — `--names BBa_R0010,,BBa_C0012` — to name that one after
its role instead, so you can name the parts you recognise and leave the rest.

## Into a registry

```sh
uv run --project client python examples/publish_to_registry.py \
  /tmp/yes-gate/YesGate.xml --design YesGate \
  --iri https://gc-ai.example/designs/yes-gate \
  --registry http://127.0.0.1:8899 --yes
```

```
published YesGate.xml as https://gc-ai.example/designs/yes-gate
  19 objects, 137 triples
  validation failed, 2 issues
  the import is kept either way; the registry records the issues against the graph
read http://sbols.org/unspecified_namespace/YesGate back
  3589 bytes of SBOL3, naming the v3 vocabulary: True
  6826 bytes of SBOL2, which does not: True
```

`--iri` names the graph the import becomes. The design is at
`<namespace>/<design>`, which is how the service builds it, so reading it back
needs nothing written down.

`--yes` is required. This is the one example that writes to a service other
people can read.

## The notebook

[`quickstart.ipynb`](quickstart.ipynb) calls the same two functions and displays
the annotated image, which is the quickest way to see which glyphs were found
and which were missed. Its outputs are committed, so it reads on GitHub without
being run. To run it:

```sh
cd client
uv run --with jupyter --with nbconvert \
  jupyter nbconvert --to notebook --execute --inplace ../examples/quickstart.ipynb
```

## Driving it from an agent

`gcai-mcp` does the first script's job as a single MCP tool call. See the MCP
section of [`../client/README.md`](../client/README.md).

## Tests

`client/tests/test_examples.py` covers both scripts against a mock service, and
`client/tests/test_examples_integration.py` runs them against a real one:

```sh
cd client
uv run pytest tests/test_examples.py
GCAI_URL=http://localhost:5001 SBOL_DB_URL=http://127.0.0.1:8899 \
  uv run pytest tests/test_examples_integration.py -m integration
```
