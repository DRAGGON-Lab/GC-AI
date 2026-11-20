# Examples

Each folder holds one circuit end to end:

| File | What it is |
| --- | --- |
| `*-CIRCUIT.png` | The input image: a photograph of a hand-drawn diagram |
| `detections.json` | What `POST /inference/` returns for that image, ordered left to right |
| `request.json` | The `POST /file/create` body that produces the files below |
| `*.xml` | The full SBOL3 document |
| `*.gb`, `*.fasta` | GenBank and FASTA from `POST /file/convert` |

`request.json` is the piece worth reading: it is a complete, working request, and
the quickest way to understand the API is to replay one and change it.

```sh
curl -fsS -X POST http://localhost:5001/file/create \
  -H 'Content-Type: application/json' \
  --data @"YES GATE/request.json" \
  -D headers.txt -o design.xml
```

## What is in each

| Example | Parts | Operons | Interactions | Species | Glyphs detected in the image |
| --- | ---: | ---: | ---: | ---: | ---: |
| YES GATE | 8 | 2 | 4 | 3 | 2 |
| Repressilator (BBa_I5200) | 20 | 4 | 7 | 4 | 3 |
| Lux System (BBa_I13263) | 10 | 2 | 4 | 4 | 4 |

## Detection does not produce these designs on its own

The last column is the number of glyphs the model finds in that folder's image,
and it is well short of the number of parts in the design. These images are
photographs of pen-on-paper drawings, which is the hardest case for the detector.

Detection is a starting point: it proposes some of the parts, and the rest of the
design — the missing parts, every part name, the operons, the interactions and
the species — is entered by hand in the web interface. `request.json` records the
finished design, not the detector's output. `detections.json` records what the
detector actually returned, so the two can be compared.

## How `request.json` was produced

Each one is derived from the committed `.xml` and verified by replaying it
against the service and comparing the result with that `.xml` triple by triple.
`YES GATE` reproduces its document exactly. The other two reproduce theirs
exactly apart from the species URIs, which are trimmed here: the committed
documents carry leading or trailing spaces in `ExternallyDefined.definition`,
and a URI with a space in it cannot be canonicalised by standard RDF tooling.
One species in the Lux system has no URI at all, which is reproduced as it is.

The service does not check the `uri` field of an entry in `eds`, so whitespace in
it reaches the generated document unchanged.
