import re
from pathlib import Path

from playwright.sync_api import Page, expect

SAMPLE = Path("tests/fixtures/sample").resolve()


def sample_paths() -> list[str]:
    return [
        str(SAMPLE / "WFS Label-Sample.pdf"),
        str(SAMPLE / "WFS Label-Sample.txt"),
        str(SAMPLE / "Logistics Label-Sample.pdf"),
    ]


def test_remove_file_and_clear_group(page: Page, live_server_url: str) -> None:
    page.goto(live_server_url)
    picker = page.locator('[name="group_1"]')
    picker.set_input_files(sample_paths())
    expect(page.locator('[data-group="1"] .file-list li')).to_have_count(3)

    page.locator('[data-group="1"] .remove-file').first.click()
    expect(page.locator('[data-group="1"] .file-list li')).to_have_count(2)

    page.locator('[data-group="1"] .clear-group').click()
    expect(page.locator('[data-group="1"] .file-list li')).to_have_count(0)


def test_validation_error_stays_in_exact_group(
    page: Page,
    live_server_url: str,
    tmp_path: Path,
) -> None:
    broken = tmp_path / "Logistics Label-Sample.pdf"
    broken.write_bytes(b"broken")
    page.goto(live_server_url)
    page.locator('[name="group_2"]').set_input_files(
        [
            str(SAMPLE / "WFS Label-Sample.pdf"),
            str(SAMPLE / "WFS Label-Sample.txt"),
            str(broken),
        ]
    )

    page.locator("#validate-button").click()

    error = page.locator('[data-group="2"] .group-error')
    expect(error).to_be_visible()
    expect(error).to_contain_text("第 2 组")
    expect(page.locator('[data-group="1"] .group-error')).to_be_hidden()


def test_success_clears_all_five_groups_and_keeps_download(
    page: Page,
    live_server_url: str,
) -> None:
    page.goto(live_server_url)
    page.locator('[name="group_1"]').set_input_files(sample_paths())
    page.locator("#validate-button").click()
    expect(page.locator("#preview")).to_be_visible()

    page.locator("#confirm-button").click()

    expect(page.locator("#result")).to_be_visible()
    expect(page.locator("#download-link")).to_have_attribute(
        "href",
        re.compile(r"^/downloads/"),
    )
    for index in range(1, 6):
        expect(page.locator(f'[data-group="{index}"] .file-list li')).to_have_count(0)
        assert page.locator(f'[name="group_{index}"]').input_value() == ""
    expect(page.locator('[name="logistics_repeat"][value="1"]')).to_be_checked()
    with page.expect_download() as download_info:
        page.locator("#download-link").click()
    assert download_info.value.suggested_filename == "output.zip"
