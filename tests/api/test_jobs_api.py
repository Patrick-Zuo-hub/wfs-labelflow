from pathlib import Path

from fastapi.testclient import TestClient

SAMPLE = Path("tests/fixtures/sample")


def upload_payload() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "group_1",
            (
                "WFS Label-Sample.pdf",
                (SAMPLE / "WFS Label-Sample.pdf").read_bytes(),
                "application/pdf",
            ),
        ),
        (
            "group_1",
            (
                "WFS Label-Sample.txt",
                (SAMPLE / "WFS Label-Sample.txt").read_bytes(),
                "text/plain",
            ),
        ),
        (
            "group_1",
            (
                "Logistics Label-Sample.pdf",
                (SAMPLE / "Logistics Label-Sample.pdf").read_bytes(),
                "application/pdf",
            ),
        ),
    ]


def test_validate_generate_download_and_invalidate(client: TestClient) -> None:
    validated = client.post(
        "/api/jobs/validate",
        files=upload_payload(),
        data={"logistics_repeat": "1"},
    )
    assert validated.status_code == 200
    body = validated.json()
    assert body["ok"] is True
    assert len(body["preview"]["pairs"]) == 3

    generated = client.post(f"/api/jobs/{body['job_id']}/generate")
    assert generated.status_code == 200
    assert generated.json()["reset_uploads"] is True

    downloaded = client.get(generated.json()["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"


def test_error_response_points_to_group_and_rule(client: TestClient) -> None:
    files = upload_payload()
    files[-1] = (
        "group_1",
        ("Logistics Label-Sample.pdf", b"broken", "application/pdf"),
    )

    response = client.post("/api/jobs/validate", files=files, data={"logistics_repeat": "1"})

    assert response.status_code == 422
    issue = response.json()["detail"]["issues"][0]
    assert issue["group_index"] == 1
    assert issue["rule"] == "pdf_readable"


def test_delete_invalidates_validated_job(client: TestClient) -> None:
    validated = client.post(
        "/api/jobs/validate",
        files=upload_payload(),
        data={"logistics_repeat": "1"},
    ).json()

    deleted = client.delete(f"/api/jobs/{validated['job_id']}")

    assert deleted.json() == {"ok": True}
    assert client.post(f"/api/jobs/{validated['job_id']}/generate").status_code == 404
