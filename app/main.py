from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.errors import ProcessingError
from app.models import Severity, ValidationIssue
from app.services.job_processor import JobProcessor
from app.services.registry import JobRegistry
from app.services.storage import JobStorage


def _issue_payloads(issues: tuple[ValidationIssue, ...]) -> list[dict]:
    return [issue.as_dict() for issue in issues]


def _validation_error(message: str) -> ValidationIssue:
    return ValidationIssue(
        severity=Severity.STRONG,
        rule="validation_error",
        message=message,
        repair="请修正上传文件后重新提交。",
    )


def _preview_dict(preview) -> dict:
    return {
        "assignments": [
            {
                "shipment_id": assignment.shipment_id,
                "carrier_number": assignment.carrier_number,
                "shipment_pdf": assignment.shipment_pdf_path.name,
                "shipment_txt": assignment.shipment_txt_path.name,
                "carrier_pdf": assignment.carrier_pdf_path.name,
                "source_rows": list(assignment.source_rows),
            }
            for assignment in preview.plan.assignments.values()
        ],
        "issues": _issue_payloads(preview.plan.issues),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    registry = JobRegistry()
    storage = JobStorage(resolved.runtime_root)
    processor = JobProcessor(storage, registry)
    app_dir = Path(__file__).resolve().parent

    app = FastAPI(title="WFS LabelFlow")
    templates = Jinja2Templates(directory=str(app_dir / "templates"))
    app.state.settings = resolved
    app.state.registry = registry
    app.state.storage = storage
    app.state.processor = processor
    app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="index.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/jobs/validate")
    async def validate_job(request: Request) -> dict:
        form = await request.form()
        zip_upload = form.get("label_zip")
        xlsx_upload = form.get("mapping_xlsx")
        if not getattr(zip_upload, "filename", None) or not getattr(
            xlsx_upload,
            "filename",
            None,
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "issues": _issue_payloads(
                        (_validation_error("请同时上传 ZIP 和 Excel 文件。"),)
                    )
                },
            )

        with TemporaryDirectory() as temporary:
            incoming = Path(temporary)
            zip_path = incoming / Path(zip_upload.filename).name
            xlsx_path = incoming / Path(xlsx_upload.filename).name
            with zip_path.open("wb") as handle:
                shutil.copyfileobj(zip_upload.file, handle)
            with xlsx_path.open("wb") as handle:
                shutil.copyfileobj(xlsx_upload.file, handle)

            try:
                preview = processor.validate_dispatch(zip_path, xlsx_path)
            except ProcessingError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"issues": _issue_payloads(exc.issues)},
                ) from exc
            except (FileNotFoundError, ValueError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"issues": _issue_payloads((_validation_error(str(exc)),))},
                ) from exc

        return {"ok": True, "job_id": preview.job_id, "preview": _preview_dict(preview)}

    @app.post("/api/jobs/{job_id}/generate")
    def generate_job(job_id: str) -> dict:
        try:
            result = processor.generate_dispatch(job_id)
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
            record = processor.get_dispatch_result(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="archive not ready") from exc

        if not record.archive.is_file():
            raise HTTPException(status_code=404, detail="archive not ready")
        return FileResponse(record.archive, media_type="application/zip", filename="output.zip")

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, bool]:
        try:
            processor.delete_dispatch(job_id)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return {"ok": True}

    @app.post("/api/maintenance/expire")
    def expire_results() -> dict[str, list[str]]:
        return {"expired_job_ids": []}

    return app


app = create_app()
