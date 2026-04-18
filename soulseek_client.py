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


def search_soulseek(query: str, timeout: int = 45, poll_interval: float = 1.0, early_exit_file_count: int | None = None) -> list[dict]:
    """
    Run a Soulseek search and return the /responses payload.

    Exit strategy (in priority order):
        1. Hard deadline exceeded (timeout seconds from search start).
        2. State is Completed/ResponseLimitReached AND min_wait has passed AND
            file count has been stable for STABLE_TICKS consecutive polls.
        3. State is Completed with 0 files AND min_wait has passed (no results
            are coming — bail quickly).

    Deliberately NO early exit on InProgress: slskd marks a search InProgress
    while peers are still sending results, and fetching /responses before the
    state flips to Completed can return an empty or partial payload even with
    a post-loop sleep.
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
    start = time.time()
    deadline = start + timeout
    min_wait_until = start + 15  # never exit before 15 s regardless of state

    # Stable-count detection: exit once file_count stops growing for N ticks
    STABLE_TICKS = 3
    last_file_count = -1
    stable_ticks_seen = 0

    print(f"[search] id={search_id} query={query!r} timeout={timeout}s")

    while True:
        elapsed = time.time() - start

        if time.time() > deadline:
            print(f"[search] deadline exceeded after {elapsed:.1f}s — fetching whatever we have")
            break

        time.sleep(poll_interval)

        poll = requests.get(
            f"{BASE_URL}/api/v0/searches/{search_id}",
            headers=headers,
            timeout=20,
        )
        poll.raise_for_status()

        data = poll.json()
        state = data.get("state", "")
        file_count = data.get("fileCount", 0)
        response_count = data.get("responseCount", 0)
        elapsed = time.time() - start

        print(
            f"[search] state={state} fileCount={file_count} "
            f"responseCount={response_count} elapsed={elapsed:.1f}s "
            f"stableTicks={stable_ticks_seen}/{STABLE_TICKS}"
        )

        past_min_wait = time.time() > min_wait_until

        # ── Completed states ──────────────────────────────────────────────
        if "Completed" in state:
            # No results at all and we've waited long enough — nothing coming
            if early_exit_file_count is not None and file_count >= early_exit_file_count:
                print(f"[search] early exit — fileCount={file_count} >= threshold={early_exit_file_count}")
                break

            # Track whether the count is still growing
            if file_count == last_file_count:
                stable_ticks_seen += 1
            else:
                stable_ticks_seen = 0
                last_file_count = file_count

            # Exit once count is stable and min wait has passed
            if past_min_wait and stable_ticks_seen >= STABLE_TICKS:
                print(f"[search] Completed + stable count ({file_count}) for {STABLE_TICKS} ticks — exiting")
                break

        else:
            # Track stable count even during InProgress
            if file_count == last_file_count:
                stable_ticks_seen += 1
            else:
                stable_ticks_seen = 0
                last_file_count = file_count

            # Early exit if we have enough files and count has been stable
            if (
                early_exit_file_count is not None
                and file_count >= early_exit_file_count
                and stable_ticks_seen >= STABLE_TICKS
            ):
                print(f"[search] early exit InProgress — fileCount={file_count} stable for {STABLE_TICKS} ticks")
                break


    # Secondary wait — if we exited early during InProgress, wait for Completed
    wait_start = time.time()
    while time.time() - wait_start < 10:  # max 10s extra wait
        poll = requests.get(
            f"{BASE_URL}/api/v0/searches/{search_id}",
            headers=headers,
            timeout=20,
        )
        poll.raise_for_status()
        data = poll.json()
        state = data.get("state", "")
        if "Completed" in state:
            print(f"[search] state settled to {state} — fetching results")
            break
        time.sleep(0.5)
    else:
        print(f"[search] secondary wait timed out — fetching anyway")

    # Give slskd a moment to flush the final write to its response store.
    time.sleep(1) 

    results_response = requests.get(
        f"{BASE_URL}/api/v0/searches/{search_id}/responses",
        headers=headers,
        timeout=20,
    )
    results_response.raise_for_status()
    raw = results_response.json()
    print(
        f"[results] type={type(raw).__name__} "
        f"len={len(raw) if isinstance(raw, list) else 'N/A'} "
        f"preview={str(raw)[:300]}"
    )

    return raw if isinstance(raw, list) else []


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