> These files are immutable legacy evidence. Their historical XML/GenBank/FASTA outputs are not a promise of current validator acceptance or byte-equivalent conversion. The current server validates species URIs and all generated SBOL before publication. Use the strict reconciliation report in `docs/validation` and regenerated structural artifacts for corrected sequence/coordinate evidence; current local GenBank exports also retain assembly features.

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

Strict reconciliation in `docs/validation` records historical validation defects and verifies corrected regenerated outputs. An empty Lux complex URI is represented by a typed LocalSubComponent in current generation. The current server validates species URIs and rejects whitespace rather than writing it through. Historical outputs remain immutable evidence.
