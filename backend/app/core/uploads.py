"""Content sniffing for uploaded files so a renamed file cannot pass as a PDF/image."""
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),
    ".doc": (b"\xd0\xcf\x11\xe0",),
    ".xls": (b"\xd0\xcf\x11\xe0",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06"),
}


def content_matches_extension(extension: str, data: bytes) -> bool:
    signatures = _SIGNATURES.get(extension.lower())
    if signatures is None:
        return False
    if extension.lower() == ".webp" and data[8:12] != b"WEBP":
        return False
    return data.startswith(signatures)
