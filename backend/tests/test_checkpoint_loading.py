"""Model architecture creation must not download weights before checkpoint load."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture(params=["fasterrcnn_resnet50_fpn", "fasterrcnn_resnet50_fpn_v2"])
def detector_builder(request, monkeypatch):
    """Execute the actual builder source against a network-observable TorchVision fake."""
    name = request.param
    default_weights = object()
    model = SimpleNamespace(
        roi_heads=SimpleNamespace(
            box_predictor=SimpleNamespace(cls_score=SimpleNamespace(in_features=256))
        )
    )
    constructor = Mock(return_value=model)
    detection = SimpleNamespace(
        **{
            name: constructor,
            (
                "FasterRCNN_ResNet50_FPN_Weights"
                if name.endswith("_fpn")
                else "FasterRCNN_ResNet50_FPN_V2_Weights"
            ): SimpleNamespace(DEFAULT=default_weights),
        }
    )
    vision = ModuleType("torchvision")
    vision.models = SimpleNamespace(detection=detection)
    predictor = Mock(return_value=object())
    faster_rcnn = ModuleType("torchvision.models.detection.faster_rcnn")
    faster_rcnn.FastRCNNPredictor = predictor
    monkeypatch.setitem(sys.modules, "torchvision", vision)
    monkeypatch.setitem(
        sys.modules, "torchvision.models.detection.faster_rcnn", faster_rcnn
    )
    source = Path(__file__).resolve().parents[1] / "app/models" / (name + ".py")
    spec = importlib.util.spec_from_file_location("isolated_" + name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_model, constructor, predictor, model, default_weights


def test_full_checkpoint_architecture_disables_all_pretrained_downloads(
    detector_builder,
):
    build, constructor, predictor, model, _ = detector_builder
    assert build(num_classes=12, pretrained=False, coco_model=False) is model
    constructor.assert_called_once_with(weights=None, weights_backbone=None)
    predictor.assert_called_once_with(256, 12)
    assert model.roi_heads.box_predictor is predictor.return_value


def test_pretrained_default_behavior_is_preserved(detector_builder):
    build, constructor, predictor, model, default_weights = detector_builder
    assert build(num_classes=12) is model
    constructor.assert_called_once_with(weights=default_weights)
    predictor.assert_called_once_with(256, 12)


def test_coco_mode_preserves_head_without_downloading_when_disabled(detector_builder):
    build, constructor, predictor, model, _ = detector_builder
    original_head = model.roi_heads.box_predictor
    assert build(num_classes=12, pretrained=False, coco_model=True) is model
    constructor.assert_called_once_with(weights=None, weights_backbone=None)
    predictor.assert_not_called()
    assert model.roi_heads.box_predictor is original_head
