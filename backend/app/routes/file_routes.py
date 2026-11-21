"""Validated transactional SBOL exports and capability-based local conversion."""

from contextlib import nullcontext
import io
import os
import tempfile
import zipfile

from flask import Blueprint, current_app, request, send_file
import sbol3
from sbol_utilities.conversion import convert_to_fasta
from app.utils.file import create_file_sol3, validate_sbol3_document
from app.utils.validation import validate_create, reject
from app.utils.custom_error import CustomError
from app.utils.artifacts import ArtifactStore
from app.utils.conversion import preflight, convert_to_genbank, verify_artifact
from app.config import get_db_connection, FILES_GENERATED_DIR

file_blueprint = Blueprint("file", __name__)


def json_object():
    if not request.is_json:
        raise CustomError("Expected application/json", 400, code="invalid_json")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise CustomError("Expected a JSON object", 400, code="invalid_json")
    return data


def require_valid(doc):
    valid, issues = validate_sbol3_document(doc)
    if not valid:
        raise CustomError(
            "SBOL validation failed", 422, code="sbol_validation_failed", issues=issues
        )


def artifact_store():
    return ArtifactStore(
        current_app.config.get("FILES_GENERATED_DIR", FILES_GENERATED_DIR)
    )


@file_blueprint.route("/create", methods=["POST"])
def create_file():
    data = validate_create(json_object())
    store = artifact_store()
    connection = None
    try:
        if any(not c["new"] for c in data["components"]):
            connection = get_db_connection()
        documents = {}
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=store.root) as staging:
            with connection.cursor() if connection else nullcontext(None) as cursor:
                for name, functional in (("full", True), ("structural", False)):
                    doc = create_file_sol3(cursor, data, functional)
                    require_valid(doc)
                    path = os.path.join(staging, name + ".xml")
                    # Reserve a private file before the serializer opens it.
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(fd)
                    doc.write(path)
                    parsed = sbol3.Document()
                    parsed.read(path)
                    require_valid(parsed)
                    with open(path, "rb") as stream:
                        documents[name] = stream.read()
            handle = store.publish(documents["full"], documents["structural"])
        response = send_file(
            io.BytesIO(documents["full"]),
            as_attachment=True,
            mimetype="application/rdf+xml",
            download_name="design.xml",
        )
        response.headers["X-GCAI-Structural-Handle"] = handle
        return response
    finally:
        if connection is not None:
            connection.close()


@file_blueprint.route("/convert", methods=["POST"])
def convert_sbol3():
    data = json_object()
    if "file_path" in data:
        reject(
            "file_path",
            "Server paths are no longer accepted; use structural_handle returned in X-GCAI-Structural-Handle by /file/create",
            400,
        )
    for flag in ("genbank", "fasta"):
        if not isinstance(data.get(flag), bool):
            reject(flag, "Expected a boolean", 400)
    if not data["genbank"] and not data["fasta"]:
        reject("", "Select at least one conversion format", 400)
    contents = artifact_store().read(data.get("structural_handle"))
    try:
        doc = sbol3.Document()
        doc.read_string(contents.decode("utf-8"), "xml")
    except Exception:
        raise CustomError(
            "Cannot parse the generated SBOL document", 422, code="invalid_sbol"
        ) from None
    require_valid(doc)
    components = preflight(doc)
    buffer = io.BytesIO()
    # No artifacts are returned until all requested formats have passed parsing and comparison.
    with tempfile.TemporaryDirectory(prefix="gcai-conversion-") as temporary:
        outputs = []
        for selected, extension, parser, convert in (
            ("fasta", "fasta", "fasta", convert_to_fasta),
            ("genbank", "gb", "genbank", convert_to_genbank),
        ):
            if not data[selected]:
                continue
            filename = "design." + extension
            path = os.path.join(temporary, filename)
            convert(doc, path)
            with open(path, "rb") as stream:
                result = stream.read()
            verify_artifact(result, parser, components)
            outputs.append((filename, result))
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, result in outputs:
                archive.writestr(name, result)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        mimetype="application/zip",
        download_name="converted_files.zip",
    )
