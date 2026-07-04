from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.models import BoxPair, LabelType, ProcessingOptions, WfsLabel
from app.services.pdf_processor import build_sku_pdf, merge_pdfs


def write_sized_pages(path: Path, widths: list[float]) -> Path:
    writer = PdfWriter()
    for width in widths:
        writer.add_blank_page(width=width, height=100)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def pair(box: int, sku: str, wfs_page: int, logistics_page: int) -> BoxPair:
    label = WfsLabel(1, wfs_page, wfs_page, LabelType.BOX, "^XA^XZ", sku=sku)
    return BoxPair(1, box, sku, wfs_page, logistics_page, label)


def widths(path: Path) -> list[int]:
    return [round(float(page.mediabox.width)) for page in PdfReader(path).pages]


def test_sku_pdf_preserves_wwl_box_order(tmp_path: Path) -> None:
    wfs = write_sized_pages(tmp_path / "wfs.pdf", [101, 102])
    logistics = write_sized_pages(tmp_path / "logistics.pdf", [201, 202])
    output = tmp_path / "sku.pdf"

    build_sku_pdf(
        (pair(1, "A", 1, 1), pair(2, "A", 2, 2)),
        wfs,
        logistics,
        ProcessingOptions(logistics_repeat=1),
        output,
    )

    assert widths(output) == [101, 101, 201, 102, 102, 202]


def test_double_logistics_mode_preserves_wwll_order(tmp_path: Path) -> None:
    wfs = write_sized_pages(tmp_path / "wfs.pdf", [101])
    logistics = write_sized_pages(tmp_path / "logistics.pdf", [201])
    output = tmp_path / "sku.pdf"

    build_sku_pdf(
        (pair(1, "A", 1, 1),),
        wfs,
        logistics,
        ProcessingOptions(logistics_repeat=2),
        output,
    )

    assert widths(output) == [101, 101, 201, 201]


def test_merge_is_simple_append(tmp_path: Path) -> None:
    first = write_sized_pages(tmp_path / "first.pdf", [101, 102])
    second = write_sized_pages(tmp_path / "second.pdf", [201])
    output = tmp_path / "merged.pdf"

    merge_pdfs((first, second), output)

    assert widths(output) == [101, 102, 201]
