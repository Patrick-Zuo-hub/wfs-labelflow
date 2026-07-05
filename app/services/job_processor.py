from __future__ import annotations

import secrets
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from app.models import GroupPreview, JobPreview, JobState, ProcessingOptions
from app.services.classifier import classify_group
from app.services.output_builder import (
    allocate_output_names,
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


def new_job_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{secrets.token_hex(2)}"


class JobProcessor:
    def __init__(self, storage: JobStorage, registry: JobRegistry):
        self.storage = storage
        self.registry = registry

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
