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

@pytest.mark.parametrize('expected', [None, '', 'bad', '0' * 63, 'g' * 64, '0' * 64])
def test_real_loader_rejects_unverified_checkpoint_before_deserialization(tmp_path, monkeypatch, expected):
    from app import config
    path = tmp_path / 'model.pth'
    path.write_bytes(b'tampered pickle bytes')
    monkeypatch.setattr(config, 'MODEL_PATH', str(path))
    if expected is None:
        monkeypatch.delenv('GCAI_EXPECTED_CHECKPOINT_SHA256', raising=False)
    else:
        monkeypatch.setenv('GCAI_EXPECTED_CHECKPOINT_SHA256', expected)
    torch = ModuleType('torch')
    torch.load = Mock(side_effect=AssertionError('unverified data reached deserialization'))
    torch.device = Mock()
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, 'torch', torch)
    models = ModuleType('app.models.create_fasterrcnn_model')
    models.create_model = {}
    monkeypatch.setitem(sys.modules, models.__name__, models)
    with pytest.raises(Exception):
        config.load_model()
    torch.load.assert_not_called()


def test_real_loader_hashes_rewinds_and_deserializes_the_same_open_stream(tmp_path, monkeypatch):
    import hashlib
    from app import config
    content = b'approved checkpoint'
    path = tmp_path / 'model.pth'
    path.write_bytes(content)
    monkeypatch.setattr(config, 'MODEL_PATH', str(path))
    monkeypatch.setenv('GCAI_EXPECTED_CHECKPOINT_SHA256', hashlib.sha256(content).hexdigest())
    model = Mock()
    model.to.return_value.eval.return_value = model
    def load(stream, **kwargs):
        assert not isinstance(stream, (str, Path))
        assert stream.tell() == 0
        # Replacing the pathname cannot change the already verified descriptor.
        replacement = tmp_path / 'replacement'
        replacement.write_bytes(b'untrusted')
        replacement.replace(path)
        assert stream.read() == content
        assert kwargs['weights_only'] is False
        return {'model_name': 'test', 'model_state_dict': {}}
    torch = ModuleType('torch')
    torch.device = Mock()
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    torch.load = Mock(side_effect=load)
    monkeypatch.setitem(sys.modules, 'torch', torch)
    models = ModuleType('app.models.create_fasterrcnn_model')
    models.create_model = {'test': Mock(return_value=model)}
    monkeypatch.setitem(sys.modules, models.__name__, models)
    assert config.load_model() is model
    torch.load.assert_called_once()
