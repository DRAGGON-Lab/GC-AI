"""Local conversion with explicit support for the generated assembly representation.

sbol-utilities 1.0a17's local converter omits SubComponents and uses a removed
Biopython strand argument. Extend only its feature projection; retain its local
record/sequence conversion and bundled SO mapping, without ontology requests.
"""

import sbol3
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from sbol_utilities.sbol3_genbank_conversion import GenBankSBOL3Converter
from app.utils.validation import reject


def preflight(doc):
    components = [o for o in doc.objects if isinstance(o, sbol3.Component)]
    if not components:
        reject(
            "structural_handle",
            "Conversion requires at least one sequence-bearing component",
        )
    for component in components:
        if len(component.sequences) != 1:
            reject(
                "structural_handle",
                "Conversion requires exactly one complete DNA sequence for every component",
            )
        sequence = component.sequences[0].lookup()
        if (
            not isinstance(sequence, sbol3.Sequence)
            or not sequence.elements
            or sequence.encoding != sbol3.IUPAC_DNA_ENCODING
            or set(sequence.elements.lower()) - set("acgtrykmswbdhvn")
        ):
            reject(
                "structural_handle",
                "Conversion requires a complete IUPAC DNA sequence for every component",
            )
        for feature in component.features:
            if feature.orientation is not None:
                reject(
                    "structural_handle",
                    "Feature-level orientation is not supported; express orientation on its Range",
                )
            if (
                not isinstance(feature, (sbol3.SubComponent, sbol3.SequenceFeature))
                or len(feature.locations) != 1
            ):
                reject(
                    "structural_handle",
                    "Conversion supports sequence features and subcomponents with one explicit Range",
                )
            location = feature.locations[0]
            if (
                not isinstance(location, sbol3.Range)
                or str(location.sequence) != sequence.identity
                or not 1 <= location.start <= location.end <= len(sequence.elements)
                or location.orientation
                not in (
                    None,
                    sbol3.SBOL_INLINE,
                    sbol3.SO_FORWARD,
                    sbol3.SBOL_REVERSE_COMPLEMENT,
                    sbol3.SO_REVERSE,
                )
            ):
                reject(
                    "structural_handle",
                    "Conversion requires valid sequence coordinates and a supported orientation",
                )
            if isinstance(feature, sbol3.SubComponent):
                child = feature.instance_of.lookup()
                if not isinstance(child, sbol3.Component) or len(child.sequences) != 1:
                    reject(
                        "structural_handle",
                        "Conversion requires resolved sequence-bearing subcomponents",
                    )
                child_sequence = child.sequences[0].lookup()
                if (
                    not isinstance(child_sequence, sbol3.Sequence)
                    or not child_sequence.elements
                ):
                    reject(
                        "structural_handle",
                        "Conversion requires complete subcomponent sequences",
                    )
                if feature.source_locations:
                    reject(
                        "structural_handle",
                        "Conversion of sliced subcomponents is not supported",
                    )
                expected = child_sequence.elements.lower()
                if location.orientation in (
                    sbol3.SO_REVERSE,
                    sbol3.SBOL_REVERSE_COMPLEMENT,
                ):
                    expected = str(Seq(expected).reverse_complement())
                if (
                    sequence.elements[location.start - 1 : location.end].lower()
                    != expected
                ):
                    reject(
                        "structural_handle",
                        "Subcomponent coordinates must match its complete sequence",
                    )
    return components


class AssemblyGenBankConverter(GenBankSBOL3Converter):
    def _handle_features_sbol_to_gb(self, record, component):
        for feature in component.features:
            location = feature.locations[0]  # preflight guarantees one supported range
            source = (
                feature.instance_of.lookup()
                if isinstance(feature, sbol3.SubComponent)
                else feature
            )
            roles = list(feature.roles) or list(source.roles)
            feature_type = next(
                (self.so2gb_map[r] for r in roles if r in self.so2gb_map),
                "misc_feature",
            )
            reverse = location.orientation in (
                sbol3.SO_REVERSE,
                sbol3.SBOL_REVERSE_COMPLEMENT,
            )
            record.features.append(
                SeqFeature(
                    location=FeatureLocation(
                        location.start - 1, location.end, strand=-1 if reverse else 1
                    ),
                    type=feature_type,
                    qualifiers={"label": [feature.name or source.display_id]},
                )
            )


def convert_to_genbank(doc, path):
    converter = AssemblyGenBankConverter()
    result = converter.convert_sbol3_to_genbank(
        sbol3_file=None, doc=doc, gb_file=path, write=True
    )
    return result["seqrecords"]


def verify_artifact(contents, format_name, components):
    """Reject silent converter losses before any ZIP can be published."""
    import io

    records = list(SeqIO.parse(io.StringIO(contents.decode("utf-8")), format_name))
    expected = {c.display_id: c for c in components}
    observed = {}
    for record in records:
        key = record.id.rsplit(".", 1)[0] if format_name == "genbank" else record.id
        if key in observed or key not in expected or not record.seq:
            raise ValueError("Converter returned unexpected or empty records")
        component = expected[key]
        if str(record.seq).lower() != component.sequences[0].lookup().elements.lower():
            raise ValueError("Converter lost sequence data")
        if format_name == "genbank":
            expected_ranges = sorted(
                (
                    f.locations[0].start - 1,
                    f.locations[0].end,
                    (
                        -1
                        if f.locations[0].orientation
                        in (sbol3.SO_REVERSE, sbol3.SBOL_REVERSE_COMPLEMENT)
                        else 1
                    ),
                )
                for f in component.features
            )
            actual_ranges = sorted(
                (int(f.location.start), int(f.location.end), f.location.strand)
                for f in record.features
            )
            if expected_ranges != actual_ranges:
                raise ValueError("Converter lost feature coordinates")
        observed[key] = record
    if set(observed) != set(expected):
        raise ValueError("Converter returned an incomplete artifact")
