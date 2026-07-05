from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import ProcessingOptions
from app.services.job_processor import JobProcessor, UploadedGroup
from app.services.registry import JobRegistry
from app.services.storage import JobStorage
from app.services.zpl_parser import parse_wfs_zpl

SAMPLE = ROOT / "tests" / "fixtures" / "sample"


def main() -> None:
    wfs = SAMPLE / "WFS Label-Sample.pdf"
    logistics = SAMPLE / "Logistics Label-Sample.pdf"
    zpl = SAMPLE / "WFS Label-Sample.txt"
    labels = parse_wfs_zpl(zpl.read_text(encoding="utf-8"), 1)
    print(
        {
            "wfs_pages": len(PdfReader(wfs).pages),
            "logistics_pages": len(PdfReader(logistics).pages),
            "zpl_segments": len(labels),
            "label_types": [label.label_type.value for label in labels],
            "skus": [label.sku for label in labels if label.sku],
        }
    )
    processor = JobProcessor(
        JobStorage(Path("/tmp/wfs-labelflow-qa/jobs")),
        JobRegistry(),
    )
    preview = processor.validate(
        (
            UploadedGroup(
                1,
                (
                    wfs,
                    zpl,
                    logistics,
                ),
            ),
        ),
        ProcessingOptions(logistics_repeat=1),
    )
    result = processor.generate(preview.job_id)
    print({"verified_archive": str(result.archive)})


if __name__ == "__main__":
    main()
