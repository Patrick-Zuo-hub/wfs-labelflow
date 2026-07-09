import re
import zipfile
from pathlib import Path

from openpyxl import Workbook
from playwright.sync_api import Page, expect


def _build_zip(tmp_path: Path) -> Path:
    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf-a")
        zipped.writestr("9233758WFA.txt", b"txt-a")
        zipped.writestr("9233758WFB.pdf", b"pdf-b")
        zipped.writestr("9233758WFB.txt", b"txt-b")
        zipped.writestr("CD2606260718.pdf", b"carrier")
    return archive


def _build_mapping(tmp_path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["货代单号", "WFS Shipment ID"])
    sheet.append(["CD2606260718", "9233758WFA"])
    sheet.append(["CD2606260718", "9233758WFB"])
    mapping = tmp_path / "mapping.xlsx"
    workbook.save(mapping)
    return mapping


def test_clear_button_removes_selected_files(
    page: Page,
    live_server_url: str,
    tmp_path: Path,
) -> None:
    page.goto(live_server_url)
    archive = _build_zip(tmp_path)
    page.locator('[name="label_zip"]').set_input_files(str(archive))
    expect(page.locator('[data-field="label_zip"] .file-list li')).to_have_count(1)

    page.locator('[data-field="label_zip"] .clear-file').click()
    expect(page.locator('[data-field="label_zip"] .file-list li')).to_have_count(0)
    assert page.locator('[name="label_zip"]').input_value() == ""


def test_success_clears_uploads_and_keeps_download(
    page: Page,
    live_server_url: str,
    tmp_path: Path,
) -> None:
    page.goto(live_server_url)
    page.locator('[name="label_zip"]').set_input_files(str(_build_zip(tmp_path)))
    page.locator('[name="mapping_xlsx"]').set_input_files(str(_build_mapping(tmp_path)))

    page.locator("#validate-button").click()
    expect(page.locator("#preview")).to_be_visible()

    page.locator("#confirm-button").click()

    expect(page.locator("#result")).to_be_visible()
    expect(page.locator("#download-link")).to_have_attribute(
        "href",
        re.compile(r"^/downloads/"),
    )
    assert page.locator('[name="label_zip"]').input_value() == ""
    assert page.locator('[name="mapping_xlsx"]').input_value() == ""

    with page.expect_download() as download_info:
        page.locator("#download-link").click()
    assert download_info.value.suggested_filename == "output.zip"
