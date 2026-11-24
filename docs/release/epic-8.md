# CPU research release candidate — epic #8

Starting source: GC-AI `3cace2414cab`; canonical environment
[DRAGGON-Lab/GC-AI-environment](https://github.com/DRAGGON-Lab/GC-AI-environment)
`29378b9a0e57`. Production cutover, production credential rotation and GPU
qualification remain separate epic #7 gates. Candidate publication requires
review of concrete qualification evidence and scientific acceptance.

## #22 integration acceptance

[PR #5](https://github.com/DRAGGON-Lab/GC-AI/pull/5), head
`25dd74dfd74164b05bb2af5c898289f90e9eb6a7`, was merged as `5690835` on its
original branch. [PR #30](https://github.com/DRAGGON-Lab/GC-AI/pull/30)
integrated its intended delta into main. This acceptance change preserves that
implementation; it does not cherry-pick the obsolete branch over current main.

Provenance comparison: `git diff 5690835^ 5690835 -- examples client .github
README.md` identifies 16 changed files. All three example entrypoints, both
example test modules, shared `name_parts` in `gcai.design`, its MCP caller and
the zero-base conversion guard remain present. Comparing `25dd74d` to the
starting main shows subsequent fixes to namespace isolation, opaque handles,
TLS authentication, explicit participant identity and sequence-aware exports.
Those fixes intentionally supersede the original wire behavior.

Executed on 24 November 2026, Python 3.12.13, clean starting main:

| Command | Result |
| --- | --- |
| `/private/tmp/gcai-venv/bin/python -m pytest client/tests -q` | exit 0; 146 passed, 22 live integrations deselected; db and MCP extras installed |
| `python -m mypy --config-file client/pyproject.toml client/src examples` | exit 0; 15 source files |
| Example imports | Included in `test_examples.py`; no live services needed |

The historical acceptance matrix contains earlier counts and prerequisites;
current release claims must use this candidate's own evidence. Historical
example inference records remain immutable and are regression evidence only.
