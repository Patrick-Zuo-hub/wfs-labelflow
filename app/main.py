from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import Settings
from app.errors import ProcessingError
from app.models import ProcessingOptions, Severity, ValidationIssue
from app.services.job_processor import JobProcessor, UploadedGroup
from app.services.registry import JobRegistry
from app.services.storage import JobStorage


def _issue_payloads(issues: tuple[ValidationIssue, ...]) -> list[dict]:
    return [issue.as_dict() for issue in issues]


def _validation_error(message: str) -> ValidationIssue:
    return ValidationIssue(
        severity=Severity.STRONG,
        rule="validation_error",
        message=message,
        repair="请修正上传文件或参数后重新提交。",
    )


def _preview_dict(preview) -> dict:
    return {
        "pairs": [
            {
                "group_index": pair.group_index,
                "box_index": pair.box_index,
                "sku": pair.sku,
                "wfs_pdf_page": pair.wfs_pdf_page,
                "logistics_pdf_page": pair.logistics_pdf_page,
                "output_sequence": (
                    ["W"] * preview.options.wfs_repeat
                    + ["L"] * preview.options.logistics_repeat
                ),
            }
            for pair in preview.pairs
        ],
        "ignored_pallets": [
            {"group_index": group.files.group_index, "page": label.pdf_page}
            for group in preview.groups
            for label in group.labels
            if label.label_type.value == "pallet"
        ],
        "issues": _issue_payloads(preview.issues),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    registry = JobRegistry()
    storage = JobStorage(resolved.runtime_root)
    processor = JobProcessor(storage, registry)
    app = FastAPI(title="WFS LabelFlow")
    app.state.settings = resolved
    app.state.registry = registry
    app.state.storage = storage
    app.state.processor = processor

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/jobs/validate")
    async def validate_job(request: Request) -> dict:
        form = await request.form()
        raw_repeat = form.get("logistics_repeat", 1)
        try:
            options = ProcessingOptions(logistics_repeat=int(raw_repeat))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"issues": _issue_payloads((_validation_error(str(exc)),))},
            ) from exc

        uploads_by_group: dict[int, list] = {}
        for key in ("group_1", "group_2", "group_3", "group_4", "group_5"):
            files = [
                item
                for item in form.getlist(key)
                if hasattr(item, "filename") and hasattr(item, "file")
            ]
            if files:
                uploads_by_group[int(key.split("_")[1])] = files

        with TemporaryDirectory() as temporary:
            incoming = Path(temporary)
            groups: list[UploadedGroup] = []
            for index in range(1, 6):
                files = uploads_by_group.get(index)
                if not files:
                    continue
                group_dir = incoming / f"group_{index}"
                group_dir.mkdir()
                paths: list[Path] = []
                for upload in files:
                    destination = group_dir / Path(upload.filename or "unnamed").name
                    with destination.open("wb") as handle:
                        shutil.copyfileobj(upload.file, handle)
                    paths.append(destination)
                groups.append(UploadedGroup(index, tuple(paths)))

            try:
                preview = processor.validate(tuple(groups), options)
            except ProcessingError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"issues": _issue_payloads(exc.issues)},
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"issues": _issue_payloads((_validation_error(str(exc)),))},
                ) from exc

        return {"ok": True, "job_id": preview.job_id, "preview": _preview_dict(preview)}

    @app.post("/api/jobs/{job_id}/generate")
    def generate_job(job_id: str) -> dict:
        try:
            result = processor.generate(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except ProcessingError as exc:
            raise HTTPException(
                status_code=500,
                detail={"issues": _issue_payloads(exc.issues)},
            ) from exc

        return {
            "ok": True,
            "reset_uploads": True,
            "download_url": f"/downloads/{result.job_id}",
        }

    @app.get("/downloads/{job_id}")
    def download_job(job_id: str) -> FileResponse:
        try:
            record = registry.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

        if record.archive is None or not record.archive.is_file():
            raise HTTPException(status_code=404, detail="archive not ready")
        return FileResponse(record.archive, media_type="application/zip", filename="output.zip")

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, bool]:
        try:
            registry.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        storage.cleanup(job_id)
        registry.remove(job_id)
        return {"ok": True}

    return app


app = create_app()
