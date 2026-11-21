"""Actual Flask → SDK create/convert/build, with no registry or detector."""

import httpx
from Bio import SeqIO
import io
from app import create_app
from gcai import GCAIClient
from gcai.design import Design, Part
from gcai.constants import Role


def test_actual_sdk_build_returns_exact_requested_formats_and_coordinates(tmp_path):
    app = create_app(
        {"TESTING": True, "FILES_GENERATED_DIR": str(tmp_path / "artifacts")}
    )
    design = Design(name="Assembly", namespace="https://example.org/sdk///")
    design.parts.extend(
        [
            Part(name="first", role=Role.PROMOTER, new=True, sequence="ATGC"),
            Part(name="second", role=Role.CDS, new=True, sequence="GGTT"),
        ]
    )
    with GCAIClient(
        "http://gcai.test", transport=httpx.WSGITransport(app=app)
    ) as client:
        created = client.create(design)
        assert created.structural_handle.startswith("v1_")
        for genbank, fasta in [(True, False), (False, True), (True, True)]:
            artifacts = client.convert(
                created.structural_handle, genbank=genbank, fasta=fasta
            )
            assert set(artifacts) == {
                key
                for key, selected in [("genbank", genbank), ("fasta", fasta)]
                if selected
            }
            for format_name, content in artifacts.items():
                records = list(SeqIO.parse(io.StringIO(content.decode()), format_name))
                parent = next(r for r in records if r.id.split(".")[0] == "Assembly")
                assert str(parent.seq).lower() == "atgctactagagggtt"
                if format_name == "genbank":
                    assert sorted(
                        (int(f.location.start), int(f.location.end))
                        for f in parent.features
                    ) == [(0, 4), (12, 16)]
        built = client.build(design)
        assert built.fasta and built.genbank and built.sbol3
