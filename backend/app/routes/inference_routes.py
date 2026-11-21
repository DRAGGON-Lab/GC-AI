"""Bounded image admission; importing routes never imports Torch or OpenCV."""

import base64
import io
from threading import Lock
import warnings

from flask import Blueprint, current_app, jsonify, request

from app.utils.custom_error import CustomError

inference_blueprint = Blueprint("inference", __name__)
_admission = Lock()


def decode_image(content):
    """Inspect before allocation and decode one PNG/JPEG into three BGR channels."""
    import numpy as np
    from PIL import Image, UnidentifiedImageError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise CustomError(
                        "Upload an actual PNG or JPEG image", 422, code="invalid_image"
                    )
                if (
                    image.format == "PNG"
                    and not content.endswith(b"\x00\x00\x00\x00IEND\xaeB\x60\x82")
                    or image.format == "JPEG"
                    and not content.endswith(b"\xff\xd9")
                ):
                    raise CustomError(
                        "Image is truncated; upload a complete PNG or JPEG",
                        422,
                        code="invalid_image",
                    )
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or max(width, height)
                    > current_app.config.get("MAX_IMAGE_DIMENSION", 8192)
                    or width * height
                    > current_app.config.get("MAX_IMAGE_PIXELS", 16_000_000)
                ):
                    raise CustomError(
                        "Image dimensions exceed the configured limit",
                        413,
                        code="image_too_large",
                    )
                if getattr(image, "n_frames", 1) != 1:
                    raise CustomError(
                        "Upload a single-frame image", 422, code="invalid_image"
                    )
                # Verify PNG checksums without allocating pixels. JPEG load below
                # rejects truncated entropy data; no permissive decoder flags are set.
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                return np.array(image.convert("RGB"), dtype=np.uint8)[:, :, ::-1].copy()
    except CustomError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise CustomError(
            "Image dimensions exceed the configured limit", 413, code="image_too_large"
        ) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise CustomError(
            "Image is corrupt, truncated, or unsupported; upload a complete PNG or JPEG",
            422,
            code="invalid_image",
        ) from None


def run_inference(image):
    from app.config import get_model
    from app.models.inference import process_image

    return process_image(image, get_model())


@inference_blueprint.route("/", methods=["POST"])
def inference():
    if not _admission.acquire(blocking=False):
        raise CustomError(
            "Inference is busy; retry shortly",
            503,
            code="inference_busy",
            headers={
                "Retry-After": str(current_app.config.get("INFERENCE_RETRY_AFTER", 1))
            },
        )
    try:
        if "image" not in request.files:
            raise CustomError("Provide an image multipart field", 400)
        file = request.files["image"]
        if not file.filename:
            raise CustomError("No image file selected", 400)
        limit = current_app.config.get("MAX_IMAGE_BYTES", 10 * 1024 * 1024)
        content = file.read(limit + 1)
        if len(content) > limit:
            raise CustomError(
                "Image bytes exceed the configured limit", 413, code="image_too_large"
            )
        image = decode_image(content)
        runner = current_app.config.get("INFERENCE_RUNNER") or run_inference
        result_image, draw_boxes, pred_classes = runner(image)
        from PIL import Image

        encoded = io.BytesIO()
        Image.fromarray(result_image[:, :, ::-1]).save(encoded, format="PNG")
        boxes = (
            draw_boxes.tolist() if hasattr(draw_boxes, "tolist") else list(draw_boxes)
        )
        response = {
            "status": "success",
            "result_image": base64.b64encode(encoded.getvalue()).decode("ascii"),
            "draw_boxes": boxes,
            "pred_classes": pred_classes,
            "has_predictions": bool(boxes),
        }
        if not boxes:
            response["message"] = "No predictions made by the model."
        return jsonify(response)
    finally:
        _admission.release()
