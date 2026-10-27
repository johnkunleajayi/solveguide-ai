import base64
import binascii
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from app.config import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS
from app.errors import VisionError
from app.schemas import VisionRequest


@dataclass(frozen=True, repr=False)
class ValidatedImage:
    data_base64: str
    width: int
    height: int


def validate_image(request: VisionRequest) -> ValidatedImage:
    if request.media_type != "image/png":
        raise VisionError("invalid_image_type", "Only PNG captures are supported.", 415)
    if len(request.image_base64) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise VisionError("image_too_large", "Capture exceeds the 10 MiB image limit.", 413)
    try:
        data = base64.b64decode(request.image_base64, validate=True)
    except (ValueError, binascii.Error):
        raise VisionError(
            "invalid_image", "The capture is not valid base64 PNG data.", 422
        ) from None
    if len(data) > MAX_IMAGE_BYTES:
        raise VisionError("image_too_large", "Capture exceeds the 10 MiB image limit.", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    raise VisionError(
                        "invalid_image_type", "A single-frame PNG capture is required.", 415
                    )
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                    raise VisionError(
                        "image_too_large", "Capture exceeds the 40 megapixel limit.", 413
                    )
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()  # Validate the actual decoder, not just a MIME label/header.
    except VisionError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise VisionError(
            "image_too_large", "Capture dimensions exceed the safe image limit.", 413
        ) from None
    except Exception:
        raise VisionError(
            "invalid_image", "The PNG capture is damaged or incomplete.", 422
        ) from None
    # Keep only canonical base64 in memory; never open a frontend-supplied path or URL.
    return ValidatedImage(base64.b64encode(data).decode("ascii"), width, height)
