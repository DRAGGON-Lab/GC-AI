# Frozen CPU detector qualification protocol

Research question: how well does the frozen detector identify individual SBOL
foreground glyphs on 20 newly authored circuit families under four capture
conditions? The qualification unit is 20 designs represented by 80 images,
not 80 independent designs. Development fixtures are excluded and must not be
used to tune the model or operating point against this corpus.

For each family collect: digital rendering, photograph of its printed diagram,
clear photograph of a hand drawing, and a harder hand-drawn photograph. Record
clutter, camera angle, illumination and resolution for the harder condition.
All 14 foreground classes must occur in at least five families. Keep `cds` and
`cds-arrow` distinct. Background is never an evaluated category.

Run `python tools/benchmark/prepare.py --output /private/path/corpus` to author
20 deterministic vector designs and a capture inventory. Their originals reuse
MIT-licensed repository glyph artwork. Render each SVG to PNG without changing
its layout, then make the three physical captures; never synthesize photographs
or treat historical predictions as labels. Record reuse rights, author and
capture provenance. Use `tools/benchmark/annotate.html` locally to draw boxes and
assign reading order independently of predictions. A reviewer must inspect
and approve every image, class and box. Review exports include image identity,
capture condition, provenance, rights and approval. Assemble them with
`python tools/benchmark/assemble.py --inventory inventory.json --reviews reviews
--images images --output approved-coco.json`.

Evaluation uses the pinned official COCO evaluator (`pycocotools==2.0.11`),
[COCOeval source](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/cocoeval.py).
AP@0.5 and AP@0.5:0.95 use ranked detections at score floor 0.001; COCO maxDets
is [1,10,100]. The service operating point stays 0.7, and class-agnostic overlap
suppression stays 0.3. Operating-point comparisons preserve the float32
threshold representation (`0.699999988079071`) used by deployed NumPy arrays;
exporting a score to JSON must not exclude a detection accepted at that boundary. The runner records TorchVision's internal score threshold,
class-aware NMS, detection limit, RPN thresholds/limits and versions. It lowers
only the internal evaluation score filter, restoring it after evaluation. It
compares each 0.7 operating-point result to ranked outputs filtered at 0.7.
Any difference fails evaluation rather than silently changing deployment.

Per-class precision, recall and F1 at score 0.7 and IoU 0.5 are read from COCO's
matching results (not an independent matching implementation). Report image and
family support, per-condition metrics, false positives, misses, duplicate
candidates, class-confusion candidates and reading-order inversions against
explicit reviewer order. Confusion/duplicate examples are diagnostic overlap
candidates, not additional COCO true positives. Missing reading-order labels
produce N/A. Save annotated error images for human inspection.

A report must record full source and environment identities, checkpoint hash,
corpus hash, dependency versions and settings. Missing captures, rights,
provenance, independent labels or approval fail qualification. Unsupported
measurements are N/A; no measurements are inferred from committed examples.
No minimum accuracy threshold is invented. The owner must explicitly accept
the measured report and its limitations before CPU candidate publication.
Production/GPU qualification remains separate.
