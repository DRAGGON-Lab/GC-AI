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
pip install -e "client[sbol]"      # also the SBOL libraries, for validating output
```

## What it does for you

**Builds the request.** `Design.to_payload()` produces exactly what
`POST /file/create` expects: the parent component first, parts in 5'-to-3'
order, instance numbers worked out for parts that share a name, and operon and
interaction members written as the `{name}_{instance}` references the service
reads. Parts are linked by object identity, so two parts may share a name and
still be told apart.

**Checks the design first.** `design.validate()` returns the problems the
service will not tell you about: names that are not valid SBOL displayIds, a
part URI that does not end in a separator, a participation role that does not
belong to its interaction type, a species URI with whitespace in it. Errors
stop `build` unless you pass `validate=False`.

**Hides the file handoff.** `POST /file/create` returns the path of a second
document in a response header, and `POST /file/convert` takes that path.
`build()` does both and hands back the bytes.

## Things about the service worth knowing

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

## Command line

```sh
gcai health
gcai detect circuit.png --json
gcai parts Promoter --grep R0010
gcai part BBa_R0010
gcai check "docs/examples/YES GATE/request.json"
gcai build "docs/examples/YES GATE/request.json" -o out
```

`--url` or `GCAI_URL` points at a service other than `http://localhost:5001`.

## Tests

Run them from `client/`, so pytest reads the configuration in its
`pyproject.toml`:

```sh
cd client
uv run --extra dev pytest                       # unit tests, no service needed

# Against a running service. The sbol extra is needed as well: without it the
# tests that compare generated documents skip instead of running.
GCAI_URL=http://localhost:5001 uv run --extra dev --extra sbol pytest -m integration
```
