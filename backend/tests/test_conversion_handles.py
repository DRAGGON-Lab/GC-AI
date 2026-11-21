"""Actual route conversion and sequence/feature retention regressions."""

import io
import zipfile
from Bio import SeqIO
import pytest
from app import create_app
from test_exports import payload


@pytest.fixture
def client(tmp_path):
    return create_app(
        {"TESTING": True, "FILES_GENERATED_DIR": str(tmp_path / "artifacts")}
    ).test_client()


def create(client):
    response = client.post("/file/create", json=payload())
    assert response.status_code == 200, response.json
    assert "file_path_structural" not in response.headers
    return response.headers["X-GCAI-Structural-Handle"]


@pytest.mark.parametrize("fasta,genbank", [(True, False), (False, True), (True, True)])
def test_selected_formats_are_complete_parseable_and_preserve_coordinates(
    client, fasta, genbank
):
    handle = create(client)
    response = client.post(
        "/file/convert",
        json={"structural_handle": handle, "fasta": fasta, "genbank": genbank},
    )
    assert response.status_code == 200, response.json
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        expected = ({"design.fasta"} if fasta else set()) | (
            {"design.gb"} if genbank else set()
        )
        assert set(archive.namelist()) == expected
        for name in expected:
            records = list(
                SeqIO.parse(
                    io.StringIO(archive.read(name).decode()),
                    "fasta" if name.endswith("fasta") else "genbank",
                )
            )
            records = {record.id.split(".")[0]: record for record in records}
            assert str(records["Design"].seq).lower() == "atgctactagagnnaa"
            assert str(records["part0"].seq).lower() == "atgc"
            assert str(records["part1"].seq).lower() == "nnaa"
            if name.endswith("gb"):
                assert sorted(
                    (int(f.location.start), int(f.location.end))
                    for f in records["Design"].features
                ) == [(0, 4), (12, 16)]


@pytest.mark.parametrize(
    "body,status",
    [
        ({"file_path": "/etc/passwd", "fasta": True, "genbank": False}, 400),
        ({"structural_handle": "../secret", "fasta": True, "genbank": False}, 400),
        ({"structural_handle": "v1_" + "a" * 43, "fasta": True, "genbank": False}, 404),
        ({"fasta": True, "genbank": False}, 400),
        ({"fasta": False, "genbank": False}, 400),
        ({"fasta": 1, "genbank": False}, 400),
    ],
)
def test_invalid_conversion_requests(client, body, status):
    response = client.post("/file/convert", json=body)
    assert response.status_code == status
    assert response.is_json and response.json["code"]


def test_missing_sequence_is_actionable_422(client):
    response = client.post("/file/create", json=payload(("", "ATGC")))
    response = client.post(
        "/file/convert",
        json={
            "structural_handle": response.headers["X-GCAI-Structural-Handle"],
            "fasta": True,
            "genbank": True,
        },
    )
    assert response.status_code == 422
    assert "complete" in response.json["error"]


@pytest.mark.parametrize("failure", ["raise", "empty"])
def test_partial_conversion_failure_never_publishes_zip(client, monkeypatch, failure):
    from app.routes import file_routes

    handle = create(client)

    def fail(doc, path):
        if failure == "raise":
            raise RuntimeError("/private/checkpoint/secret")
        open(path, "w").close()

    monkeypatch.setattr(file_routes, "convert_to_genbank", fail)
    response = client.post(
        "/file/convert",
        json={"structural_handle": handle, "fasta": True, "genbank": True},
    )
    assert response.status_code == 500
    assert response.is_json
    assert b"/private/" not in response.data
    # Failed conversions keep the capability usable for a retry.
    response = client.post(
        "/file/convert",
        json={"structural_handle": handle, "fasta": True, "genbank": False},
    )
    assert response.status_code == 200


def test_feature_level_orientation_is_rejected_before_converter(client, monkeypatch):
    import sbol3
    from app.utils.artifacts import ArtifactStore
    from app.routes import file_routes

    store = ArtifactStore(client.application.config["FILES_GENERATED_DIR"])
    handle = create(client)
    doc = sbol3.Document()
    doc.read_string(store.read(handle).decode(), "xml")
    parent = doc.find("https://example.org/test/Design")
    parent.features.append(
        sbol3.SequenceFeature(
            sbol3.Range(parent.sequences[0], 1, 4),
            orientation=sbol3.SBOL_REVERSE_COMPLEMENT,
        )
    )
    assert len(doc.validate()) == 0
    handle = store.publish(b"full", doc.write_string("xml").encode())
    monkeypatch.setattr(
        file_routes,
        "convert_to_genbank",
        lambda *args: pytest.fail("Unsupported orientation reached converter"),
    )
    response = client.post(
        "/file/convert",
        json={"structural_handle": handle, "fasta": False, "genbank": True},
    )
    assert response.status_code == 422
    assert "Feature-level orientation" in response.json["error"]


@pytest.fixture(scope="module")
def regenerated_examples(tmp_path_factory):
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "tools/reconcile_sbol_validation.py"
    spec = importlib.util.spec_from_file_location(
        "conversion_example_reconciliation", script
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = tmp_path_factory.mktemp("conversion-examples")
    module.regenerate(directory)
    return directory


@pytest.mark.parametrize(
    "example", ["YES GATE", "Repressilator (BBa_I5200)", "Lux System (BBa_I13263)"]
)
def test_committed_examples_keep_sequences_and_legacy_parent_coordinates(
    client, regenerated_examples, example
):
    """Current exports preserve biological sequence/coordinates from committed examples.

    Legacy GenBank contains only the parent. Current GenBank also includes the
    component records present in FASTA; comparing records does not imply that
    legacy RDF is valid or that the new serialization is byte-identical.
    """
    from pathlib import Path
    from app.utils.artifacts import ArtifactStore

    original = Path(__file__).resolve().parents[2] / "docs/examples" / example
    fasta = next(original.glob("*.fasta"))
    genbank = next(original.glob("*.gb"))
    sequences = {r.id: str(r.seq).lower() for r in SeqIO.parse(fasta, "fasta")}
    legacy_records = {r.id: r for r in SeqIO.parse(genbank, "genbank")}
    structural = (regenerated_examples / example / "structural.xml").read_bytes()
    handle = ArtifactStore(client.application.config["FILES_GENERATED_DIR"]).publish(
        b"full", structural
    )
    response = client.post(
        "/file/convert",
        json={"structural_handle": handle, "fasta": True, "genbank": True},
    )
    assert response.status_code == 200, response.json
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        for name, format_name in [("design.fasta", "fasta"), ("design.gb", "genbank")]:
            records = list(
                SeqIO.parse(io.StringIO(archive.read(name).decode()), format_name)
            )
            current = {
                (r.id.rsplit(".", 1)[0] if format_name == "genbank" else r.id): r
                for r in records
            }
            assert {
                name: str(record.seq).lower() for name, record in current.items()
            } == sequences
            if format_name == "genbank":
                for name, record in legacy_records.items():
                    coords = lambda r: sorted(
                        (int(f.location.start), int(f.location.end), f.location.strand)
                        for f in r.features
                    )
                    assert coords(current[name]) == coords(record)
