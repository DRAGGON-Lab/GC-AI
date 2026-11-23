"""Real image decoding at the HTTP boundary, without a detector checkpoint."""

import io
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import numpy as np
from PIL import Image
import pytest

from app import create_app


def image_bytes(mode="RGB", size=(8, 6), format="PNG"):
    stream = io.BytesIO()
    Image.new(mode, size).save(stream, format=format)
    return stream.getvalue()


@pytest.fixture
def inference_app():
    runner = Mock(side_effect=lambda image: (image, [], []))
    app = create_app(
        {
            "TESTING": True,
            "INFERENCE_RUNNER": runner,
            "MAX_CONTENT_LENGTH": 12 * 1024 * 1024,
        }
    )
    return app, runner


def upload(app, content, filename="anything.bin"):
    return app.test_client().post(
        "/inference/", data={"image": (io.BytesIO(content), filename)}
    )


@pytest.mark.parametrize(
    "mode,format",
    [("RGB", "PNG"), ("RGBA", "PNG"), ("P", "PNG"), ("L", "JPEG"), ("CMYK", "JPEG")],
)
def test_real_images_normalize_once_before_runner(inference_app, mode, format):
    app, runner = inference_app
    response = upload(app, image_bytes(mode, format=format))
    assert response.status_code == 200, response.json
    assert response.json["has_predictions"] is False
    decoded = runner.call_args.args[0]
    assert decoded.shape == (6, 8, 3)
    assert decoded.dtype == np.uint8


@pytest.mark.parametrize(
    "content",
    [
        b"not an image",
        b"",
        image_bytes()[:-1],
        image_bytes()[:-15],
        image_bytes(format="JPEG")[:-2],
        image_bytes(format="JPEG")[:-30],
        image_bytes(format="GIF"),
        image_bytes(format="TIFF"),
    ],
)
def test_invalid_images_never_run_model(inference_app, content):
    app, runner = inference_app
    response = upload(app, content, "image.png")
    assert response.status_code == 422, response.json
    assert response.json["code"] == "invalid_image"
    runner.assert_not_called()


def test_animation_rejected(inference_app):
    app, runner = inference_app
    stream = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        stream,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (4, 4), "blue")],
    )
    assert upload(app, stream.getvalue()).status_code == 422
    runner.assert_not_called()


@pytest.mark.parametrize(
    "setting,value",
    [("MAX_IMAGE_BYTES", 20), ("MAX_IMAGE_PIXELS", 47), ("MAX_IMAGE_DIMENSION", 7)],
)
def test_image_limits_reject_before_inference(inference_app, setting, value):
    app, runner = inference_app
    app.config[setting] = value
    assert upload(app, image_bytes()).status_code == 413
    runner.assert_not_called()


def test_exact_boundaries_accepted(inference_app):
    app, _ = inference_app
    content = image_bytes()
    app.config.update(
        MAX_IMAGE_BYTES=len(content), MAX_IMAGE_PIXELS=48, MAX_IMAGE_DIMENSION=8
    )
    assert upload(app, content).status_code == 200


def test_request_limit_and_multipart_errors(inference_app):
    app, runner = inference_app
    assert app.test_client().post("/inference/", data={}).status_code == 400
    assert upload(app, image_bytes(), filename="").status_code == 400
    app.config["MAX_CONTENT_LENGTH"] = 50
    assert upload(app, image_bytes()).status_code == 413
    runner.assert_not_called()


def test_busy_admission_and_failure_recovery(inference_app):
    app, runner = inference_app
    entered, release = Event(), Event()

    def block(image):
        entered.set()
        assert release.wait(5)
        raise RuntimeError("/private/checkpoint secret")

    runner.side_effect = block
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(upload, app, image_bytes())
        try:
            assert entered.wait(5)
            busy = upload(app, image_bytes())
            assert busy.status_code == 503
            assert busy.json["code"] == "inference_busy"
            assert busy.headers["Retry-After"] == "1"
        finally:
            release.set()
        failed = first.result(timeout=5)
    assert failed.status_code == 500
    assert b"secret" not in failed.data
    runner.side_effect = lambda image: (image, [], [])
    assert upload(app, image_bytes()).status_code == 200


def test_rejected_uploads_release_admission(inference_app):
    app, runner = inference_app
    assert upload(app, b"corrupt").status_code == 422
    assert app.test_client().post("/inference/", data={}).status_code == 400
    app.config["MAX_IMAGE_BYTES"] = 1
    assert upload(app, image_bytes()).status_code == 413
    app.config["MAX_IMAGE_BYTES"] = 10 * 1024 * 1024
    assert upload(app, image_bytes()).status_code == 200
    assert runner.call_count == 1


def test_channel_order_is_preserved_for_detector(inference_app):
    app, runner = inference_app
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (11, 22, 33)).save(stream, format="PNG")
    assert upload(app, stream.getvalue()).status_code == 200
    assert runner.call_args.args[0][0, 0].tolist() == [33, 22, 11]


def test_dimensions_checked_before_pixel_decode(inference_app, monkeypatch):
    app, runner = inference_app
    content = image_bytes(size=(9, 6))
    app.config["MAX_IMAGE_DIMENSION"] = 8
    monkeypatch.setattr(
        Image.Image,
        "load",
        Mock(side_effect=AssertionError("pixels allocated before limits")),
    )
    assert upload(app, content).status_code == 413
    runner.assert_not_called()


def test_camera_jpeg_exif_orientation_reaches_detector_upright(inference_app):
    """EXIF 6 rotates stored landscape pixels clockwise into displayed portrait."""
    import base64

    app, runner = inference_app
    source = Image.new("RGB", (24, 12), (255, 0, 0))
    source.paste((0, 255, 0), (12, 0, 24, 12))
    exif = Image.Exif()
    exif[274] = 6
    stream = io.BytesIO()
    source.save(stream, format="JPEG", quality=100, subsampling=0, exif=exif)

    response = upload(app, stream.getvalue(), "camera.jpg")
    assert response.status_code == 200, response.json
    decoded = runner.call_args.args[0]
    assert decoded.shape == (24, 12, 3)
    # After clockwise rotation the red half is above the green half. Check
    # interior pixels with room for JPEG rounding and the detector's BGR order.
    assert decoded[3, 6, 2] > 240 and decoded[3, 6, :2].max() < 15
    assert decoded[20, 6, 1] > 240 and decoded[20, 6, [0, 2]].max() < 15
    annotated = Image.open(io.BytesIO(base64.b64decode(response.json["result_image"])))
    assert annotated.size == (12, 24)
    np.testing.assert_array_equal(np.array(annotated), decoded[:, :, ::-1])
