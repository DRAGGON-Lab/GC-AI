# Examples

Captured output: each folder holds one circuit end to end. For the code that
produces this kind of output, see [`examples/`](../../examples/).

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

## How these files were produced

Each `request.json` is derived from the document that was committed for that
example, and verified by replaying it against the service and comparing the
result with that document triple by triple. The YES gate reproduced its
document exactly, so its files are untouched.

The Repressilator and Lux documents carried leading or trailing spaces in
`ExternallyDefined.definition` — all four species URIs in the Repressilator,
two of four in the Lux system. A URI containing a space cannot be
canonicalised by standard RDF tooling, so those documents could not be
processed by ordinary RDF libraries at all. The requests here hold the
trimmed URIs and the two documents are regenerated from them, which changes
nothing else: both still hold the same number of triples, and their GenBank
and FASTA files are byte for byte what they were.

All three documents now canonicalise, and validate with no errors and no
warnings.

One species in the Lux system, `LuxR-AHL Complex`, has no URI at all. That is
kept as it is, because it is what the design says. Be aware that an empty
`rdf:resource` is resolved against the document's own location when the file
is parsed, so that species appears to be defined by whatever path the file
happens to sit at.

The service does not check the `uri` field of an entry in `eds`, so whatever
is typed into the web interface reaches the generated document unchanged.
