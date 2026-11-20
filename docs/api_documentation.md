# GC-AI API Documentation

The GC-AI API detects SBOL Visual glyphs in an image and builds SBOL3 documents
from the detected parts, with optional conversion to GenBank and FASTA.

The machine-readable contract is [`openapi.yaml`](openapi.yaml), which is the
authoritative reference for schemas, enumerated values and error codes. This page
is the guide to using it.

- [Base URL and conventions](#base-url-and-conventions)
- [Endpoints](#endpoints)
  - [Health](#health)
  - [Inference](#inference)
  - [Components](#components)
  - [Files](#files)
- [Walkthrough: image to GenBank](#walkthrough-image-to-genbank)
- [Building a design](#building-a-design)
- [Errors](#errors)

---

## Base URL and conventions

In the [Docker environment](https://github.com/DRAGGON-Lab/GC-AI-environment) the
API is served at `http://localhost:5001`.

Every path carries the prefix of the blueprint that serves it: `/healthcheck`,
`/inference`, `/component` or `/file`. The trailing slash on `/healthcheck/` and
`/inference/` is part of the path.

There is no authentication. Every failed request, at every status code, returns
the same body shape:

```json
{ "status_code": 404, "error": "Component not found" }
```

Responses are not paginated.

---

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthcheck/` | Model and database status |
| `POST` | `/inference/` | Detect glyphs in an image |
| `GET` | `/component/names` | List registry part names for a role |
| `GET` | `/component/interactions` | List participation roles for an interaction type |
| `GET` | `/component/details` | Get one registry part |
| `POST` | `/file/create` | Generate SBOL3 documents for a design |
| `POST` | `/file/convert` | Convert a generated document to GenBank and FASTA |

### Health

#### `GET /healthcheck/`

**This endpoint always fails.** It is built to report whether the detection model
is loaded and the parts database answers, but it runs its test query and closes
the database cursor without reading the result, so the MySQL connector raises
`Unread result found`:

```sh
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5001/healthcheck/
```

```
500
{"error":"Healthcheck failed: Unread result found","status_code":500}
```

It answers `500` whatever the state of the service, so it tells you nothing.

To test whether the service is usable, call `GET /component/names?role=Promoter`.
That succeeds only when the application is serving, the detection model has
loaded (it loads at import, so the application does not serve without it), and
the parts database answers queries.

### Inference

#### `POST /inference/`

Runs the detection model over an uploaded image.

```sh
curl -s -X POST http://localhost:5001/inference/ \
  -F "image=@docs/examples/YES GATE/YES-GATE-CIRCUIT.png"
```

```json
{
  "status": "success",
  "result_image": "iVBORw0KGgoAAAANSUhEUg...",
  "draw_boxes": [[112, 240, 198, 300], [205, 232, 286, 300]],
  "pred_classes": ["promoter", "ribosome-entry-site"],
  "has_predictions": true
}
```

Things worth knowing:

- `draw_boxes` and `pred_classes` are parallel arrays **in the model's order,
  which is not left to right**. To recover the order the parts appear in along
  the backbone, sort by the first element of each box (`x_min`).
- `result_image` is the input image as a base64 PNG with a labelled box drawn
  around each detection. It is present whether or not anything was found.
- Detections are filtered at a fixed confidence threshold of 0.7, and
  overlapping detections above an IoU of 0.3 are reduced to the highest-scoring
  one. Neither is configurable, and confidence scores are not returned.
- An image with no recognised glyphs is still a `200`, with `has_predictions`
  false, both arrays empty, and a `message` field.

The classes the model can emit are `aptamer`, `cds`, `cds-arrow`,
`engineered-region`, `inert-dna-spacer`, `ncrna`, `operator`,
`origin-of-replication`, `origin-of-transfer`, `polyA`, `primer-binding-site`,
`promoter`, `ribosome-entry-site` and `terminator`. Note that `cds` and
`cds-arrow` are separate classes that both mean a coding sequence.

### Components

These endpoints read the bundled snapshot of the iGEM parts registry held in the
application's MySQL database.

#### `GET /component/names`

```sh
curl -s "http://localhost:5001/component/names?role=Promoter"
```

```json
["BBa_R0010", "BBa_J23100", "BBa_R0040"]
```

`role` is required. The searchable roles are the fourteen listed under
[Building a design](#building-a-design) — all of `ComponentRole` except `mRNA`,
which no registry part type maps to.

The result is unpaginated, and large for common roles: CDS and
Engineered-Region each return several thousand names.

#### `GET /component/interactions`

```sh
curl -s "http://localhost:5001/component/interactions?interaction_type=Inhibition"
```

```json
["Inhibitor", "Inhibited"]
```

These are the keys to use in `participants` for an interaction of that type.

**The answer is advisory.** `POST /file/create` checks a participation role
against the full set of ten roles, not against the roles valid for the
interaction type, so it will accept `Stimulator` on an `Inhibition` interaction
and write the stimulator SBO term into the document. Use this endpoint to build a
correct design; the service will not reject an incorrect one.

#### `GET /component/details`

```sh
curl -s "http://localhost:5001/component/details?component_name=BBa_R0010&role=Promoter"
```

```json
{
  "identifier": "BBa_R0010",
  "name": "BBa_R0010",
  "description": "promoter (lacI regulated)",
  "role": "Promoter",
  "sequence": "caatacgcaaaccgcctctccccgcgcgttggccgattcatta...",
  "sequence_length": 200
}
```

`role` is echoed back unchanged and is not used to look the part up, so passing
a role that does not match the part has no effect on the result. An unknown part
name is a `404`.

### Files

#### `POST /file/create`

Builds two SBOL3 documents from a design:

- the **full** document, with the structural parts and, when the design has at
  least one operon, a functional system holding the operons, interactions and
  external species. This is returned as the response body.
- the **structural** document, with only the parts and their order. This one is
  not returned; its path on the server is in the `file_path_structural` response
  header, and that path is what `POST /file/convert` takes.

```sh
curl -s -X POST http://localhost:5001/file/create \
  -H 'Content-Type: application/json' \
  --data @request.json \
  -D headers.txt -o design.xml

grep -i file_path_structural headers.txt
```

```
file_path_structural: /app/app/files_generated/structural_sbol3_1a2b3c4d.xml
```

Both documents are written into the server's own storage and **deleted after 24
hours**, so a structural path is only usable within that window.

The request body is described under [Building a design](#building-a-design), and
in full in `openapi.yaml`.

#### `POST /file/convert`

Converts a document the service generated earlier into GenBank and/or FASTA, and
returns them together in a ZIP.

```sh
curl -s -X POST http://localhost:5001/file/convert \
  -H 'Content-Type: application/json' \
  -d '{"file_path": "/app/app/files_generated/structural_sbol3_1a2b3c4d.xml",
       "genbank": true, "fasta": true}' \
  -o converted.zip

unzip -l converted.zip
```

The document is identified **by its path on the server**. This endpoint reads the
file from the server's filesystem; it does not accept an uploaded document, so
only documents this service generated can be converted.

ZIP members are named after the source file with the format appended, for example
`structural_sbol3_1a2b3c4d_genbank.gb` and
`structural_sbol3_1a2b3c4d_fasta.fasta`.

GenBank conversion uses the online SBOL validator, so the service needs outbound
internet access for it. FASTA conversion is local. Requesting neither format
returns an empty ZIP rather than an error.

---

## Walkthrough: image to GenBank

The three calls in sequence, using the YES gate example from this repository.

**1. Confirm the service is ready.**

```sh
curl -fsS http://localhost:5001/healthcheck/
```

**2. Detect the glyphs.**

```sh
curl -fsS -X POST http://localhost:5001/inference/ \
  -F "image=@docs/examples/YES GATE/YES-GATE-CIRCUIT.png" \
  -o detection.json

python3 - <<'PY'
import json
d = json.load(open("detection.json"))
parts = sorted(zip(d["pred_classes"], d["draw_boxes"]), key=lambda p: p[1][0])
for cls, box in parts:
    print(f"{cls:22} x={box[0]}")
PY
```

Sorting by `x_min` gives the glyphs in 5'-to-3' order, which is the order the
parts go into the design.

**3. Build the design and generate SBOL3.**

Each detected glyph becomes a part, and a part needs a name from the registry.
`docs/examples/YES GATE/request.json` is a complete, working body for this image;
use it directly, or build your own as described below.

```sh
curl -fsS -X POST http://localhost:5001/file/create \
  -H 'Content-Type: application/json' \
  --data @"docs/examples/YES GATE/request.json" \
  -D headers.txt -o design.xml

STRUCTURAL=$(grep -i '^file_path_structural:' headers.txt | cut -d' ' -f2 | tr -d '\r')
echo "structural document: $STRUCTURAL"
```

**4. Convert to GenBank and FASTA.**

```sh
curl -fsS -X POST http://localhost:5001/file/convert \
  -H 'Content-Type: application/json' \
  -d "{\"file_path\": \"$STRUCTURAL\", \"genbank\": true, \"fasta\": true}" \
  -o converted.zip

unzip -o converted.zip
```

**5. Validate what you got.** The service reports whether it could *write* a
document, not whether that document is valid, and it does not check a design
against the rules above beyond what it needs to build the file. Validate the
result yourself:

```sh
python3 -c "
import sbol3
doc = sbol3.Document()
doc.read('design.xml')
report = doc.validate()
print(f'{len(report.errors)} errors, {len(report.warnings)} warnings')
for issue in report: print(' ', issue)
"
```

---

## Building a design

A `POST /file/create` body has four arrays and a namespace:

```json
{
  "namespace": "https://example.org/designs/",
  "components": [],
  "expressions": [],
  "interactions": [],
  "eds": []
}
```

### `components`

The first entry is the design itself and becomes the parent component; the rest
are its parts **in 5'-to-3' order**.

```json
{
  "id": "component-principal",
  "name": "YES_GATE",
  "identifier": "YES_GATE",
  "role": "Engineered-Region",
  "uri": "http://parts.igem.org/",
  "new": true,
  "description": "YES gate circuit"
}
```

```json
{
  "id": "4d1f0c9e-...",
  "name": "BBa_R0010",
  "identifier": "BBa_R0010",
  "role": "Promoter",
  "uri": "http://parts.igem.org/",
  "new": false,
  "description": "",
  "sequence": "",
  "sequence_length": ""
}
```

Rules that matter:

- **`name` becomes an SBOL `displayId`**, so it has to match
  `^[A-Za-z_][A-Za-z0-9_]*$`. A name with a space or a hyphen fails.
- **`new: false` means the registry is authoritative.** The description and
  sequence are read from the bundled registry by `name`, and anything you send
  in those fields is ignored. A name that is not in the registry fails the
  request with a `500`.
- **`new: true` means you supply everything**, including `sequence`. Give the
  sequence in **lower case**: the assembly-scar rule that joins parts into the
  parent sequence inspects the leading bases literally.
- **`uri` has to end in `/` or `#`.** Registry metadata is attached to each part
  as annotations under the namespace `{uri}{name}#`.
- **`instance_id` distinguishes parts that share a name.** Include it only when
  two or more components share that name and all of them have the same role, and
  number them from 1 in list order.
- **Send `namespace` on every request.** It is applied process-wide when present
  and left untouched when absent, so a request that omits it is built under
  whatever namespace the previous request set — the namespace leaks between
  requests, and between clients sharing the service. With no namespace ever set,
  documents are built under `http://sbols.org/unspecified_namespace/`.

The roles a component may take are `Promoter`, `RBS`, `CDS`, `Terminator`,
`Operator`, `Engineered-Region`, `Aptamer-DNA`, `Aptamer-RNA`,
`Inert-DNA-Spacer`, `Ncrna`, `PolyA-Site`, `Primer-Binding-Site`,
`Origin-Of-Transfer`, `Origin-Of-Replication` and `mRNA`. `openapi.yaml` lists
the Sequence Ontology term each one maps to.

### Referring to a part

Operons, unions and interaction participants refer to a part by the string
`{name}_{instance_id}`, defaulting to `{name}_1` when the part carries no
`instance_id`. External species are referred to by their bare `name`.

### `expressions`

An operon: a named group of parts, optionally with a constitutive promoter, and
with ordering relationships between its members.

```json
{
  "name": "LacI Operon",
  "components": ["BBa_R0010_1", "BBa_B0034_1", "BBa_C0012_1"],
  "unions": [
    { "type": "Order", "from": "BBa_R0010_1", "to": "BBa_B0034_1" },
    { "type": "Order", "from": "BBa_B0034_1", "to": "BBa_C0012_1" }
  ],
  "constitutive": false
}
```

`type` is `Order` or `Regulate`. **An empty `expressions` array means no
functional system is built, and `interactions` and `eds` are then ignored.**

### `interactions`

```json
{
  "type": "Inhibition",
  "participants": {
    "Inhibitor": ["LacI"],
    "Inhibited": ["BBa_R0010_1"]
  }
}
```

Use the participation roles that
`GET /component/interactions?interaction_type=...` returns for that type. They
are not enforced — any of the ten roles below is accepted on any interaction
type, and a mismatch produces a document that is structurally valid and
semantically wrong. A key outside all ten fails the request with a `500`.

The meaningful combinations are:

| Interaction type | Participation roles |
| --- | --- |
| Inhibition | Inhibitor, Inhibited |
| Stimulation | Stimulator, Stimulated |
| Biochemical Reaction | Reactant, Modifier, Product |
| Non-Covalent Binding | Reactant, Product |
| Degradation | Reactant |
| Control | Modifier, Modified |
| Genetic Production | Promoter, Template, Product |

### `eds`

Species that take part in interactions but are not encoded on the DNA.

```json
{
  "name": "LacI",
  "type": "Protein",
  "uri": "https://identifiers.org/uniprot:P03023"
}
```

`type` is `Simple Chemical`, `Protein` or `Restriction Enzyme`. `Protein` and
`Restriction Enzyme` are both typed as protein in the generated document, and
`Protein` denotes molecular type only; no transcription-factor activity is inferred.

A resolvable identifier is the useful choice for `uri` — for example
`https://identifiers.org/CHEBI:61448` for IPTG, or
`https://identifiers.org/uniprot:P03023` for LacI.

### Worked examples

Each folder under [`examples/`](examples) holds a circuit image, the exact
`request.json` that produced its output, and the resulting SBOL3, GenBank and
FASTA files.

---

## Errors

| Status | Meaning |
| --- | --- |
| `400` | A required parameter is missing, or a parameter value is not recognised |
| `404` | The named part does not exist, or the file path does not exist |
| `500` | The model or database is unavailable, or a document could not be built |

The `error` message is written for a human reader and is not a stable
identifier; branch on the status code, not on the message text.

Common causes of a `500` from `POST /file/create`:

- a part marked `new: false` whose name is not in the bundled registry
- a part whose `name` is not a valid SBOL `displayId`
- a `role` outside the list above, including a detector class such as `cds-arrow`
- a participation key outside the ten participation roles

A participation role that is valid in itself but wrong for its interaction type
is accepted, not rejected.

---

## Contributing

Issues and pull requests are welcome on the
[GC-AI repository](https://github.com/DRAGGON-Lab/GC-AI). When changing the API,
update `openapi.yaml` in the same change: it is the contract this page describes.
