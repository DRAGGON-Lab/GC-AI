"""Independent synthetic fixtures validate metrics, never detector accuracy."""

from pathlib import Path
import sys

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from corpus import digest, corpus_identity, validate
from evaluate import evaluate
from prepare import prepare
from settings import EFFECTIVE_OPERATING_THRESHOLD


@pytest.fixture
def fixture(tmp_path):
    import yaml

    root = Path(__file__).resolve().parents[2]
    classes = yaml.safe_load((root / "backend/app/data_configs/glyphs.yaml").read_text())["CLASSES"][1:]
    path = tmp_path / "development.png"
    Image.new("RGB", (100, 100), "white").save(path)
    coco = {
        "info": {},
        "development_fixture": True,
        "categories": [{"id": index + 1, "name": name} for index, name in enumerate(classes)],
        "images": [
            {
                "id": 1,
                "file_name": path.name,
                "family_id": "dev-1",
                "condition": "digital",
                "width": 100,
                "height": 100,
                "sha256": digest(path),
                "annotator": "synthetic fixture author",
                "provenance": "Pillow synthetic fixture",
                "reuse_rights": "CC0",
                "approved_by": "test fixture",
                "approved_at": "2026-11-24",
                "approved": True,
                "independently_labeled": True,
            }
        ],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 2,
                "bbox": [10, 10, 20, 20],
                "area": 400,
                "iscrowd": 0,
                "reading_order": 0,
            }
        ],
    }
    record = {
        "development_fixture": True,
        "source_revision": "a" * 40,
        "environment_revision": "b" * 40,
        "checkpoint_sha256": "c" * 64,
        "corpus_sha256": corpus_identity(coco),
        "settings": {
            "score_floor": 0.001,
            "operating_threshold": 0.7,
            "overlap_suppression": 0.3,
            "coco_max_dets": [1, 10, 100],
            "operating_point_parity": True,
            "score_dtype": "float32",
            "effective_operating_threshold": EFFECTIVE_OPERATING_THRESHOLD,
        },
        "predictions": [{"image_id": 1, "category_id": 2, "bbox": [10, 10, 20, 20], "score": 0.9}],
    }
    return coco, record, tmp_path


def test_official_evaluator_perfect_fixture_and_no_support_na(fixture):
    coco, record, images = fixture
    report = evaluate(coco, record, images, qualification=False)
    cds = report["per_class"][1]
    assert cds["tp"] == 1 and cds["fp"] == cds["fn"] == 0
    assert cds["precision"] == cds["recall"] == cds["f1"] == 1
    assert cds["ap50"] == pytest.approx(1)
    assert report["per_class"][0]["recall"] is None
    assert report["evidence_kind"] == "development_evaluator_test"
    assert report["qualification_data_complete"] is False


def test_official_evaluator_misses_and_fp_and_low_score_ranking(fixture):
    coco, record, images = fixture
    record["predictions"][0]["score"] = 0.6
    record["predictions"].append({"image_id": 1, "category_id": 2, "bbox": [60, 60, 20, 20], "score": 0.8})
    report = evaluate(coco, record, images, qualification=False)
    cds = report["per_class"][1]
    assert (cds["tp"], cds["fp"], cds["fn"]) == (0, 1, 1)
    assert cds["f1"] == 0
    assert cds["ap50"] == pytest.approx(0.5)
    assert len(report["errors"]["missed_glyphs"]) == 1


def test_empty_predictions_have_zero_recall_without_fabricated_precision(fixture):
    coco, record, images = fixture
    record["predictions"] = []
    cds = evaluate(coco, record, images, qualification=False)["per_class"][1]
    assert cds["precision"] is None and cds["recall"] == cds["f1"] == 0
    assert cds["ap50"] == 0


@pytest.mark.parametrize("change", ["unapproved", "prediction_labels", "hash", "dimensions", "invalid_box"])
def test_missing_scientific_prerequisites_fail_even_in_development(fixture, change):
    coco, record, images = fixture
    if change == "unapproved":
        coco["images"][0]["approved"] = False
    if change == "prediction_labels":
        coco["images"][0]["independently_labeled"] = False
    if change == "hash":
        coco["images"][0]["sha256"] = "0" * 64
    if change == "dimensions":
        coco["images"][0]["width"] = 200
    if change == "invalid_box":
        coco["annotations"][0]["bbox"][0] = -1
    with pytest.raises(ValueError):
        validate(coco, images, qualification=False)


def test_development_fixture_never_qualifies(fixture):
    coco, record, images = fixture
    with pytest.raises(ValueError, match="Development"):
        evaluate(coco, record, images)
    coco["development_fixture"] = False
    with pytest.raises(ValueError, match="80 images"):
        evaluate(coco, record, images)


def test_twenty_new_families_have_four_conditions_and_required_design_support(tmp_path):
    inventory = prepare(tmp_path / "draft")
    assert len(inventory["families"]) == 20
    assert len(inventory["images"]) == 80
    for category in inventory["categories"]:
        assert sum(category["name"] in family["classes"] for family in inventory["families"]) >= 5
    sources = list((tmp_path / "draft/sources").glob("*.svg"))
    assert len(sources) == len({source.read_bytes() for source in sources}) == 20
    assert len({tuple(family["classes"]) for family in inventory["families"]}) == 20


def test_float32_operating_boundary_matches_deployed_comparator(fixture):
    import numpy as np

    coco, record, images = fixture
    score = float(np.float32(0.7))
    assert score < 0.7
    assert bool((np.array([score], dtype=np.float32) >= 0.7)[0])
    record["predictions"][0]["score"] = score
    result = evaluate(coco, record, images, qualification=False)["per_class"][1]
    assert result["tp"] == 1 and result["recall"] == 1


@pytest.mark.parametrize("identity", [0, -1, True, 1.5])
def test_coco_unmatched_sentinel_and_invalid_ids_are_rejected(fixture, identity):
    coco, record, images = fixture
    coco["annotations"][0]["id"] = identity
    with pytest.raises(ValueError, match="positive integers"):
        validate(coco, images, qualification=False)


def test_official_evaluation_does_not_mutate_approved_corpus_or_prediction_identity(fixture):
    import copy
    coco,record,images=fixture
    original_coco,original_record=copy.deepcopy(coco),copy.deepcopy(record)
    result=evaluate(coco,record,images,qualification=False)
    assert coco==original_coco and record==original_record
    assert result['corpus_sha256']==record['corpus_sha256']
