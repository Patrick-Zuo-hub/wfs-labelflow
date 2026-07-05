from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ProcessingError
from app.models import BoxPair, ProcessingOptions, Severity, ValidationIssue


def _write(writer: PdfWriter, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)


def _check_page_count(output: Path, expected: int, rule: str, repair: str) -> None:
    try:
        actual = len(PdfReader(output).pages)
    except Exception as exc:  # pragma: no cover - exercised through higher-level test
        raise ProcessingError(
            (
                ValidationIssue(
                    Severity.STRONG,
                    f"{rule}_readback",
                    f"{output.name} 回读校验失败",
                    repair,
                    filename=output.name,
                    actual=str(exc),
                ),
            )
        ) from exc
    if actual != expected:
        raise ProcessingError(
            (
                ValidationIssue(
                    Severity.STRONG,
                    rule,
                    f"{output.name} 输出页数校验失败",
                    repair,
                    filename=output.name,
                    expected=expected,
                    actual=actual,
                ),
            )
        )


def build_sku_pdf(
    pairs: tuple[BoxPair, ...],
    wfs_pdf: Path,
    logistics_pdf: Path,
    options: ProcessingOptions,
    output: Path,
) -> None:
    wfs_reader = PdfReader(wfs_pdf)
    logistics_reader = PdfReader(logistics_pdf)
    writer = PdfWriter()
    for pair in pairs:
        wfs_page = wfs_reader.pages[pair.wfs_pdf_page - 1]
        logistics_page = logistics_reader.pages[pair.logistics_pdf_page - 1]
        for _ in range(options.wfs_repeat):
            writer.add_page(wfs_page)
        for _ in range(options.logistics_repeat):
            writer.add_page(logistics_page)
    _write(writer, output)
    expected = len(pairs) * (options.wfs_repeat + options.logistics_repeat)
    _check_page_count(
        output,
        expected,
        "output_page_count",
        "停止下载并检查 PDF 生成流程。",
    )


def merge_pdfs(inputs: tuple[Path, ...], output: Path) -> None:
    writer = PdfWriter()
    expected = 0
    for path in inputs:
        reader = PdfReader(path)
        expected += len(reader.pages)
        for page in reader.pages:
            writer.add_page(page)
    _write(writer, output)
    _check_page_count(
        output,
        expected,
        "merge_page_count",
        "停止下载并检查跨组合并流程。",
    )
