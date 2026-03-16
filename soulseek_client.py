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
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["token"]


def build_auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def search_soulseek(query: str, timeout: int = 45, poll_interval: float = 1.0) -> list[dict]:
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
        timeout=20,
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
            timeout=20,
        )
        poll.raise_for_status()

        data = poll.json()
        state = data.get("state", "")

        if "Completed" in state:
            break

    results_response = requests.get(
        f"{BASE_URL}/api/v0/searches/{search_id}/responses",
        headers=headers,
        timeout=20,
    )
    results_response.raise_for_status()

    return results_response.json()

def enqueue_download(username: str, filename: str, size: int | None = None) -> dict:
    token = get_token()
    headers = build_auth_headers(token)

    file_payload = {"filename": filename}
    if size is not None:
        file_payload["size"] = int(size)

    payload_attempts = [
        [file_payload],                  # likely body shape
        {"files": [file_payload]},       # fallback body shape
    ]

    last_error: Exception | None = None

    for payload in payload_attempts:
        try:
            response = requests.post(
                f"{BASE_URL}/api/v0/transfers/downloads/{username}",
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.HTTPError as exc:
            last_error = exc

            if exc.response is not None and exc.response.status_code == 400:
                # try the next payload shape
                continue

            body = exc.response.text if exc.response is not None else str(exc)
            raise RuntimeError(
                f"Failed to enqueue download for {username} :: {filename} :: {body}"
            ) from exc

    if isinstance(last_error, requests.HTTPError) and last_error.response is not None:
        raise RuntimeError(
            f"Failed to enqueue download for {username} :: {filename} :: {last_error.response.text}"
        ) from last_error

    if last_error:
        raise last_error

    return {}


def get_downloads() -> list[dict]:
    token = get_token()
    headers = build_auth_headers(token)

    response = requests.get(
        f"{BASE_URL}/api/v0/transfers/downloads",
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    return response.json()