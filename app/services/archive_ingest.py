from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from app.errors import ProcessingError
from app.models import ArchiveEntry, ArchiveInventory, Severity, ValidationIssue

SUPPORTED_SUFFIXES = {".pdf", ".txt"}


def _fail(
    rule: str,
    message: str,
    *,
    filename: str | None = None,
    actual: object | None = None,
) -> None:
    raise ProcessingError(
        (
            ValidationIssue(
                severity=Severity.STRONG,
                rule=rule,
                message=message,
                repair="请修正 ZIP 文件后重新上传。",
                filename=filename,
                actual=actual,
            ),
        )
    )


def parse_zip_archive(path: Path) -> ArchiveInventory:
    if not path.is_file():
        _fail("archive_missing", "ZIP archive is missing", filename=path.name)

    extracted_root = Path(tempfile.mkdtemp(prefix="wfs-zip-archive-"))
    entries: list[ArchiveEntry] = []
    seen: set[tuple[str, str]] = set()

    try:
        with zipfile.ZipFile(path) as zipped:
            for member in zipped.infolist():
                if member.is_dir():
                    continue

                original = Path(member.filename)
                name = original.name
                suffix = original.suffix.casefold()
                stem = original.stem
                if suffix not in SUPPORTED_SUFFIXES:
                    _fail(
                        "unsupported_extension",
                        "ZIP contains unsupported file types",
                        filename=name,
                        actual=suffix,
                    )

                key = (stem.casefold(), suffix)
                if key in seen:
                    _fail(
                        "duplicate_archive_member",
                        "duplicate basename in ZIP",
                        filename=name,
                        actual={"stem": stem, "suffix": suffix},
                    )
                seen.add(key)

                destination = extracted_root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                entries.append(
                    ArchiveEntry(
                        name=name,
                        stem=stem,
                        suffix=suffix,
                        path=destination,
                    )
                )
    except zipfile.BadZipFile as exc:
        _fail("invalid_archive", "ZIP archive is invalid", filename=path.name, actual=str(exc))

    return ArchiveInventory(
        archive_path=path,
        extracted_root=extracted_root,
        entries=tuple(sorted(entries, key=lambda item: item.name.casefold())),
    )
