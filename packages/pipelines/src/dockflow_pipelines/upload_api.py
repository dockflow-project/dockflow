"""Authenticated native upload transport; the shared core owns publication."""

from dockflow_core.canonical import loads
from dockflow_core.errors import DockflowError
from fastapi import Request
from fastapi.responses import JSONResponse
from python_multipart.exceptions import MultipartParseError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from .multipart import CompleteMultipartParser
from .uploads import OPTIONS_BYTES, too_large, upload_stream, validate_options


class ArtifactMultipartParser(CompleteMultipartParser):
    def on_part_end(self):
        if self._current_part.file is None:
            if self._charset.lower() not in {"utf-8", "utf8"}:
                raise MultiPartException("Upload options require UTF-8")
            try:
                self._current_part.data.decode("utf-8")
            except UnicodeError as exc:
                raise MultiPartException("Upload options require UTF-8") from exc
        super().on_part_end()


def mount_uploads(app, core, scheduler):
    @app.post("/dockflow/v1/artifacts/upload", status_code=201)
    async def upload_artifact(request: Request):
        if request.query_params:
            raise DockflowError("Artifact upload does not accept query arguments")
        if not scheduler.available():
            raise DockflowError("Service is not ready", "UNAVAILABLE", 503)
        if scheduler.active_run:
            raise DockflowError(
                "Artifact upload requires an idle owner", "CONFLICT", 409
            )
        parser = ArtifactMultipartParser(
            request.headers,
            request.stream(),
            max_files=1,
            max_fields=1,
            max_part_size=core.settings.service["request_max_bytes"],
        )
        try:
            form = await parser.parse()
            try:
                items = form.multi_items()
                file = form.get("uploadfile")
                options = form.get("options")
                if (
                    len(items) != 2
                    or set(form) != {"uploadfile", "options"}
                    or not isinstance(file, UploadFile)
                    or not isinstance(options, str)
                ):
                    raise DockflowError(
                        "Upload requires exactly one uploadfile file and one options text field"
                    )
                if len(options.encode("utf-8")) > OPTIONS_BYTES:
                    too_large("Artifact upload options exceed 64 KiB")
                try:
                    values = loads(options)
                except (ValueError, UnicodeError) as exc:
                    raise DockflowError(
                        "Upload options must be valid UTF-8 JSON"
                    ) from exc
                validate_options(values)

                def publish():
                    with core.mutex:
                        if scheduler.active_run:
                            raise DockflowError(
                                "Artifact upload requires an idle owner",
                                "CONFLICT",
                                409,
                            )
                        return upload_stream(
                            core.artifacts,
                            file.file,
                            file.filename or "",
                            values,
                            core.settings.service["request_max_bytes"],
                        )

                result = await run_in_threadpool(publish)
                return JSONResponse(result, status_code=201)
            finally:
                await form.close()
        except (MultiPartException, MultipartParseError, ValueError, KeyError) as exc:
            raise DockflowError("Invalid multipart artifact upload") from exc
        finally:
            for stream in parser._files_to_close_on_error:
                stream.close()
