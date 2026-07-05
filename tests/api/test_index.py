from fastapi.testclient import TestClient


def test_index_has_five_groups_and_required_actions(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('class="group-panel"') == 5
    assert 'id="clear-all"' in response.text
    assert 'id="validate-button"' in response.text
    assert 'id="confirm-button"' in response.text
