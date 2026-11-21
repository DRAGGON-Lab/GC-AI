import sbol3
from app.utils.validation import reject


def add_biobrick_scar(next_sequence):
    return "tactag" if next_sequence.lower().startswith("at") else "tactagag"


def calculate_seq_with_scars(parent_component, components):
    """Assemble only fully sequenced DNA; unknown bases leave structural ordering."""
    if sbol3.SBO_DNA not in parent_component.types:
        reject("components[0]", "Assembly parent must be DNA")
    sequences = []
    for sub in components:
        component = sub.instance_of.lookup()
        if sbol3.SBO_DNA not in component.types or sbol3.SBO_RNA in component.types:
            reject("components", "Assembly members must be DNA")
        if len(component.sequences) > 1:
            reject("components", "Assembly part has ambiguous sequences")
        seq = component.sequences[0].lookup() if component.sequences else None
        if seq and (
            seq.encoding != sbol3.IUPAC_DNA_ENCODING
            or set(seq.elements.lower()) - set("acgtrykmswbdhvn")
        ):
            reject("components.sequence", "Expected IUPAC DNA sequence")
        sequences.append(seq.elements.lower() if seq else "")
    if not sequences or not all(sequences):
        return None
    sequence = sbol3.Sequence(
        parent_component.identity + "_sequence",
        elements="",
        encoding=sbol3.IUPAC_DNA_ENCODING,
    )
    for i, (sub, bases) in enumerate(zip(components, sequences)):
        if i:
            sequence.elements += add_biobrick_scar(bases)
        start = len(sequence.elements) + 1
        sequence.elements += bases
        sub.locations.append(sbol3.Range(sequence, start, len(sequence.elements)))
    parent_component.document.add(sequence)
    parent_component.sequences.append(sequence)
    return sequence
