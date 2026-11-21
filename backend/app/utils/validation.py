"""Server-owned request and scientific invariants, shared with discovery routes."""

import re
from urllib.parse import urlsplit
from app.utils.custom_error import CustomError

PARTICIPATIONS = {
    "Inhibition": ["Inhibitor", "Inhibited"],
    "Stimulation": ["Stimulator", "Stimulated"],
    "Biochemical Reaction": ["Reactant", "Modifier", "Product"],
    "Non-Covalent Binding": ["Reactant", "Product"],
    "Degradation": ["Reactant"],
    "Control": ["Modifier", "Modified"],
    "Genetic Production": ["Promoter", "Template", "Product"],
}
ROLES = {
    "Aptamer-DNA",
    "Inert-DNA-Spacer",
    "Promoter",
    "RBS",
    "CDS",
    "Terminator",
    "Operator",
    "Engineered-Region",
    "Primer-Binding-Site",
    "Origin-Of-Transfer",
    "Origin-Of-Replication",
}
RNA_ROLES = {"Aptamer-RNA", "Ncrna", "PolyA-Site", "mRNA"}
EXTERNAL_TYPES = {"Simple Chemical", "Protein", "Restriction Enzyme", "DNA", "RNA"}


def reject(path, message, status=422):
    raise CustomError(
        message,
        status,
        issues=[{"severity": "error", "path": path, "message": message}],
    )


def http_uri(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        uri = urlsplit(value)
        return uri.scheme in ("http", "https") and bool(uri.netloc)
    except ValueError:
        return False


def validate_namespace(value):
    """Require an explicit namespace, independent of pySBOL's process default."""
    if not isinstance(value, str):
        reject("namespace", "A namespace string is required", 400)
    message = (
        "Expected an absolute HTTP(S) namespace without credentials, whitespace, "
        "query, or fragment"
    )
    if (
        not value
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
        or any(c in value for c in "?#\\")
    ):
        reject("namespace", message)
    try:
        uri = urlsplit(value)
        valid = (
            uri.scheme in ("http", "https")
            and bool(uri.hostname)
            and uri.username is None
            and uri.password is None
        )
        # Accessing port rejects malformed and out-of-range port numbers.
        uri.port
    except ValueError:
        valid = False
    if not valid:
        reject("namespace", message)
    return value.rstrip("/")


def validate_create(data):
    if not isinstance(data, dict):
        reject("", "Expected a JSON object", 400)
    data = {**data, "namespace": validate_namespace(data.get("namespace"))}
    for key in ("components", "expressions", "interactions", "eds"):
        if not isinstance(data.get(key), list):
            reject(key, "Expected an array", 400)
    if len(data["components"]) < 2:
        reject("components", "A DNA design needs a parent and at least one part")
    names = set()
    physical_order = []
    definitions = {}
    parent = (
        data["components"][0].get("name")
        if isinstance(data["components"][0], dict)
        else None
    )
    for i, c in enumerate(data["components"]):
        path = f"components[{i}]"
        if not isinstance(c, dict):
            reject(path, "Expected an object", 400)
        name = c.get("name")
        role = c.get("role")
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", name
        ):
            reject(path + ".name", "Invalid SBOL displayId")
        if not isinstance(role, str):
            reject(path + ".role", "Expected a string", 400)
        if role not in ROLES:
            reject(
                path + ".role",
                "Physical DNA assembly requires a supported DNA role; put RNA species in eds",
            )
        if not isinstance(c.get("new"), bool):
            reject(path + ".new", "Expected a boolean", 400)
        if not http_uri(c.get("uri")):
            reject(path + ".uri", "Expected an absolute HTTP(S) URI")
        instance = c.get("instance_id", 1)
        if isinstance(instance, bool) or not isinstance(instance, int) or instance < 1:
            reject(path + ".instance_id", "Expected positive integer", 400)
        if not isinstance(c.get("description", ""), str):
            reject(path + ".description", "Expected a string", 400)
        sequence = c.get("sequence", "")
        if not isinstance(sequence, str):
            reject(path + ".sequence", "Expected a string", 400)
        if c["new"] and set(sequence.lower()) - set("acgtrykmswbdhvn"):
            reject(path + ".sequence", "Not IUPAC DNA")
        signature = (
            role,
            c["new"],
            sequence.lower() if c["new"] else "",
            c["uri"],
            c.get("description", "") if c["new"] else "",
        )
        if name in definitions and definitions[name] != signature:
            reject(path, "Conflicting definitions share a name")
        definitions[name] = signature
        if i:
            if name == parent:
                reject(path + ".name", "Part name collides with parent")
            ref = f"{name}_{instance}"
            if ref in names:
                reject(path, "Duplicate part reference")
            names.add(ref)
            physical_order.append(ref)
    all_names = set(definitions)
    for name in all_names:
        if name + "_seq" in all_names:
            reject(
                "components.name", "Name collides with a generated sequence identity"
            )
    if parent + "_sequence" in all_names or parent + "_system" in all_names:
        reject("components.name", "Name collides with a generated identity")
    species = set()
    for i, e in enumerate(data["eds"]):
        path = f"eds[{i}]"
        if not isinstance(e, dict):
            reject(path, "Expected an object", 400)
        if not isinstance(e.get("type"), str):
            reject(path + ".type", "Expected a string", 400)
        if e.get("type") not in EXTERNAL_TYPES:
            reject(path + ".type", "Unsupported species type")
        name = e.get("name")
        if not isinstance(name, str) or not name.strip() or name in names | species:
            reject(path + ".name", "Missing or ambiguous species name")
        if (
            not isinstance(e.get("uri", ""), str)
            or e.get("uri")
            and not http_uri(e["uri"])
        ):
            reject(path + ".uri", "Expected empty or absolute HTTP(S) URI")
        species.add(name)
    operon_names = set()
    for i, e in enumerate(data["expressions"]):
        path = f"expressions[{i}]"
        if (
            not isinstance(e, dict)
            or not isinstance(e.get("components"), list)
            or not isinstance(e.get("unions"), list)
        ):
            reject(path, "Invalid operon shape", 400)
        if (
            not isinstance(e.get("name"), str)
            or not e["name"].strip()
            or not e["components"]
        ):
            reject(path, "Operon needs a name and members")
        if e["name"] in names | species | operon_names:
            reject(
                path + ".name", "Operon name collides with another functional feature"
            )
        operon_names.add(e["name"])
        if not isinstance(e.get("constitutive"), bool):
            reject(path + ".constitutive", "Expected boolean", 400)
        for ref in e["components"]:
            if not isinstance(ref, str) or ref not in names:
                reject(path + ".components", "Unknown part reference")
        for u in e["unions"]:
            if not isinstance(u, dict):
                reject(path + ".unions", "Expected object", 400)
            if not isinstance(u.get("type"), str):
                reject(path + ".unions.type", "Expected a string", 400)
            if u.get("type") not in ("Order", "Regulate"):
                reject(path + ".unions.type", "Unknown union type")
            if (
                u.get("from") not in e["components"]
                or u.get("to") not in e["components"]
                or u["from"] == u["to"]
            ):
                reject(path + ".unions", "Endpoints must be distinct operon members")
            if physical_order.index(u["from"]) >= physical_order.index(u["to"]):
                reject(path + ".unions", "Union contradicts physical assembly order")
    for i, x in enumerate(data["interactions"]):
        path = f"interactions[{i}]"
        if not isinstance(x, dict):
            reject(path, "Expected object", 400)
        kind = x.get("type")
        participants = x.get("participants")
        if not isinstance(kind, str) or kind not in PARTICIPATIONS:
            reject(path + ".type", "Unknown interaction type")
        if not isinstance(participants, dict) or not participants:
            reject(path + ".participants", "Interaction needs participants")
        for role, refs in participants.items():
            if role not in PARTICIPATIONS[kind]:
                reject(
                    path + ".participants." + role,
                    "Role is incompatible with interaction type",
                )
            if not isinstance(refs, list) or not refs:
                reject(
                    path + ".participants." + role,
                    "Expected nonempty participant array",
                )
            for ref in refs:
                if not isinstance(ref, str) or ref not in names | species:
                    reject(path + ".participants." + role, "Unknown participant")
    return data
