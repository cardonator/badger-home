"""Bounded, single-app storage. No catalog, icons, archives, or credentials."""

import errno
import hashlib
import json
import os

MAX_APP_BYTES = 256 * 1024
RESERVE_BYTES = 64 * 1024
MAX_FILES = 32


def safe_path(path):
    if not isinstance(path, str) or not path or len(path) > 160:
        raise ValueError("Invalid app path")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
    if any(not part or part in (".", "..") or
           any(char not in allowed for char in part) for part in path.split("/")):
        raise ValueError("Unsafe app path")
    return path


def validate_catalog(data):
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Unsupported catalog")
    apps = data.get("apps")
    if not isinstance(apps, list) or not 1 <= len(apps) <= 64:
        raise ValueError("Catalog must contain 1-64 apps")
    seen = set()
    for app in apps:
        slug = safe_path(app["id"])
        if "/" in slug or slug in seen:
            raise ValueError("Duplicate or invalid app ID")
        seen.add(slug)
        if not isinstance(app["title"], str) or not 1 <= len(app["title"]) <= 40:
            raise ValueError("Invalid app title")
        if not isinstance(app["description"], str) or len(app["description"]) > 200:
            raise ValueError("Invalid app description")
        files = app["files"]
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
            raise ValueError("Too many runtime files")
        paths = set()
        total = 0
        for entry in files:
            path = safe_path(entry["path"])
            if path in paths:
                raise ValueError("Duplicate runtime file")
            paths.add(path)
            size = entry["size"]
            digest = entry["sha256"]
            if type(size) is not int or size < 0:
                raise ValueError("Invalid file size")
            if (not isinstance(digest, str) or len(digest) != 64 or
                    any(char not in "0123456789abcdef" for char in digest)):
                raise ValueError("Invalid file checksum")
            total += size
        if "__init__.py" not in paths or total > MAX_APP_BYTES:
            raise ValueError("Missing entry point or app exceeds 256 KiB")
        for path in paths:
            parts = path.split("/")
            if any("/".join(parts[:index]) in paths for index in range(1, len(parts))):
                raise ValueError("File conflicts with a directory")
    return apps


def mkdir(path):
    try:
        os.mkdir(path)
    except OSError as error:
        if error.args[0] != errno.EEXIST:
            raise


def remove_tree(path):
    try:
        entries = os.listdir(path)
    except OSError as error:
        if error.args[0] == errno.ENOENT:
            return
        raise
    for name in entries:
        child = path + "/" + name
        if os.stat(child)[0] & 0x4000:
            remove_tree(child)
        else:
            os.remove(child)
    os.rmdir(path)


class Slot:
    def __init__(self, root="/state/app_store"):
        self.root = root
        self.path = root + "/slot"
        self.record = root + "/installed.json"
        mkdir(root)
        self.current = None
        try:
            with open(self.record) as handle:
                self.current = json.load(handle)
            if (not isinstance(self.current, dict) or
                    not isinstance(self.current.get("title"), str)):
                raise ValueError("Invalid installed-app record")
            safe_path(self.current["id"])
            os.stat(self.path + "/__init__.py")
        except (ValueError, KeyError, TypeError) as error:
            print("APP_STORE: damaged installed-app record; clearing slot:", error)
            self.clear()
        except OSError as error:
            if error.args[0] != errno.ENOENT:
                raise
            if self.current is not None:
                print("APP_STORE: missing installed entry point; clearing slot")
                self.clear()
        # An incomplete transfer is never launchable, including after power loss.
        if self.current is None:
            self.clear()

    def clear(self):
        for path in (self.record, self.record + ".tmp"):
            try:
                os.remove(path)
            except OSError as error:
                if error.args[0] != errno.ENOENT:
                    raise
        self.current = None
        remove_tree(self.path)

    def install(self, app, chunks):
        """Yield progress between bounded reads; caller closes on cancellation."""
        validate_catalog({"schema": 1, "apps": [app]})
        stats = os.statvfs(self.root)
        block = stats[1] or stats[0]
        required = sum(((f["size"] + block - 1) // block) * block for f in app["files"])
        required += block * (2 + sum(f["path"].count("/") for f in app["files"]))
        # The UI asks before replacement. Reclaim the old slot before reserving space.
        self.clear()
        if stats[4] * block < required + RESERVE_BYTES:
            # statvfs above included the old app; recheck after reclaiming it.
            if os.statvfs(self.root)[4] * block < required + RESERVE_BYTES:
                raise ValueError("Not enough space; 64 KiB is reserved for state")
        mkdir(self.path)
        total = sum(f["size"] for f in app["files"])
        done = 0
        complete = False
        try:
            for entry in app["files"]:
                parts = entry["path"].split("/")
                parent = self.path
                for part in parts[:-1]:
                    parent += "/" + part
                    mkdir(parent)
                digest = hashlib.sha256()
                count = 0
                stream = chunks(entry["path"])
                try:
                    with open(self.path + "/" + entry["path"], "wb") as handle:
                        for chunk in stream:
                            if len(chunk) > 1024:
                                raise ValueError("Download chunk exceeds 1 KiB")
                            count += len(chunk)
                            if count > entry["size"]:
                                raise ValueError("Download larger than catalog size")
                            handle.write(chunk)
                            digest.update(chunk)
                            done += len(chunk)
                            yield done, total
                finally:
                    stream.close()
                actual = "".join("%02x" % byte for byte in digest.digest())
                if count != entry["size"] or actual != entry["sha256"]:
                    raise ValueError("Download incomplete or checksum mismatch")
            record = {"id": app["id"], "title": app["title"]}
            # The record is the commit marker; incomplete files are removed on reopen.
            with open(self.record + ".tmp", "w") as handle:
                json.dump(record, handle)
            os.rename(self.record + ".tmp", self.record)
            self.current = record
            complete = True
        finally:
            if not complete:
                self.clear()
