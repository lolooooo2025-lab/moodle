"""Secure file storage (prompt §7.7).

Uploads are stored OUTSIDE the web root (config.STORAGE_DIR, never mounted as
static). They are served only through permission-checked endpoints. We validate
extension + magic bytes + size, store under a random opaque key (never the
user-supplied name), and resolve keys with a path-traversal guard.
"""
from __future__ import annotations
import secrets
import io
import zipfile
import hashlib
from pathlib import Path
from app import config

MAX_BYTES = 25 * 1024 * 1024   # 25 MB per file

# extension -> (mime, magic-prefixes or None for text)
ALLOWED = {
    ".pdf": ("application/pdf", [b"%PDF"]),
    ".png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".webp": ("image/webp", [b"RIFF"]),
    ".mp4": ("video/mp4", None),
    ".webm": ("video/webm", [b"\x1a\x45\xdf\xa3"]),
    ".gif": ("image/gif", [b"GIF87a", b"GIF89a"]),
    ".txt": ("text/plain; charset=utf-8", None),
    ".md": ("text/plain; charset=utf-8", None),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", [b"PK\x03\x04"]),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", [b"PK\x03\x04"]),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", [b"PK\x03\x04"]),
}


class FileError(Exception):
    def __init__(self, key: str):
        self.key = key
        super().__init__(key)


def _ext(name: str) -> str:
    return Path(name or "").suffix.lower()


def validate(filename: str, data: bytes) -> str:
    """Return the mime type, or raise FileError with an i18n key."""
    if not data:
        raise FileError("err.file_required")
    if len(data) > MAX_BYTES:
        raise FileError("err.upload_size")
    ext = _ext(filename)
    if ext not in ALLOWED:
        raise FileError("err.upload_type")
    mime, magics = ALLOWED[ext]
    if magics is not None and not any(data.startswith(m) for m in magics):
        raise FileError("err.upload_type")
    if ext == ".webp" and (len(data) < 12 or data[8:12] != b"WEBP"):
        raise FileError("err.upload_type")
    if ext == ".mp4" and (len(data) < 12 or data[4:8] != b"ftyp"
                          or data[8:12] not in (b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"dash", b"M4V ")):
        raise FileError("err.upload_type")
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(data)) as im:
                fmt = im.format
                if im.width * im.height > 40_000_000:
                    raise FileError("err.upload_type")
                im.verify()
            expected = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "gif": "GIF"}
            if fmt != expected[ext[1:]]:
                raise FileError("err.upload_type")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise FileError("err.upload_type")
    if ext in (".docx", ".xlsx", ".pptx"):
        member = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml",
                  ".pptx": "ppt/presentation.xml"}[ext]
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if (member not in z.namelist() or "[Content_Types].xml" not in z.namelist()
                        or sum(i.file_size for i in z.infolist()) > 100 * 1024 * 1024):
                    raise FileError("err.upload_type")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise FileError("err.upload_type")
    if magics is None:
        # text must be decodable (blocks disguised binaries)
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise FileError("err.upload_type")
    return mime


def save(subdir: str, filename: str, data: bytes) -> dict:
    """Validate + store; return {key, file_name, file_size, mime}."""
    mime = validate(filename, data)
    ext = _ext(filename)
    key = f"{subdir}/{secrets.token_hex(16)}{ext}"
    dest = config.STORAGE_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"key": key, "file_name": Path(filename).name[:255],
            "file_size": len(data), "mime": mime, "sha256": hashlib.sha256(data).hexdigest()}


def resolve(key: str) -> Path:
    """Resolve a storage key to a real path, guarding against traversal."""
    if not key:
        raise FileError("err.not_found")
    base = config.STORAGE_DIR.resolve()
    path = (base / key).resolve()
    if not str(path).startswith(str(base) + "/") and path != base:
        raise FileError("err.not_found")
    if not path.is_file():
        raise FileError("err.not_found")
    return path


def delete(key: str):
    try:
        resolve(key).unlink(missing_ok=True)
    except FileError:
        pass


async def read_upload(upload) -> bytes:
    """Bounded read: never allocate an unbounded client upload in memory."""
    data = await upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise FileError("err.upload_size")
    return data


def gateway(path: Path, name: str, mime: str, *, inline: bool = False):
    """Private file gateway. Only verified image/video formats may render inline."""
    from fastapi.responses import FileResponse
    safe_inline = {"image/png", "image/jpeg", "image/webp", "image/gif", "video/mp4", "video/webm"}
    render = inline and mime in safe_inline
    return FileResponse(path, media_type=mime if render else "application/octet-stream",
                        filename=name, content_disposition_type="inline" if render else "attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
