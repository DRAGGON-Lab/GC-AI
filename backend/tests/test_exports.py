from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
import sbol3
from app import create_app
from app.utils.file import create_file_sol3
from app.utils.custom_error import CustomError


def payload(sequences=("ATGC", "NNAA")):
    return {
        "namespace": "https://example.org/test",
        "components": [
            {
                "name": "Design",
                "role": "Engineered-Region",
                "new": True,
                "uri": "https://example.org/",
            },
            *[
                {
                    "name": f"part{i}",
                    "role": "CDS",
                    "new": True,
                    "uri": "https://example.org/",
                    "sequence": seq,
                }
                for i, seq in enumerate(sequences)
            ],
        ],
        "expressions": [],
        "interactions": [],
        "eds": [],
    }


@pytest.fixture
def client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "FILES_GENERATED_DIR": str(tmp_path / "generated"),
            "FILES_CONVERTED_DIR": str(tmp_path / "converted"),
        }
    )
    return app.test_client()


def read(response):
    doc = sbol3.Document()
    doc.read_string(response.data.decode(), "xml")
    return doc


def test_valid_export_and_correct_coordinates(client):
    response = client.post("/file/create", json=payload())
    assert response.status_code == 200, response.json
    doc = read(response)
    parent = doc.find("https://example.org/test/Design")
    assert parent.sequences[0].lookup().elements == "atgctactagagnnaa"
    assert sorted(
        (f.locations[0].start, f.locations[0].end) for f in parent.features
    ) == [(1, 4), (13, 16)]
    assert all(c.restriction == sbol3.SBOL_PRECEDES for c in parent.constraints)
    from app.utils.artifacts import ArtifactStore
    assert ArtifactStore(client.application.config["FILES_GENERATED_DIR"]).read(response.headers["X-GCAI-Structural-Handle"])
    assert len(doc.validate()) == 0


@pytest.mark.parametrize("sequences", [("", ""), ("ATGC", "")])
def test_unknown_bases_have_no_parent_sequence_or_ranges(client, sequences):
    response = client.post("/file/create", json=payload(sequences))
    assert response.status_code == 200, response.json
    doc = read(response)
    parent = doc.find("https://example.org/test/Design")
    assert not parent.sequences
    assert all(not f.locations for f in parent.features)
    converted = client.post(
        "/file/convert",
        json={
            "structural_handle": response.headers["X-GCAI-Structural-Handle"],
            "fasta": True,
            "genbank": False,
        },
    )
    assert converted.status_code == 422


@pytest.mark.parametrize(
    "change",
    ["rna", "characters", "displayid", "unknownrole", "missingfields", "badinstance"],
)
def test_bad_requests_rejected_before_generation(client, change):
    data = payload()
    if change == "rna":
        data["components"][1]["role"] = "mRNA"
    elif change == "characters":
        data["components"][1]["sequence"] = "AUCG"
    elif change == "displayid":
        data["components"][1]["name"] = "bad name"
    elif change == "unknownrole":
        data["components"][1]["role"] = "MadeUp"
    elif change == "missingfields":
        del data["eds"]
    elif change == "badinstance":
        data["components"][1]["instance_id"] = "1"
    response = client.post("/file/create", json=data)
    assert response.status_code in (400, 422)
    assert response.json["code"]


@pytest.mark.parametrize(
    "content,kind",
    [("no", "application/json"), ("[]", "application/json"), ("{}", "text/plain")],
)
def test_invalid_json(client, content, kind):
    assert (
        client.post("/file/create", data=content, content_type=kind).status_code == 400
    )


@pytest.mark.parametrize("warning", [False, True])
def test_tuple_regression_and_atomic_cleanup(client, monkeypatch, warning):
    from app.routes import file_routes

    monkeypatch.setattr(
        file_routes,
        "validate_sbol3_document",
        lambda doc: (
            False,
            [
                {
                    "severity": "warning" if warning else "error",
                    "message": "fabricated finding",
                }
            ],
        ),
    )
    response = client.post("/file/create", json=payload())
    assert response.status_code == 422
    assert response.json["issues"][0]["message"] == "fabricated finding"
    assert not list(Path(client.application.config["FILES_GENERATED_DIR"]).iterdir())


def test_structural_validation_failure_cleans_both_documents(client, monkeypatch):
    from app.routes import file_routes

    real = file_routes.validate_sbol3_document
    calls = []

    def validate(doc):
        calls.append(doc)
        return (
            (False, [{"message": "structural failed"}])
            if len(calls) == 3
            else real(doc)
        )

    monkeypatch.setattr(file_routes, "validate_sbol3_document", validate)
    response = client.post("/file/create", json=payload())
    assert response.status_code == 422
    assert not list(Path(client.application.config["FILES_GENERATED_DIR"]).iterdir())


def test_validation_exception_sanitized(client, monkeypatch):
    from app.routes import file_routes

    def explode(doc):
        raise RuntimeError("/private/secret traceback")

    monkeypatch.setattr(file_routes, "validate_sbol3_document", explode)
    response = client.post("/file/create", json=payload())
    assert response.status_code == 500
    assert b"secret" not in response.data


def test_no_operons_preserves_species_and_interactions(client):
    data = payload()
    data["eds"] = [
        {"name": "rna", "type": "RNA", "uri": ""},
        {"name": "protein", "type": "Protein", "uri": "https://example.org/protein"},
    ]
    data["interactions"] = [
        {
            "type": "Genetic Production",
            "participants": {"Template": ["part0_1"], "Product": ["rna", "protein"]},
        }
    ]
    response = client.post("/file/create", json=data)
    assert response.status_code == 200, response.json
    system = read(response).find("https://example.org/test/Design_system")
    assert len(system.interactions) == 1
    assert len(system.interactions[0].participations) == 3
    assert any(
        isinstance(f, sbol3.LocalSubComponent)
        and f.name == "rna"
        and sbol3.SBO_RNA in f.types
        for f in system.features
    )
    assert any(
        isinstance(f, sbol3.ExternallyDefined) and f.name == "protein"
        for f in system.features
    )


@pytest.mark.parametrize(
    "kind,participants",
    [
        ("Inhibition", {"Stimulator": ["part0_1"]}),
        ("Inhibition", {"Catalyst": ["part0_1"]}),
        ("Inhibition", {"Inhibitor": ["missing"]}),
        ("Unknown", {"Inhibitor": ["part0_1"]}),
        ("Inhibition", {}),
    ],
)
def test_invalid_interactions_rejected(client, kind, participants):
    data = payload()
    data["interactions"] = [{"type": kind, "participants": participants}]
    assert client.post("/file/create", json=data).status_code == 422


def test_same_part_multiple_roles_preserved(client):
    data = payload()
    data["interactions"] = [
        {
            "type": "Control",
            "participants": {"Modifier": ["part0_1"], "Modified": ["part0_1"]},
        }
    ]
    response = client.post("/file/create", json=data)
    assert response.status_code == 200, response.json
    system = read(response).find("https://example.org/test/Design_system")
    assert len(system.interactions[0].participations) == 2


@pytest.mark.parametrize("kind", ["Order", "Regulate"])
def test_union_emits_relative_order(client, kind):
    data = payload()
    data["expressions"] = [
        {
            "name": "operon",
            "components": ["part0_1", "part1_1"],
            "constitutive": False,
            "unions": [{"type": kind, "from": "part0_1", "to": "part1_1"}],
        }
    ]
    response = client.post("/file/create", json=data)
    assert response.status_code == 200, response.json
    system = read(response).find("https://example.org/test/Design_system")
    assert any(c.restriction == sbol3.SBOL_PRECEDES for c in system.constraints)


@pytest.mark.parametrize(
    "union",
    [
        {"type": "Unknown", "from": "part0_1", "to": "part1_1"},
        {"type": "Order", "from": "missing", "to": "part1_1"},
    ],
)
def test_invalid_unions_fail(client, union):
    data = payload()
    data["expressions"] = [
        {
            "name": "operon",
            "components": ["part0_1", "part1_1"],
            "constitutive": False,
            "unions": [union],
        }
    ]
    assert client.post("/file/create", json=data).status_code == 422


def test_diagnostics_bounded(client, monkeypatch):
    from app.routes import file_routes

    monkeypatch.setattr(
        file_routes,
        "validate_sbol3_document",
        lambda doc: (False, [{"message": "x" * 2000}] * 70),
    )
    response = client.post("/file/create", json=payload())
    assert len(response.json["issues"]) == 50
    assert len(response.json["issues"][0]["message"]) == 1000
    assert response.json["total_count"] == 70 and response.json["truncated"]


def test_expected_lookup_error_keeps_404():
    from app.utils.file import get_component_data

    cursor = SimpleNamespace(execute=lambda *a: None, fetchone=lambda: None)
    with pytest.raises(CustomError) as error:
        get_component_data(cursor, "missing")
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "path,value",
    [
        (("components", 1, "role"), []),
        (("components", 1, "description"), {}),
        (("namespace",), []),
        (("components", 1, "new"), 0),
    ],
)
def test_wrong_json_types_do_not_become_500(client, path, value):
    data = payload()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert client.post("/file/create", json=data).status_code in (400, 422)


def test_bad_species_type_shape(client):
    data = payload()
    data["eds"] = [{"name": "rna", "type": {}, "uri": ""}]
    assert client.post("/file/create", json=data).status_code == 400


def test_expired_export_and_abandoned_staging_directories_removed(tmp_path):
    import os, time, uuid
    from app.utils.cleanup import empty_folders

    old = tmp_path / str(uuid.uuid4())
    old.mkdir()
    (old / "full.xml").write_text("old")
    current = tmp_path / str(uuid.uuid4())
    current.mkdir()
    staging = tmp_path / ".staging-active"
    staging.mkdir()
    yesterday = time.time() - 25 * 3600
    os.utime(old, (yesterday, yesterday))
    os.utime(staging, (yesterday, yesterday))
    empty_folders([str(tmp_path)], 24)
    assert not old.exists()
    assert current.exists() and not staging.exists()


def test_discovery_table_matches_client_and_openapi(client):
    import yaml
    from gcai.constants import PARTICIPATIONS as CLIENT
    from app.utils.validation import PARTICIPATIONS

    assert {
        kind.value: [r.value for r in roles] for kind, roles in CLIENT.items()
    } == PARTICIPATIONS
    spec = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "docs/openapi.yaml").read_text()
    )
    description = spec["components"]["schemas"]["ParticipationRole"]["description"]
    for kind, roles in PARTICIPATIONS.items():
        assert (
            client.get(
                "/component/interactions", query_string={"interaction_type": kind}
            ).json
            == roles
        )
        assert kind in description
        assert all(role in description for role in roles)


@pytest.mark.parametrize(
    "kind,participants",
    [
        ("Inhibition", {"Inhibitor": ["part0_1"], "Inhibited": ["part1_1"]}),
        ("Stimulation", {"Stimulator": ["part0_1"], "Stimulated": ["part1_1"]}),
        ("Biochemical Reaction", {"Reactant": ["part0_1"], "Product": ["part1_1"]}),
        ("Non-Covalent Binding", {"Reactant": ["part0_1"], "Product": ["part1_1"]}),
        ("Degradation", {"Reactant": ["part0_1"]}),
        ("Genetic Production", {"Template": ["part0_1"], "Product": ["part1_1"]}),
    ],
)
def test_supported_interactions_round_trip(client, kind, participants):
    data = payload()
    data["interactions"] = [{"type": kind, "participants": participants}]
    response = client.post("/file/create", json=data)
    assert response.status_code == 200, response.json
    system = read(response).find("https://example.org/test/Design_system")
    assert len(system.interactions[0].participations) == sum(
        len(v) for v in participants.values()
    )


def test_reverse_union_rejected(client):
    data = payload()
    data["expressions"] = [
        {
            "name": "operon",
            "components": ["part0_1", "part1_1"],
            "constitutive": False,
            "unions": [{"type": "Order", "from": "part1_1", "to": "part0_1"}],
        }
    ]
    assert client.post("/file/create", json=data).status_code == 422


def test_operon_species_name_collision_cannot_redirect_interaction(client):
    data = payload()
    data["eds"] = [{"name": "GFP", "type": "Protein", "uri": ""}]
    data["expressions"] = [
        {"name": "GFP", "components": ["part0_1"], "constitutive": False, "unions": []}
    ]
    data["interactions"] = [
        {
            "type": "Genetic Production",
            "participants": {"Template": ["part0_1"], "Product": ["GFP"]},
        }
    ]
    assert client.post("/file/create", json=data).status_code == 422


def test_serialized_document_parse_failure_is_atomic_and_sanitized(client, monkeypatch):
    def fail(self, path, *args, **kwargs):
        raise ValueError("/private/files/stack trace")

    monkeypatch.setattr(sbol3.Document, "read", fail)
    response = client.post("/file/create", json=payload())
    assert response.status_code == 500
    assert b"/private/" not in response.data
    assert not list(Path(client.application.config["FILES_GENERATED_DIR"]).iterdir())


def test_real_validator_report_is_not_lost():
    from app.utils.file import validate_sbol3_document

    doc = sbol3.Document()
    component = sbol3.Component("https://example.org/invalid", sbol3.SBO_DNA)
    doc.add(component)
    component.features.append(sbol3.LocalSubComponent([]))
    valid, issues = validate_sbol3_document(doc)
    assert valid is False
    assert issues and all(issue["message"] and issue["object_id"] for issue in issues)
    assert all("rule_id" in issue for issue in issues)  # pySBOL3 may omit a rule ID


@pytest.mark.parametrize("uri", ["", "https://example.org/GFP"])
def test_protein_molecular_type_does_not_imply_transcription_factor(client, uri):
    data = payload()
    data["eds"] = [{"name": "GFP", "type": "Protein", "uri": uri}]
    response = client.post("/file/create", json=data)
    assert response.status_code == 200
    system = read(response).find("https://example.org/test/Design_system")
    protein = next(f for f in system.features if f.name == "GFP")
    assert sbol3.SBO_PROTEIN in protein.types
    assert not protein.roles
    if uri:
        assert str(protein.definition) == uri


@pytest.mark.parametrize("uri", ["", "https://example.org/GFP"])
@pytest.mark.parametrize("instance", [1, 2])
def test_react_selection_preserves_same_name_dna_and_protein_in_export(
    client, uri, instance
):
    import json
    import subprocess

    data = payload()
    data["components"][0]["id"] = "component-principal"
    for i, component in enumerate(data["components"][1:]):
        component.update(id=f"dna-{i}", name="GFP", instance_id=i + 1, sequence="ATGC")
    data["eds"] = [{"id": "protein-gfp", "name": "GFP", "type": "Protein", "uri": uri}]
    data["selected_instance"] = instance
    script = r"""
import fs from 'node:fs';
const {participantOptions, selectParticipant, functionalPayload} = await import(process.argv[1]);
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const options = participantOptions(data.components, data.eds);
const choose = (kind, id) => selectParticipant({id: `row-${kind}`}, options.find(o => o.sourceKind === kind && o.sourceId === id));
const interactions = [{type:'Genetic Production', participants:{
  Template:[choose('component', `dna-${data.selected_instance - 1}`)],
  Product:[choose('species', 'protein-gfp')]
}}];
console.log(JSON.stringify(functionalPayload([], interactions, data.eds, data.components)));
"""
    module = (
        Path(__file__).resolve().parents[2] / "frontend/src/utils/FunctionalPayload.js"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, module.as_uri()],
        input=json.dumps(data),
        text=True,
        capture_output=True,
        check=True,
    )
    data.update(json.loads(result.stdout))
    response = client.post("/file/create", json=data)
    assert response.status_code == 200, response.json
    document = read(response)
    system = document.find("https://example.org/test/Design_system")
    participations = system.interactions[0].participations
    template = next(
        p.participant.lookup() for p in participations if sbol3.SBO_TEMPLATE in p.roles
    )
    product = next(
        p.participant.lookup() for p in participations if sbol3.SBO_PRODUCT in p.roles
    )
    assert template.identity != product.identity
    assert isinstance(template, sbol3.ComponentReference)
    dna = template.refers_to.lookup()
    assert dna.name == f"GFP_{instance}"
    assert sbol3.SBO_DNA in dna.instance_of.lookup().types
    assert product.name == "GFP" and sbol3.SBO_PROTEIN in product.types
    assert isinstance(
        product, sbol3.ExternallyDefined if uri else sbol3.LocalSubComponent
    )
