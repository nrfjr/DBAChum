from fastapi import UploadFile

from app.core.exceptions import AppError


ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}


def _signature_matches(content_type: str, data: bytes) -> bool:
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


async def read_image_upload(upload: UploadFile, *, max_bytes: int = 2 * 1024 * 1024) -> tuple[str, bytes]:
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise AppError(
            "Use a PNG, JPEG, or WebP image.",
            code="UNSUPPORTED_IMAGE_TYPE",
            status_code=400,
        )

    data = await upload.read(max_bytes + 1)
    if not data:
        raise AppError(
            "The selected image is empty.",
            code="EMPTY_IMAGE",
            status_code=400,
        )
    if len(data) > max_bytes:
        raise AppError(
            "The image must be 2 MB or smaller.",
            code="IMAGE_TOO_LARGE",
            status_code=400,
        )
    if not _signature_matches(content_type, data):
        raise AppError(
            "The image content does not match its file type.",
            code="INVALID_IMAGE",
            status_code=400,
        )

    return content_type, data
