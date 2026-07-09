import zipfile
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook


def _build_zip() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf-a")
        zipped.writestr("9233758WFA.txt", b"txt-a")
        zipped.writestr("9233758WFB.pdf", b"pdf-b")
        zipped.writestr("9233758WFB.txt", b"txt-b")
        zipped.writestr("CD2606260718.pdf", b"carrier")
    return buffer.getvalue()


def _build_mapping(headers: tuple[str, str] = ("货代单号", "WFS Shipment ID")) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(list(headers))
    sheet.append(["CD2606260718", "9233758WFA"])
    sheet.append(["CD2606260718", "9233758WFB"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _payload(
    zip_name: str = "labels.zip",
    xlsx_name: str = "mapping.xlsx",
) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "label_zip",
            (zip_name, _build_zip(), "application/zip"),
        ),
        (
            "mapping_xlsx",
            (
                xlsx_name,
                _build_mapping(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
    ]


def test_validate_generate_download_and_reset(client: TestClient) -> None:
    validated = client.post("/api/jobs/validate", files=_payload())
    assert validated.status_code == 200
    body = validated.json()
    assert body["ok"] is True
    assert len(body["preview"]["assignments"]) == 2

    generated = client.post(f"/api/jobs/{body['job_id']}/generate")
    assert generated.status_code == 200
    assert generated.json()["reset_uploads"] is True

    downloaded = client.get(generated.json()["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"


def test_error_response_points_to_specific_mapping_issue(client: TestClient) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["Carrier", "Shipment"])
    sheet.append(["CD2606260718", "9233758WFA"])
    buffer = BytesIO()
    workbook.save(buffer)

    response = client.post(
        "/api/jobs/validate",
        files=[
            (
                "label_zip",
                ("labels.zip", _build_zip(), "application/zip"),
            ),
            (
                "mapping_xlsx",
                (
                    "broken.xlsx",
                    buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
        ],
    )

    assert response.status_code == 422
    issue = response.json()["detail"]["issues"][0]
    assert issue["rule"] == "missing_required_headers"
    assert issue["filename"] == "broken.xlsx"


def test_delete_invalidates_validated_job(client: TestClient) -> None:
    validated = client.post("/api/jobs/validate", files=_payload()).json()

    deleted = client.delete(f"/api/jobs/{validated['job_id']}")

    assert deleted.json() == {"ok": True}
    assert client.post(f"/api/jobs/{validated['job_id']}/generate").status_code == 404
