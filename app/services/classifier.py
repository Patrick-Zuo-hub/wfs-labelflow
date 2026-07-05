from pathlib import Path
from typing import NoReturn

from app.errors import ProcessingError
from app.models import LabelGroupFiles, Severity, ValidationIssue

SUPPORTED_SUFFIXES = frozenset({".pdf", ".txt", ".zpl"})
SOURCE_SUFFIXES = frozenset({".txt", ".zpl"})


def _is_wfs(path: Path) -> bool:
    return path.stem.casefold().startswith("wfs")


def _fail(
    group_index: int,
    *,
    rule: str,
    message: str,
    repair: str,
    filenames: list[str],
) -> NoReturn:
    raise ProcessingError(
        (
            ValidationIssue(
                severity=Severity.STRONG,
                rule=rule,
                message=message,
                repair=repair,
                group_index=group_index,
                actual=sorted(filenames),
            ),
        )
    )


def classify_group(group_index: int, files: list[Path]) -> LabelGroupFiles:
    unsupported = [
        path.name for path in files if path.suffix.casefold() not in SUPPORTED_SUFFIXES
    ]
    if unsupported:
        _fail(
            group_index,
            rule="unsupported_extension",
            message="存在不支持的文件类型",
            repair="请移除列出的文件，并且仅上传 PDF、TXT 或 ZPL 文件。",
            filenames=unsupported,
        )

    sources = [path for path in files if path.suffix.casefold() in SOURCE_SUFFIXES]
    pdfs = [path for path in files if path.suffix.casefold() == ".pdf"]
    if len(sources) != 1 or len(pdfs) != 2:
        _fail(
            group_index,
            rule="required_file_roles",
            message="每个非空组必须包含一个 ZPL/TXT 文件和两个 PDF 文件",
            repair="请删除重复文件或补齐缺失文件后重新上传。",
            filenames=[path.name for path in files],
        )

    source = sources[0]
    if not _is_wfs(source):
        _fail(
            group_index,
            rule="wfs_source_prefix_required",
            message="WFS 源文件必须以 WFS 开头",
            repair="请将 ZPL/TXT 文件命名为以 WFS 开头的文件名后重新上传。",
            filenames=[source.name],
        )

    wfs_candidates = [path for path in pdfs if _is_wfs(path)]
    if len(wfs_candidates) != 1:
        _fail(
            group_index,
            rule="wfs_pdf_prefix_required",
            message="WFS PDF 必须以 WFS 开头且只能有一个",
            repair="请保留一个以 WFS 开头的 PDF 作为 WFS 标签。",
            filenames=[path.name for path in pdfs],
        )

    wfs_pdf = wfs_candidates[0]
    logistics_candidates = [path for path in pdfs if path != wfs_pdf and not _is_wfs(path)]
    if len(logistics_candidates) != 1:
        _fail(
            group_index,
            rule="logistics_pdf_prefix_required",
            message="物流 PDF 不能以 WFS 开头",
            repair="请保留一个不以 WFS 开头的 PDF 作为物流标签。",
            filenames=[path.name for path in pdfs],
        )

    return LabelGroupFiles(
        group_index=group_index,
        wfs_pdf_path=wfs_pdf,
        wfs_zpl_path=source,
        logistics_pdf_path=logistics_candidates[0],
    )
