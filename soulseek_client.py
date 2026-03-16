import time
import requests

BASE_URL = "http://localhost:5030"

UI_USERNAME = "slskd"
UI_PASSWORD = "slskd"


def get_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/v0/session",
        json={
            "username": UI_USERNAME,
            "password": UI_PASSWORD,
        },
    )
    response.raise_for_status()
    return response.json()["token"]


def build_auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def search_soulseek(query: str, timeout: int = 20, poll_interval: float = 1.0) -> list[dict]:
    """
    Run a Soulseek search and return the /responses payload.
    `timeout` is the total time allowed for the search to complete.
    """
    token = get_token()
    headers = build_auth_headers(token)

    response = requests.post(
        f"{BASE_URL}/api/v0/searches",
        headers=headers,
        json={"searchText": query},
    )
    response.raise_for_status()

    search_id = response.json()["id"]
    deadline = time.time() + timeout

    while True:
        if time.time() > deadline:
            raise TimeoutError(f'Soulseek search timed out for query: "{query}"')

        time.sleep(poll_interval)

        poll = requests.get(
            f"{BASE_URL}/api/v0/searches/{search_id}",
            headers=headers,
        )
        poll.raise_for_status()

        data = poll.json()
        state = data.get("state", "")

        if "Completed" in state:
            break

    results_response = requests.get(
        f"{BASE_URL}/api/v0/searches/{search_id}/responses",
        headers=headers,
    )
    results_response.raise_for_status()

    return results_response.json()