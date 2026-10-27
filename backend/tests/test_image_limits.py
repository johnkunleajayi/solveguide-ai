import base64
import struct
import zlib

from app.config import MAX_IMAGE_PIXELS


def test_png_dimensions_are_checked_before_pixel_allocation(api_factory):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", MAX_IMAGE_PIXELS + 1, 1, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )
    response = api_factory().post(
        "/api/v1/vision/question",
        json={"media_type": "image/png", "image_base64": base64.b64encode(data).decode()},
    )
    assert response.status_code == 413


def test_damaged_png_is_not_accepted_by_mime_header(api_factory, image_payload):
    data = bytearray(base64.b64decode(image_payload["image_base64"]))
    data[-5] ^= 0xFF
    image_payload["image_base64"] = base64.b64encode(data).decode()
    response = api_factory().post("/api/v1/vision/question", json=image_payload)
    assert response.status_code == 422
