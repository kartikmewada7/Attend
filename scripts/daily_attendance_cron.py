import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> None:
    api_base_url = os.getenv("ATTENDANCE_API_URL", "").rstrip("/")
    cron_secret = os.getenv("CRON_SECRET", "")

    if not api_base_url:
        raise RuntimeError("ATTENDANCE_API_URL is not configured")
    if not cron_secret:
        raise RuntimeError("CRON_SECRET is not configured")

    url = f"{api_base_url}/api/attendance/daily-summary"

    request = Request(
        url,
        method="POST",
        headers={
            "X-Cron-Secret": cron_secret,
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(f"Daily attendance summary response: HTTP {response.status}")
            print(body)

            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Daily summary failed with HTTP {response.status}")

    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Daily attendance summary failed: HTTP {exc.code}")
        print(body)
        raise
    except URLError as exc:
        print(f"Could not reach attendance API: {exc}")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"CRON ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
