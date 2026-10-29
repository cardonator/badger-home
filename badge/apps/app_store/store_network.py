"""Read a curated catalog and stream runtime files from one GitHub revision."""

import json

from store_storage import validate_catalog

REPOSITORY = "cardonator/badger-home"
BRANCH = "main"
CATALOG = "badge/apps/app_store/catalog.json"
TIMEOUT = 8
CATALOG_LIMIT = 24 * 1024


def response(url):
    import requests

    result = requests.get(url, timeout=TIMEOUT)
    if result.status_code != 200:
        status = result.status_code
        result.close()
        raise OSError("GitHub HTTP %s; check published catalog / rate limit" % status)
    return result


def read_json(url, limit):
    result = response(url)
    try:
        body = bytearray()
        while True:
            chunk = result.raw.read(min(1024, limit + 1 - len(body)))
            if not chunk:
                return json.loads(body.decode())
            body.extend(chunk)
            if len(body) > limit:
                raise ValueError("GitHub metadata exceeds size limit")
    finally:
        result.close()


class Source:
    def __init__(self):
        self.revision = None

    def catalog(self):
        reference = read_json(
            "https://api.github.com/repos/%s/git/ref/heads/%s" % (REPOSITORY, BRANCH),
            4096,
        )
        revision = reference["object"]["sha"]
        if (len(revision) != 40 or
                any(char not in "0123456789abcdef" for char in revision)):
            raise ValueError("Invalid GitHub revision")
        apps = validate_catalog(read_json(
            "https://raw.githubusercontent.com/%s/%s/%s" % (REPOSITORY, revision, CATALOG),
            CATALOG_LIMIT,
        ))
        self.revision = revision
        return apps

    def chunks(self, slug, path):
        if self.revision is None:
            raise ValueError("Refresh catalog before downloading")
        result = response(
            "https://raw.githubusercontent.com/%s/%s/badge/apps/%s/%s" %
            (REPOSITORY, self.revision, slug, path)
        )
        try:
            while True:
                chunk = result.raw.read(1024)
                if not chunk:
                    break
                yield chunk
        finally:
            result.close()
