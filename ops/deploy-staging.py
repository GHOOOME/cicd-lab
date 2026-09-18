#!/usr/bin/env python3
"""部署已构建的前端到 staging；失败时恢复之前的版本和环境信息。"""

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

STAGING_ROOT = Path("/opt/cicd-web/environments/staging")
STAGING_URL = "http://127.0.0.1:18082"
MAX_BYTES = 50 * 1024 * 1024


def unpack(archive, destination):
    """先验证整个归档，再写文件；不使用会恢复链接或特殊文件的 extractall。"""
    with tarfile.open(archive, "r:gz") as bundle:
        entries, seen, total = [], set(), 0
        for member in bundle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError(f"Unsafe archive entry: {member.name!r}")
            if str(path) == "." and not member.isdir():
                raise ValueError("Archive root must be a directory")
            if path in seen:
                raise ValueError(f"Duplicate archive entry: {member.name!r}")
            seen.add(path)
            total += member.size
            if member.size < 0 or total > MAX_BYTES or len(seen) > 10000:
                raise ValueError("Archive exceeds deployment limits")
            entries.append((member, path))
        for member, path in entries:
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o644)
        for directory in [destination, *destination.rglob("*")]:
            if directory.is_dir():
                directory.chmod(0o755)


def release_metadata(directory, expected_commit):
    if not (directory / "index.html").is_file():
        raise ValueError("Artifact is missing index.html")
    metadata = json.loads((directory / "release.json").read_text(encoding="utf-8"))
    fields = ("version", "builtAt", "buildId", "commit")
    if not isinstance(metadata, dict) or any(not isinstance(metadata.get(k), str) or not metadata[k] for k in fields):
        raise ValueError("release.json must contain nonempty release fields")
    if metadata["commit"] != expected_commit:
        raise ValueError("Artifact commit does not match the requested commit")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", metadata["buildId"]):
        raise ValueError("Invalid buildId")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", metadata["version"]):
        raise ValueError("Invalid version")
    if datetime.fromisoformat(metadata["builtAt"].replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("builtAt must include a timezone")
    return metadata


def manifest(directory):
    """相同 buildId 只能复用完全相同的目录，不能覆盖历史版本。"""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Release path must be a real directory")
    result = {}
    for path in directory.rglob("*"):
        name = str(path.relative_to(directory))
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"Unsupported existing release entry: {name}")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


def replace_bytes(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".metadata-", delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(content)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def replace_link(path, target):
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".switch-") as temporary:
        link = Path(temporary) / "current"
        link.symlink_to(target)
        os.replace(link, path)


def verify_http(base_url, metadata, environment):
    def fetch(path):
        request = Request(base_url.rstrip("/") + path, headers={"Cache-Control": "no-cache"})
        with urlopen(request, timeout=2) as response:
            if response.status != 200:
                raise ValueError(f"{path}: expected HTTP 200")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("HTTP response is too large")
            return body

    for attempt in range(5):
        try:
            for path in ("/release.json", "/health"):
                if json.loads(fetch(path)) != metadata:
                    raise ValueError(f"{path} does not match this release")
            if json.loads(fetch("/environment.json")) != environment:
                raise ValueError("Runtime environment does not match this deployment")
            if b"<html" not in fetch("/").lower():
                raise ValueError("Home page is not HTML")
            return
        except (OSError, ValueError) as error:
            if attempt == 4:
                raise RuntimeError(f"Staging verification failed: {error}") from error
            time.sleep(1)


def deploy(archive, expected_commit, root=STAGING_ROOT, base_url=STAGING_URL):
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit):
        raise ValueError("Expected commit must be a full 40-character SHA")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Staging directory must already exist and cannot be a symlink")
    descriptor = os.open(root / ".deploy.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        releases = root / "releases"
        if releases.is_symlink():
            raise ValueError("Releases directory cannot be a symlink")
        releases.mkdir(mode=0o755, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=releases, prefix=".incoming-") as temporary:
            incoming = Path(temporary)
            unpack(archive, incoming)
            metadata = release_metadata(incoming, expected_commit)
            release = releases / metadata["buildId"]
            if os.path.lexists(release):
                if manifest(release) != manifest(incoming):
                    raise ValueError("buildId already exists with different contents")
            else:
                os.rename(incoming, release)

        current, env_file = root / "current", root / "environment.json"
        if os.path.lexists(current) and not current.is_symlink():
            raise ValueError("current must be a symlink or absent")
        if env_file.is_symlink() or (env_file.exists() and not env_file.is_file()):
            raise ValueError("environment.json must be a regular file or absent")
        previous = os.readlink(current) if current.is_symlink() else None
        old_environment = env_file.read_bytes() if env_file.exists() else None
        environment = {"environment": "staging", "deployedAt": datetime.now(timezone.utc).isoformat()}
        try:
            replace_bytes(env_file, (json.dumps(environment) + "\n").encode())
            replace_link(current, release)
            verify_http(base_url, metadata, environment)
        except BaseException:
            # 恢复链接字符串即可；不要跟随或修改以前共享的版本目录。
            errors = []
            for path, value, restore in ((current, previous, replace_link), (env_file, old_environment, replace_bytes)):
                try:
                    restore(path, value) if value is not None else path.unlink(missing_ok=True)
                except OSError as error:
                    errors.append(str(error))
            if errors:
                raise RuntimeError("Deployment failed; rollback needs attention: " + "; ".join(errors))
            print("Staging verification failed; previous release and environment restored.", file=sys.stderr)
            raise
        print(f"Deployed staging: {metadata['version']} ({metadata['buildId']}), commit={metadata['commit']}")
        return metadata


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 deploy-staging.py FRONTEND.tar.gz EXPECTED_COMMIT")
    try:
        deploy(sys.argv[1], sys.argv[2])
    except Exception as error:
        sys.exit(f"Deployment failed: {error}")
