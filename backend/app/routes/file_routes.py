"""Validated, transactional SBOL export and sequence conversion boundaries."""

from contextlib import nullcontext
import io
import logging
import os
import shutil
import tempfile
import uuid
import zipfile

from flask import Blueprint, current_app, request, send_file
import sbol3
from sbol_utilities.conversion import convert_to_genbank, convert_to_fasta
from app.utils.file import (
    create_file_sol3,
    validate_sbol3_document,
    generate_related_filename,
)
from app.utils.validation import validate_create, reject
from app.utils.custom_error import CustomError
from app.config import get_db_connection, FILES_GENERATED_DIR, FILES_CONVERTED_DIR

logger = logging.getLogger(__name__)
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


@file_blueprint.route("/create", methods=["POST"])
def create_file():
    data = validate_create(json_object())
    directory = current_app.config.get("FILES_GENERATED_DIR", FILES_GENERATED_DIR)
    os.makedirs(directory, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".staging-", dir=directory)
    destination = os.path.join(directory, str(uuid.uuid4()))
    connection = None
    try:
        if any(not c["new"] for c in data["components"]):
            connection = get_db_connection()
        with connection.cursor() if connection else nullcontext(None) as cursor:
            for name, functional in (("full", True), ("structural", False)):
                doc = create_file_sol3(cursor, data, functional)
                require_valid(doc)
                path = os.path.join(staging, name + ".xml")
                doc.write(path)
                parsed = sbol3.Document()
                parsed.read(path)
                require_valid(parsed)
        # Publish the directory once: neither file is reachable until both pass.
        os.replace(staging, destination)
        response = send_file(os.path.join(destination, "full.xml"), as_attachment=True)
        response.headers["file_path_structural"] = os.path.join(
            destination, "structural.xml"
        )
        return response
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if connection is not None:
            connection.close()


@file_blueprint.route("/convert", methods=["POST"])
def convert_sbol3():
    data = json_object()
    file_path = data.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        reject("file_path", "Expected a generated structural file reference", 400)
    for flag in ("genbank", "fasta"):
        if not isinstance(data.get(flag), bool):
            reject(flag, "Expected a boolean", 400)
    if not data["genbank"] and not data["fasta"]:
        reject("", "Select at least one conversion format", 400)
    if not os.path.isfile(file_path):
        raise CustomError("File not found", 404)
    try:
        doc = sbol3.Document()
        doc.read(file_path)
    except Exception:
        raise CustomError(
            "Cannot parse the SBOL document", 422, code="invalid_sbol"
        ) from None
    require_valid(doc)
    components = [o for o in doc.objects if isinstance(o, sbol3.Component)]
    if not components or any(
        not c.sequences or any(not q.lookup().elements for q in c.sequences)
        for c in components
    ):
        reject(
            "file_path", "Conversion requires a complete sequence for every component"
        )
    directory = current_app.config.get("FILES_CONVERTED_DIR", FILES_CONVERTED_DIR)
    os.makedirs(directory, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        output_files = []
        if data["fasta"]:
            path = os.path.join(
                temporary, generate_related_filename(file_path, "fasta", "fasta")
            )
            convert_to_fasta(doc, path)
            output_files.append(path)
        if data["genbank"]:
            path = os.path.join(
                temporary, generate_related_filename(file_path, "genbank", "gb")
            )
            convert_to_genbank(doc, path, allow_genbank_online=True)
            output_files.append(path)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for path in output_files:
                archive.write(path, os.path.basename(path))
        buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        mimetype="application/zip",
        download_name="converted_files.zip",
    )
