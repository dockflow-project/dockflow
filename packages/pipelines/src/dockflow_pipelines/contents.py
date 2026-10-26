"""Bounded read-only artifact previews, never an arbitrary URI/file gateway."""

from __future__ import annotations

import base64
import codecs
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import stat
import struct
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from dockflow_core.errors import DockflowError

from .artifacts import _relative_path

CSV_BYTES = 1024 * 1024
RECORD_BYTES = 128 * 1024
JSON_BYTES = 2 * 1024 * 1024
IMAGE_BYTES = 8 * 1024 * 1024
TEXT_BYTES = 64 * 1024
JSON_NODES = 20000


def fail(message, code="INVALID_ARGUMENT", status=400):
    raise DockflowError(message, code, status)


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _stat(value):
    return [
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    ]


def _open_file(path):
    """Walk every component through directory descriptors without following links."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    parent = os.open("/", flags | os.O_DIRECTORY)
    try:
        parts = path.parts[1:]
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent)
            os.close(parent)
            parent = child
        descriptor = os.open(parts[-1], flags, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        fail("Preview requires a regular file", "PERMISSION_DENIED", 403)
    return descriptor


class _Source:
    def __init__(self, manager, uri, expected_size):
        scheme, bucket, parts = manager._admit(uri)
        self.fd = None
        self.client = None
        self.bucket, self.key = bucket, "/".join(parts)
        if scheme == "file":
            path = Path(unquote(urlsplit(uri).path)).absolute()
            if path.is_relative_to(manager.control.state):
                fail(
                    "Control-state files cannot be previewed", "PERMISSION_DENIED", 403
                )
            self.fd = _open_file(path)
            self.observed = _stat(os.fstat(self.fd))
            self.size = self.observed[2]
        else:
            self.client = manager._s3()
            head = self.client.head_object(Bucket=bucket, Key=self.key)
            if not head.get("ETag"):
                fail("Storage lacks a stable object validator", "UNAVAILABLE", 503)
            self.etag, self.version = head["ETag"], head.get("VersionId")
            self.size = head["ContentLength"]
            self.observed = [self.etag, self.version, self.size]
        self.identity = _identity(self.observed)
        if self.size != expected_size:
            self.close()
            fail(
                "File size differs from the registered artifact; refresh or check its integrity",
                "CONFLICT",
                409,
            )

    def read(self, offset, length):
        count = min(length, max(0, self.size - offset))
        if not count:
            return b""
        if self.fd is not None:
            return os.pread(self.fd, count, offset)
        arguments = {
            "Bucket": self.bucket,
            "Key": self.key,
            "Range": f"bytes={offset}-{offset + count - 1}",
            "IfMatch": self.etag,
        }
        if self.version:
            arguments["VersionId"] = self.version
        assert self.client is not None
        response = self.client.get_object(**arguments)
        body = response["Body"]
        try:
            if (
                response.get("ContentRange")
                != f"bytes {offset}-{offset + count - 1}/{self.size}"
                or response.get("ContentLength") != count
                or response.get("ETag") != self.etag
                or (self.version and response.get("VersionId") != self.version)
            ):
                fail(
                    "Storage did not honor the bounded conditional read",
                    "CONFLICT",
                    409,
                )
            data = body.read(count + 1)
            if len(data) != count:
                fail("Storage returned an incomplete byte range", "CONFLICT", 409)
            return data
        finally:
            body.close()

    def close(self):
        if self.fd is not None:
            descriptor, self.fd = self.fd, None
            try:
                if _stat(os.fstat(descriptor)) != self.observed:
                    fail("File changed during preview; start again", "CONFLICT", 409)
            finally:
                os.close(descriptor)


@contextmanager
def _source(manager, uri, expected_size):
    source = None
    try:
        source = _Source(manager, uri, expected_size)
        yield source
    except DockflowError:
        raise
    except FileNotFoundError:
        fail("Artifact file is missing", "NOT_FOUND", 404)
    except PermissionError:
        fail("Artifact file is inaccessible", "PERMISSION_DENIED", 403)
    except OSError:
        fail(
            "Artifact path is inaccessible, unsafe or changed", "PERMISSION_DENIED", 403
        )
    except Exception as error:
        code = str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}:
            fail("Artifact object is missing", "NOT_FOUND", 404)
        if code in {"412", "PreconditionFailed"}:
            fail("Artifact object changed; start again", "CONFLICT", 409)
        if code in {"403", "AccessDenied"}:
            fail("Artifact object is inaccessible", "PERMISSION_DENIED", 403)
        fail("Artifact storage cannot provide a bounded preview", "UNAVAILABLE", 503)
    finally:
        if source:
            source.close()


class _Number(str):
    pass


class _Object(list):
    pass


def json_tree(text):
    """Preserve property order/duplicates and numeric spelling without JS rounding."""

    def constant(_):
        raise ValueError("Non-finite JSON number")

    try:
        value = json.loads(
            text,
            parse_int=_Number,
            parse_float=_Number,
            parse_constant=constant,
            object_pairs_hook=_Object,
        )
        remaining = JSON_NODES

        def node(value, depth=0):
            nonlocal remaining
            remaining -= 1
            if remaining < 0 or depth > 64:
                fail(
                    "JSON preview exceeds 20,000 nodes or 64 levels",
                    "PREVIEW_LIMIT",
                    413,
                )
            if isinstance(value, _Number):
                return {"kind": "number", "value": str(value)}
            if isinstance(value, list):
                pairs = value if isinstance(value, _Object) else enumerate(value)
                return {
                    "kind": "object" if isinstance(value, _Object) else "array",
                    "children": [
                        {
                            "key": json.dumps(key, ensure_ascii=True)
                            if isinstance(value, _Object)
                            else str(key),
                            "node": node(child, depth + 1),
                        }
                        for key, child in pairs
                    ],
                }
            return {
                "kind": "null"
                if value is None
                else "boolean"
                if isinstance(value, bool)
                else "string",
                "value": json.dumps(value, ensure_ascii=True)
                if isinstance(value, str)
                else value,
            }

        return node(value)
    except RecursionError:
        fail("JSON exceeds the preview nesting limit", "PREVIEW_LIMIT", 413)
    except ValueError:
        fail("File is not valid bounded JSON", "INVALID_CONTENT", 422)


def image_info(data):
    """Recognize raster containers and reject unreasonable decoded canvas sizes."""
    mime = None
    width = height = 0
    if (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        and len(data) >= 24
        and data[12:16] == b"IHDR"
    ):
        mime = "image/png"
        width, height = struct.unpack(">II", data[16:24])
    elif data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        mime = "image/gif"
        width, height = struct.unpack("<HH", data[6:10])
    elif data.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 4 <= len(data):
            if data[offset] != 255:
                break
            marker = data[offset + 1]
            if marker == 255:
                offset += 1
                continue
            if marker in {0xD8, 0xD9}:
                offset += 2
                continue
            size = int.from_bytes(data[offset + 2 : offset + 4], "big")
            if size < 2 or offset + 2 + size > len(data):
                break
            if (
                marker
                in {
                    0xC0,
                    0xC1,
                    0xC2,
                    0xC3,
                    0xC5,
                    0xC6,
                    0xC7,
                    0xC9,
                    0xCA,
                    0xCB,
                    0xCD,
                    0xCE,
                    0xCF,
                }
                and size >= 7
            ):
                height, width = struct.unpack(">HH", data[offset + 5 : offset + 9])
                mime = "image/jpeg"
                break
            offset += size + 2
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 20:
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width, height = (
                int.from_bytes(data[i : i + 2], "little") & 0x3FFF for i in (26, 28)
            )
        elif chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if width and height:
            mime = "image/webp"
    if not mime:
        fail(
            "This file is not a supported PNG, JPEG, GIF or WebP raster image",
            "INVALID_CONTENT",
            422,
        )
    if (
        not width
        or not height
        or max(width, height) > 16384
        or width * height > 40_000_000
    ):
        fail(
            "Image exceeds the 16,384-pixel side or 40-megapixel preview limit",
            "PREVIEW_LIMIT",
            413,
        )
    return mime, width, height


class ArtifactContents:
    def __init__(self, manager):
        self.manager = manager
        self.secret = secrets.token_bytes(32)

    def _token(self, scope, identity, offset, row=0):
        body = json.dumps(
            [scope, identity, offset, row], separators=(",", ":")
        ).encode()
        return base64.urlsafe_b64encode(
            body + hmac.digest(self.secret, body, "sha256")
        ).decode()

    def _position(self, token, scope, identity):
        if not token:
            return None
        try:
            if len(token) > 4096:
                raise ValueError
            raw = base64.b64decode(token, altchars=b"-_", validate=True)
            body, signature = raw[:-32], raw[-32:]
            if not hmac.compare_digest(
                signature, hmac.digest(self.secret, body, "sha256")
            ):
                raise ValueError
            selected_scope, selected_identity, offset, row = json.loads(body)
            if selected_scope != scope or selected_identity != identity:
                fail(
                    "Preview or file changed; start from the beginning", "CONFLICT", 409
                )
            if any(type(value) is not int or value < 0 for value in (offset, row)):
                raise ValueError
            return offset, row
        except (ValueError, TypeError):
            fail("Invalid or expired preview cursor; start from the beginning")

    def show(
        self, artifact_id, *, path="", format="auto", page_size=50, page_token=None
    ):
        if format not in {"auto", "csv", "json", "image", "text"}:
            fail("Unknown preview format")
        if type(page_size) is not int or not 1 <= page_size <= 200:
            fail("page_size must be between 1 and 200")
        if not isinstance(path, str) or len(path) > 4096:
            fail("Invalid artifact-relative path")
        if path:
            _relative_path(path)
        descriptor = self.manager.get(artifact_id)
        if descriptor["publication_state"] != "committed" or descriptor[
            "availability"
        ] in {"missing", "inaccessible", "corrupt", "deleted"}:
            fail(
                "Artifact contents are unavailable; inspect Overview for its state",
                "CONFLICT",
                409,
            )
        result = {
            "artifact_id": artifact_id,
            "path": path,
            "next_page_token": None,
            "size_bytes": descriptor["size_bytes"],
            "checksum_verified": False,
        }
        scope = _identity(
            [
                artifact_id,
                descriptor.get("revision"),
                descriptor["fingerprint"],
                path,
                format,
                page_size,
            ]
        )
        if descriptor["payload_kind"] == "metadata":
            if path or page_token:
                fail("Metadata-only artifacts have no file paths or pages")
            text = json.dumps(descriptor["metadata"], ensure_ascii=True)
            if len(text.encode()) > JSON_BYTES:
                fail(
                    "Metadata exceeds the 2 MiB JSON preview limit",
                    "PREVIEW_LIMIT",
                    413,
                )
            return {
                **result,
                "format": "json",
                "tree": json_tree(text),
                "message": "Metadata-only artifact; there are no storage files.",
            }
        entry = None
        if descriptor["payload_kind"] == "directory":
            entries = descriptor["inventory"]
            entry = next(
                (
                    item
                    for item in entries
                    if item["path"] == path and item["kind"] == "file"
                ),
                None,
            )
            if entry is None:
                return self._directory(
                    result, entries, path, page_size, page_token, scope
                )
        elif path:
            fail("A file artifact has no child paths")
        expected_size = entry["size_bytes"] if entry else descriptor["size_bytes"]
        expected_sha = entry["sha256"] if entry else descriptor["fingerprint"]["value"]
        uri = descriptor["content_uri"]
        if descriptor["ownership"] == "managed":
            relative = self.manager.managed_content_path(descriptor)
            expected_uri = (
                (self.manager.managed_root / relative).as_uri()
                if self.manager.backend == "filesystem"
                else "s3://"
                + self.manager.options["bucket"]
                + "/"
                + self.manager.object_key(relative)
            )
            if uri != expected_uri:
                fail(
                    "Managed artifact location differs from its registered layout",
                    "CONFLICT",
                    409,
                )
        if entry:
            uri = (
                uri.rstrip("/") + "/" + quote(path, safe="/")
                if not uri.startswith("file:")
                else (Path(unquote(urlsplit(uri).path)) / path).as_uri()
            )
        filename = (
            path
            or descriptor.get("upload", {}).get("filename")
            or unquote(urlsplit(descriptor.get("source_uri") or uri).path).split("/")[
                -1
            ]
        )
        with _source(self.manager, uri, expected_size) as source:
            position = self._position(page_token, scope, source.identity)
            sample = source.read(0, min(TEXT_BYTES, source.size))
            selected = self._format(format, filename, sample)
            result.update(
                size_bytes=source.size,
                name=filename,
                format=selected,
                message="Preview checks file identity and size; partial reads do not reverify the full checksum.",
            )
            if selected == "csv":
                return {
                    **result,
                    **self._csv(source, page_size, position, scope, sample),
                }
            if position:
                fail("This preview format does not have pages")
            if selected == "unsupported":
                return {
                    **result,
                    "message": "No visual preview is available for this file type. Overview retains its metadata and storage location.",
                }
            limit = (
                IMAGE_BYTES
                if selected == "image"
                else JSON_BYTES
                if selected == "json"
                else TEXT_BYTES
            )
            if selected != "text" and source.size > limit:
                fail(
                    f"{selected.upper()} exceeds the {limit // (1024 * 1024)} MiB preview limit; try a bounded text preview",
                    "PREVIEW_LIMIT",
                    413,
                )
            raw = source.read(0, min(source.size, limit))
            if len(raw) == source.size:
                if hashlib.sha256(raw).hexdigest() != expected_sha:
                    fail(
                        "Content checksum differs from the registered artifact",
                        "CONFLICT",
                        409,
                    )
                result.update(
                    checksum_verified=True,
                    message="Full file checksum verified for this preview.",
                )
            if selected == "image":
                mime, width, height = image_info(raw)
                return {
                    **result,
                    "mime_type": mime,
                    "width": width,
                    "height": height,
                    "base64": base64.b64encode(raw).decode(),
                }
            try:
                text = codecs.getincrementaldecoder("utf-8-sig")().decode(
                    raw, final=len(raw) == source.size
                )
            except UnicodeError:
                fail("This file is not UTF-8 text", "INVALID_CONTENT", 422)
            return {
                **result,
                **(
                    {"tree": json_tree(text)}
                    if selected == "json"
                    else {"text": text, "truncated": len(raw) < source.size}
                ),
            }

    def _directory(self, result, entries, path, size, token, scope):
        prefix = path + "/" if path else ""
        children = {}
        if path and not any(
            item["path"] == path
            and item["kind"] == "directory"
            or item["path"].startswith(prefix)
            for item in entries
        ):
            fail(
                "Path is absent from the registered directory inventory",
                "NOT_FOUND",
                404,
            )
        for item in entries:
            if not item["path"].startswith(prefix):
                continue
            relative = item["path"][len(prefix) :]
            if not relative:
                continue
            name, separator, _ = relative.partition("/")
            kind = "directory" if separator else item["kind"]
            children[name] = {
                "name": name,
                "path": prefix + name,
                "kind": kind,
                "size_bytes": item.get("size_bytes") if kind == "file" else None,
            }
        ordered = sorted(
            children.values(),
            key=lambda item: (item["kind"] != "directory", item["name"].encode()),
        )
        position = self._position(token, scope, scope)
        offset = position[0] if position else 0
        if offset > len(ordered):
            fail("Directory cursor is outside its inventory")
        next_offset = offset + size
        return {
            **result,
            "format": "directory",
            "items": ordered[offset:next_offset],
            "total_entries": len(ordered),
            "next_page_token": self._token(scope, scope, next_offset)
            if next_offset < len(ordered)
            else None,
            "message": "Registered directory inventory; file availability is checked when opened.",
        }

    @staticmethod
    def _format(selected, filename, sample):
        if selected != "auto":
            return selected
        if (
            sample.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8", b"GIF87a", b"GIF89a"))
            or sample[:4] == b"RIFF"
            and sample[8:12] == b"WEBP"
        ):
            return "image"
        name = filename.lower()
        if name.endswith((".json", ".jsonl", ".ndjson")) or sample.lstrip(
            b"\xef\xbb\xbf \r\n\t"
        )[:1] in {b"{", b"["}:
            return "json" if not name.endswith((".jsonl", ".ndjson")) else "text"
        if name.endswith((".csv", ".tsv")):
            return "csv"
        if b"\x00" in sample:
            return "unsupported"
        try:
            text = codecs.getincrementaldecoder("utf-8-sig")().decode(
                sample, final=False
            )
            csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
            return "csv"
        except csv.Error:
            return "text"
        except UnicodeError:
            return "unsupported"

    def _csv(self, source, size, position, scope, sample):
        try:
            sample_text = codecs.getincrementaldecoder("utf-8-sig")().decode(
                sample, final=len(sample) == source.size
            )
            try:
                delimiter = (
                    csv.Sniffer()
                    .sniff(sample_text[:8192], delimiters=",;\t|")
                    .delimiter
                )
            except csv.Error:
                delimiter = ","
            header_raw = source.read(0, min(RECORD_BYTES + 1, source.size))
            header_stream = io.BytesIO(header_raw)

            def lines(stream, budget, initial=False):
                consumed = 0
                while line := stream.readline():
                    consumed += len(line)
                    if consumed > budget:
                        fail(
                            "CSV record exceeds the 128 KiB preview limit",
                            "PREVIEW_LIMIT",
                            413,
                        )
                    yield line.decode(
                        "utf-8-sig" if initial and consumed == len(line) else "utf-8"
                    )

            header = next(
                csv.reader(
                    lines(header_stream, RECORD_BYTES, True),
                    delimiter=delimiter,
                    strict=True,
                ),
                [],
            )
            if len(header) > 200:
                fail("CSV exceeds the 200-column preview limit", "PREVIEW_LIMIT", 413)
            start, row_number = position if position else (header_stream.tell(), 0)
            if start < header_stream.tell() or start > source.size:
                fail("CSV cursor is outside its registered file")
            block = source.read(start, min(CSV_BYTES, source.size - start))
            stream = io.BytesIO(block)
            rows, accepted = [], start
            while stream.tell() < len(block) and len(rows) < size:
                previous = stream.tell()
                # A page ending inside a logical record resumes at that record.
                if start + len(block) < source.size and b"\n" not in block[previous:]:
                    break
                try:
                    row = next(
                        csv.reader(
                            lines(stream, RECORD_BYTES),
                            delimiter=delimiter,
                            strict=True,
                        )
                    )
                except (csv.Error, UnicodeError):
                    if start + len(block) < source.size and stream.tell() == len(block):
                        break
                    raise
                if (
                    stream.tell() == len(block)
                    and start + len(block) < source.size
                    and not block.endswith(b"\n")
                ):
                    break
                if len(row) > 200:
                    fail("CSV row exceeds 200 columns", "PREVIEW_LIMIT", 413)
                rows.append(row)
                accepted = start + stream.tell()
            if accepted == start and start < source.size:
                fail(
                    "CSV record cannot fit a bounded preview page", "PREVIEW_LIMIT", 413
                )
            return {
                "columns": header,
                "rows": rows,
                "first_row": row_number + 1 if rows else 0,
                "last_row": row_number + len(rows),
                "delimiter": delimiter,
                "next_page_token": self._token(
                    scope, source.identity, accepted, row_number + len(rows)
                )
                if accepted < source.size
                else None,
            }
        except (csv.Error, UnicodeError, StopIteration):
            fail(
                "CSV is malformed, not UTF-8, or has a field above 128 KiB",
                "INVALID_CONTENT",
                422,
            )
