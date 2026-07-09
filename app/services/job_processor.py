from __future__ import annotations

import secrets
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from app.models import (
    ArchiveInventory,
    CarrierMappingRow,
    DispatchPlan,
    GroupPreview,
    JobPreview,
    JobState,
    ProcessingOptions,
)
from app.services.archive_ingest import parse_zip_archive
from app.services.classifier import classify_group
from app.services.dispatch import build_dispatch_plan
from app.services.excel_mapping import read_excel_mapping
from app.services.output_builder import (
    allocate_output_names,
    build_dispatch_summary,
    build_processing_log,
    build_summary,
    build_verified_zip,
)
from app.services.pairing import build_pairs
from app.services.pdf_processor import build_sku_pdf, merge_pdfs
from app.services.registry import JobRecord, JobRegistry
from app.services.storage import JobPaths, JobStorage
from app.services.validation import collect_warnings, validate_group_counts, validate_labels
from app.services.zpl_parser import parse_wfs_zpl


@dataclass(frozen=True)
class UploadedGroup:
    group_index: int
    files: tuple[Path, ...]


@dataclass(frozen=True)
class JobResult:
    job_id: str
    archive: Path
    sku_pdf_names: tuple[str, ...]
    paths: JobPaths


@dataclass(frozen=True)
class DispatchPreview:
    job_id: str
    inventory: ArchiveInventory
    mappings: tuple[CarrierMappingRow, ...]
    plan: DispatchPlan


@dataclass(frozen=True)
class DispatchJobResult:
    job_id: str
    archive: Path
    paths: JobPaths


def new_job_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{secrets.token_hex(2)}"


class JobProcessor:
    def __init__(self, storage: JobStorage, registry: JobRegistry):
        self.storage = storage
        self.registry = registry
        self._dispatch_previews: dict[str, DispatchPreview] = {}
        self._dispatch_results: dict[str, DispatchJobResult] = {}

    def validate(
        self,
        groups: tuple[UploadedGroup, ...],
        options: ProcessingOptions,
    ) -> JobPreview:
        if not groups:
            raise ValueError("at least one non-empty group is required")

        job_id = new_job_id()
        paths = self.storage.create(job_id)
        previews: list[GroupPreview] = []

        try:
            for uploaded in sorted(groups, key=lambda item: item.group_index):
                group_dir = paths.uploads / f"group_{uploaded.group_index}"
                group_dir.mkdir()
                stored: list[Path] = []
                for source in uploaded.files:
                    destination = group_dir / source.name
                    shutil.copyfile(source, destination)
                    stored.append(destination)

                files = classify_group(uploaded.group_index, stored)
                text = files.wfs_zpl_path.read_text(encoding="utf-8-sig")
                labels = parse_wfs_zpl(text, uploaded.group_index)
                validate_labels(uploaded.group_index, labels)
                _, logistics_pages = validate_group_counts(
                    uploaded.group_index,
                    files.wfs_pdf_path,
                    files.logistics_pdf_path,
                    labels,
                )
                pairs = build_pairs(uploaded.group_index, labels, logistics_pages)
                warnings = collect_warnings(uploaded.group_index, labels, logistics_pages)
                previews.append(GroupPreview(files, labels, pairs, warnings))
        except Exception:
            self.storage.cleanup(job_id)
            raise

        preview = JobPreview(
            job_id,
            tuple(previews),
            options,
            tuple(issue for group in previews for issue in group.issues),
        )
        self.registry.add(
            job_id,
            JobRecord(JobState.AWAITING_CONFIRMATION, preview, paths),
        )
        return preview

    def generate(self, job_id: str) -> JobResult:
        record = self.registry.get(job_id)
        if record.state is not JobState.AWAITING_CONFIRMATION:
            raise ValueError("job is not awaiting confirmation")

        if record.preview.dispatch_plan is not None:
            return self._generate_dispatch(record)

        record.state = JobState.GENERATING
        try:
            grouped_outputs: dict[str, list[tuple[int, Path]]] = defaultdict(list)
            all_pairs = record.preview.pairs
            sku_names = tuple(dict.fromkeys(pair.sku for pair in all_pairs))
            names = allocate_output_names(sku_names)

            for group in record.preview.groups:
                pairs_by_sku: dict[str, list] = defaultdict(list)
                for pair in group.pairs:
                    pairs_by_sku[pair.sku].append(pair)
                for sku, pairs in pairs_by_sku.items():
                    temp = (
                        record.paths.intermediate
                        / f"group_{group.files.group_index}_{names[sku]}"
                    )
                    build_sku_pdf(
                        tuple(pairs),
                        group.files.wfs_pdf_path,
                        group.files.logistics_pdf_path,
                        record.preview.options,
                        temp,
                    )
                    grouped_outputs[sku].append((group.files.group_index, temp))

            final_pdfs: list[Path] = []
            for sku, items in grouped_outputs.items():
                output = record.paths.output / names[sku]
                merge_pdfs(tuple(path for _, path in sorted(items)), output)
                final_pdfs.append(output)

            summary = record.paths.output / "summary.csv"
            log = record.paths.output / "processing_log.txt"
            archive = record.paths.output / "output.zip"
            build_summary(job_id, record.preview.groups, names, summary)

            log_lines = [f"job_id={job_id}", f"cleanup_scope={record.paths.root}"]
            for group in record.preview.groups:
                pallet_pages = [
                    label.pdf_page
                    for label in group.labels
                    if label.label_type.value == "pallet"
                ]
                log_lines.extend(
                    (
                        f"group={group.files.group_index} "
                        f"wfs={group.files.wfs_pdf_path.name} "
                        f"zpl={group.files.wfs_zpl_path.name} "
                        f"logistics={group.files.logistics_pdf_path.name}",
                        f"group={group.files.group_index} "
                        f"zpl_segments={len(group.labels)} boxes={len(group.pairs)} "
                        f"ignored_pallet_pages={pallet_pages}",
                    )
                )
                log_lines.extend(
                    f"warning rule={issue.rule} message={issue.message}"
                    for issue in group.issues
                )
            log_lines.extend(
                f"group={pair.group_index} box={pair.box_index} sku={pair.sku} "
                f"wfs_page={pair.wfs_pdf_page} logistics_page={pair.logistics_pdf_page}"
                for pair in all_pairs
            )
            for sku, path in zip(grouped_outputs, final_pdfs, strict=True):
                merge_groups = [group_index for group_index, _ in sorted(grouped_outputs[sku])]
                log_lines.append(
                    f"sku={sku} merge_groups={merge_groups} output={path.name} "
                    f"pages={len(PdfReader(path).pages)}"
                )
            build_processing_log(tuple(log_lines), log)
            build_verified_zip(tuple(final_pdfs), summary, log, archive)
            self.storage.cleanup_inputs(job_id, archive)
        except Exception:
            record.state = JobState.GENERATION_FAILED
            raise

        record.state = JobState.READY_FOR_DOWNLOAD
        record.archive = archive
        record.completed_at = datetime.now(UTC)
        return JobResult(
            job_id,
            archive,
            tuple(path.name for path in final_pdfs),
            record.paths,
        )

    def _generate_dispatch(self, record: JobRecord) -> JobResult:
        plan = record.preview.dispatch_plan
        if plan is None:
            raise ValueError("job is not a dispatch preview")

        record.state = JobState.GENERATING
        try:
            assignments = tuple(plan.assignments.values())
            carrier_numbers = tuple(
                dict.fromkeys(assignment.carrier_number for assignment in assignments)
            )
            names = allocate_output_names(carrier_numbers)

            final_pdfs: list[Path] = []
            for carrier_number in carrier_numbers:
                assignment = next(
                    item for item in assignments if item.carrier_number == carrier_number
                )
                output = record.paths.output / names[carrier_number]
                shutil.copy2(assignment.carrier_pdf_path, output)
                final_pdfs.append(output)

            summary = record.paths.output / "summary.csv"
            log = record.paths.output / "processing_log.txt"
            archive = record.paths.output / "output.zip"
            build_dispatch_summary(record.preview.job_id, plan, names, summary)
            log_lines = [f"job_id={record.preview.job_id}", f"cleanup_scope={record.paths.root}"]
            for assignment in assignments:
                log_lines.append(
                    f"shipment_id={assignment.shipment_id} "
                    f"carrier_number={assignment.carrier_number} "
                    f"shipment_pdf={assignment.shipment_pdf_path.name} "
                    f"shipment_txt={assignment.shipment_txt_path.name} "
                    f"carrier_pdf={assignment.carrier_pdf_path.name} "
                    f"output={names[assignment.carrier_number]} "
                    f"source_rows={list(assignment.source_rows)}"
                )
            build_processing_log(tuple(log_lines), log)
            build_verified_zip(tuple(final_pdfs), summary, log, archive)
            self.storage.cleanup_inputs(record.preview.job_id, archive)
        except Exception:
            record.state = JobState.GENERATION_FAILED
            raise

        record.state = JobState.READY_FOR_DOWNLOAD
        record.archive = archive
        record.completed_at = datetime.now(UTC)
        self._dispatch_results[record.preview.job_id] = DispatchJobResult(
            job_id=record.preview.job_id,
            archive=archive,
            paths=record.paths,
        )
        return JobResult(
            record.preview.job_id,
            archive,
            tuple(path.name for path in final_pdfs),
            record.paths,
        )

    def validate_dispatch(self, label_zip: Path, mapping_xlsx: Path) -> DispatchPreview:
        if not label_zip.is_file():
            raise FileNotFoundError(label_zip)
        if not mapping_xlsx.is_file():
            raise FileNotFoundError(mapping_xlsx)

        job_id = new_job_id()
        paths = self.storage.create(job_id)
        inventory: ArchiveInventory | None = None
        try:
            zip_copy = paths.uploads / label_zip.name
            xlsx_copy = paths.uploads / mapping_xlsx.name
            shutil.copy2(label_zip, zip_copy)
            shutil.copy2(mapping_xlsx, xlsx_copy)

            inventory = parse_zip_archive(zip_copy)
            mappings = read_excel_mapping(xlsx_copy)
            plan = build_dispatch_plan(inventory, mappings)
            preview = DispatchPreview(job_id, inventory, mappings, plan)
            self._dispatch_previews[job_id] = preview
            self.registry.add(
                job_id,
                JobRecord(
                    JobState.AWAITING_CONFIRMATION,
                    JobPreview(
                        job_id,
                        (),
                        ProcessingOptions(),
                        dispatch_plan=plan,
                    ),
                    paths,
                ),
            )
        except Exception:
            if inventory is not None:
                shutil.rmtree(inventory.extracted_root, ignore_errors=True)
            self.storage.cleanup(job_id)
            raise

        return preview

    def generate_dispatch(self, job_id: str) -> DispatchJobResult:
        self.generate(job_id)
        return self.get_dispatch_result(job_id)

    def get_dispatch_result(self, job_id: str) -> DispatchJobResult:
        result = self._dispatch_results.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def delete_dispatch(self, job_id: str) -> None:
        preview = self._dispatch_previews.pop(job_id, None)
        self._dispatch_results.pop(job_id, None)
        self.registry.remove(job_id)
        if preview is not None:
            shutil.rmtree(preview.inventory.extracted_root, ignore_errors=True)
        self.storage.cleanup(job_id)
