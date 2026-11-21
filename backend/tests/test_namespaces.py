"""Namespace boundary and RDF isolation regressions; no registry/detector required."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import sbol3
from rdflib import URIRef

from app import create_app
from app.utils.file import create_file_sol3
from test_exports import payload


def functional_payload(namespace):
    data = payload()
    data["namespace"] = namespace
    data["expressions"] = [
        {
            "name": "operon",
            "components": ["part0_1", "part1_1"],
            "unions": [],
            "constitutive": True,
        }
    ]
    return data


@pytest.mark.parametrize(
    "value,status",
    [
        (None, 400),
        (17, 400),
        (False, 400),
        ("", 422),
        ("relative/path", 422),
        ("ftp://example.org/n", 422),
        ("https://a:b@example.org/n", 422),
        ("https://example.org/n?q=x", 422),
        ("https://example.org/n#frag", 422),
        ("https://example.org/n?", 422),
        ("https://example.org/n#", 422),
        ("https://example.org/n space", 422),
        ("https://example.org:bad/n", 422),
        ("https://example.org/n\x00", 422),
        ("https://example.org/n\x1f", 422),
        ("https://example.org/n\x7f", 422),
    ],
)
def test_namespace_rejected_before_database_or_artifacts(
    tmp_path, monkeypatch, value, status
):
    from app.routes import file_routes

    monkeypatch.setattr(
        file_routes, "get_db_connection", lambda: pytest.fail("Database accessed")
    )
    directory = tmp_path / "artifacts"
    app = create_app({"TESTING": True, "FILES_GENERATED_DIR": str(directory)})
    data = payload()
    data["namespace"] = value
    data["components"][1]["new"] = False
    response = app.test_client().post("/file/create", json=data)
    assert response.status_code == status, response.json
    assert not directory.exists()


def test_missing_namespace_rejected(tmp_path):
    app = create_app(
        {"TESTING": True, "FILES_GENERATED_DIR": str(tmp_path / "artifacts")}
    )
    data = payload()
    del data["namespace"]
    assert app.test_client().post("/file/create", json=data).status_code == 400
    assert not (tmp_path / "artifacts").exists()


def assert_namespace(doc, namespace):
    graph = doc.graph()
    assert list(graph.triples((None, URIRef(sbol3.SBOL_NAMESPACE), None)))
    for obj in doc.objects:
        assert obj.namespace == namespace
        assert obj.identity.startswith(namespace + "/")
        assert not obj.identity.startswith(namespace + "//")
    for subject, predicate, target in graph:
        if str(predicate) in {
            sbol3.SBOL_INSTANCE_OF,
            sbol3.SBOL_SEQUENCES,
            sbol3.SBOL_SEQUENCE,
            sbol3.SBOL_IN_CHILD_OF,
            sbol3.SBOL_REFERS_TO,
        }:
            assert str(target).startswith(namespace + "/")
    assert len(doc.validate()) == 0


def test_sequential_exports_ignore_library_global_namespace():
    original = sbol3.get_namespace()
    try:
        sbol3.set_namespace("https://a.example")
        for namespace in ["https://a.example/design", "https://b.example/design"]:
            for functional in (True, False):
                doc = create_file_sol3(
                    None, functional_payload(namespace + "///"), functional
                )
                assert_namespace(doc, namespace)
                assert sbol3.get_namespace() == "https://a.example"
        bad = functional_payload("https://a.example/design")
        del bad["namespace"]
        from app.utils.custom_error import CustomError

        with pytest.raises(CustomError) as error:
            create_file_sol3(None, bad, True)
        assert error.value.status_code == 400
    finally:
        sbol3.set_namespace(original)


def test_concurrent_exports_keep_rdf_namespaces_and_references_isolated():
    barrier = Barrier(2)
    original = sbol3.get_namespace()
    sbol3.set_namespace("https://a.example")

    def export(namespace):
        barrier.wait(timeout=5)
        return [
            create_file_sol3(None, functional_payload(namespace), functional)
            for functional in (True, False)
        ]

    try:
        namespaces = ["https://a.example/design", "https://b.example/design"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(export, namespaces))
        for namespace, documents in zip(namespaces, results):
            for doc in documents:
                assert_namespace(doc, namespace)
        assert sbol3.get_namespace() == "https://a.example"
    finally:
        sbol3.set_namespace(original)


def export_documents(app, namespace):
    """Read both artifacts emitted by the actual create route."""
    from app.utils.artifacts import ArtifactStore

    response = app.test_client().post(
        "/file/create", json=functional_payload(namespace)
    )
    assert response.status_code == 200, response.json
    full = sbol3.Document()
    full.read_string(response.data.decode(), "xml")
    structural_bytes = ArtifactStore(app.config["FILES_GENERATED_DIR"]).read(
        response.headers["X-GCAI-Structural-Handle"]
    )
    structural = sbol3.Document()
    structural.read_string(structural_bytes.decode(), "xml")
    return [full, structural]


def test_route_a_missing_b_exports_keep_both_artifacts_isolated(tmp_path):
    app = create_app(
        {"TESTING": True, "FILES_GENERATED_DIR": str(tmp_path / "artifacts")}
    )
    for namespace in ["https://a.example/design", "https://b.example/design"]:
        for doc in export_documents(app, namespace + "///"):
            assert_namespace(doc, namespace)
        data = functional_payload(namespace)
        del data["namespace"]
        assert app.test_client().post("/file/create", json=data).status_code == 400


def test_route_concurrent_a_b_exports_keep_both_artifacts_isolated(
    tmp_path, monkeypatch
):
    from app.routes import file_routes

    app = create_app(
        {"TESTING": True, "FILES_GENERATED_DIR": str(tmp_path / "artifacts")}
    )
    barrier = Barrier(2)
    original_export = file_routes.create_file_sol3

    def synchronized_export(cursor, data, functional):
        # Force both requests into full generation, then structural generation.
        barrier.wait(timeout=5)
        return original_export(cursor, data, functional)

    monkeypatch.setattr(file_routes, "create_file_sol3", synchronized_export)
    namespaces = ["https://a.example/design", "https://b.example/design"]
    original_namespace = sbol3.get_namespace()
    try:
        sbol3.set_namespace("https://a.example")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda ns: export_documents(app, ns), namespaces))
        for namespace, documents in zip(namespaces, results):
            for doc in documents:
                assert_namespace(doc, namespace)
        assert sbol3.get_namespace() == "https://a.example"
    finally:
        sbol3.set_namespace(original_namespace)
