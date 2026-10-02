"""Cache images already supplied by the two approved profile sources."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pairlit.store import Store


def cache(person):
    root = Path("data/private/portraits")
    root.mkdir(parents=True, exist_ok=True)
    path = root / (person["id"] + ".image")
    if path.exists():
        return True
    for source in reversed(person["sources"]):
        url = source.get("portrait", "")
        host = (urlsplit(url).hostname or "").lower()
        if not url.startswith("https://") or not any(
            host == h or host.endswith("." + h) for h in ["cdninstagram.com", "fbcdn.net", "licdn.com"]
        ):
            continue
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                response = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            mime = response.headers.get("content-type", "").split(";")[0]
            if (
                response.status_code != 200
                or mime not in ["image/jpeg", "image/png", "image/webp"]
                or len(response.content) > 2000000
            ):
                continue
            path.write_bytes(response.content)
            path.chmod(0o600)
            (root / (person["id"] + ".mime")).write_text(mime)
            return True
        except httpx.HTTPError:
            continue
    return False


if __name__ == "__main__":
    profiles = Store().all("profiles")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(cache, profiles))
    print({"profiles": len(profiles), "cached_portraits": sum(results)})
