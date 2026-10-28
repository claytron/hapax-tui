"""Print `version=X.YY` for GITHUB_OUTPUT when squarp.net lists firmware newer than hapax.rules.RELEASES."""

import re
import urllib.request

from hapax.rules import RELEASES

URL = "https://squarp.net/hapax/firmware/"


def key(version: str) -> tuple[int, int]:
    major, minor = version.split(".")
    return int(major), int(minor)


def newest(html: str, releases=RELEASES) -> str | None:
    found = re.findall(r"hapaxOS/([0-9]+\.[0-9]+)/hapax\.bin", html)
    top = max(found, key=key, default=None)
    return top if top and key(top) > key(releases[-1]) else None


if __name__ == "__main__":
    with urllib.request.urlopen(URL, timeout=30) as response:
        version = newest(response.read().decode())
    if version:
        print(f"version={version}")
