"""Build the opt-in badge store catalog from explicit runtime file lists."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "badge/apps"
TARGET = APPS / "app_store/catalog.json"
sys.path.insert(0, str(TARGET.parent))
from store_storage import validate_catalog


def build():
    apps = []
    for metadata in sorted(APPS.glob("*/store.json")):
        if metadata.parent.name in ("app_store", "menu", "startup", "system", "mass_storage"):
            raise ValueError("System apps cannot be offered in the experimental store")
        app = json.loads(metadata.read_text())
        files = []
        for name in app["files"]:
            path = metadata.parent / name
            if not path.resolve().is_relative_to(metadata.parent.resolve()):
                raise ValueError("Runtime file escapes app directory")
            content = path.read_bytes()
            files.append({
                "path": name,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        apps.append({
            "id": metadata.parent.name,
            "title": app["title"],
            "description": app["description"],
            "files": files,
        })
    catalog = {"schema": 1, "apps": apps}
    validate_catalog(catalog)
    output = json.dumps(catalog, indent=2) + "\n"
    if len(output.encode()) > 24 * 1024:
        raise ValueError("Catalog exceeds the badge's 24 KiB metadata limit")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = build()
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != content:
            parser.exit(1, "Store catalog is stale; run python3 .github/scripts/build_store_catalog.py\n")
    else:
        TARGET.write_text(content)
