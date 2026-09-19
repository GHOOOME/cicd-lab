"""在临时目录和本机 HTTP 服务中验证发布与回滚，不连接 EC2。"""
import functools
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("deploy_staging", Path(__file__).parents[1] / "deploy-staging.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)
production_spec = importlib.util.spec_from_file_location("deploy_production", Path(__file__).parents[1] / "deploy-production.py")
production = importlib.util.module_from_spec(production_spec)
production_spec.loader.exec_module(production)
COMMIT = "a" * 40


class StaticHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, root, **kwargs):
        self.root = root
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.server.bad_health and self.path == "/health":
            body = b'{}'
        elif self.path == "/environment.json":
            body = (self.root / "environment.json").read_bytes()
        else:
            filename = {"/": "index.html", "/health": "release.json"}.get(self.path, self.path.lstrip("/"))
            body = (self.root / "current" / filename).read_bytes()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start_http(test, root):
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(StaticHandler, root=root))
    server.bad_health = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()
        thread.join()

    test.addCleanup(stop)
    return server, f"http://127.0.0.1:{server.server_port}"


class DeploymentTests(unittest.TestCase):
    environment = "staging"
    deploy = staticmethod(deployment.deploy)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / self.environment
        self.root.mkdir()
        self.previous = self.base / "shared-old-release"
        self.previous.mkdir()
        (self.previous / "index.html").write_text("<html>old</html>")
        (self.root / "current").symlink_to(self.previous)
        self.old_environment = (json.dumps({"environment": self.environment, "deployedAt": "old"}) + "\n").encode()
        (self.root / "environment.json").write_bytes(self.old_environment)
        self.server, self.url = start_http(self, self.root)
        self.metadata = {"version": "1.1", "commit": COMMIT, "builtAt": "2026-09-17T00:00:00Z", "buildId": "aaaaaaa-20260917000000000"}

    def archive(self, html=b"<html>new</html>", extra=None):
        target = self.base / "artifact.tar.gz"
        with tarfile.open(target, "w:gz") as bundle:
            root_entry = tarfile.TarInfo(".")
            root_entry.type = tarfile.DIRTYPE
            bundle.addfile(root_entry)
            for name, data in {"./index.html": html, "./release.json": json.dumps(self.metadata).encode(), "./assets/app.js": b"console.log('1.1')"}.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                bundle.addfile(entry, io.BytesIO(data))
            if extra is not None:
                bundle.addfile(extra, io.BytesIO(b"x") if extra.isfile() else None)
        return target

    def run_deploy(self, archive=None, commit=COMMIT):
        return self.deploy(archive or self.archive(), commit, self.root, self.url)

    def assert_original(self):
        self.assertEqual(os.readlink(self.root / "current"), str(self.previous))
        self.assertEqual((self.root / "environment.json").read_bytes(), self.old_environment)
        self.assertEqual((self.previous / "index.html").read_text(), "<html>old</html>")

    def test_success_and_identical_retry(self):
        archive = self.archive()
        self.assertEqual(self.run_deploy(archive), self.metadata)
        self.assertEqual(self.run_deploy(archive), self.metadata)
        release = self.root / "releases" / self.metadata["buildId"]
        self.assertEqual((self.root / "current").resolve(), release.resolve())
        self.assertEqual((release / "index.html").stat().st_mode & 0o777, 0o644)
        self.assertEqual((release / "assets").stat().st_mode & 0o777, 0o755)
        self.assertEqual(json.loads((self.root / "environment.json").read_text())["environment"], self.environment)

    def test_failed_http_restores_both_original_link_and_metadata(self):
        self.server.bad_health = True
        with patch.object(deployment.time, "sleep"), self.assertRaisesRegex(RuntimeError, "verification failed"):
            self.run_deploy()
        self.assert_original()

    def test_wrong_commit_does_not_switch(self):
        with self.assertRaisesRegex(ValueError, "commit does not match"):
            self.run_deploy(commit="b" * 40)
        self.assert_original()

    def test_existing_build_cannot_be_overwritten(self):
        self.run_deploy()
        with self.assertRaisesRegex(ValueError, "different contents"):
            self.run_deploy(self.archive(html=b"<html>changed</html>"))
        self.assertEqual((self.root / "current" / "index.html").read_bytes(), b"<html>new</html>")

    def test_path_traversal_is_rejected(self):
        entry = tarfile.TarInfo("../../../outside")
        entry.size = 1
        with self.assertRaisesRegex(ValueError, "Unsafe archive"):
            self.run_deploy(self.archive(extra=entry))
        self.assert_original()
        self.assertFalse((self.base / "outside").exists())

    def test_symlink_is_rejected(self):
        entry = tarfile.TarInfo("./assets/outside")
        entry.type = tarfile.SYMTYPE
        entry.linkname = str(self.previous)
        with self.assertRaisesRegex(ValueError, "Unsafe archive"):
            self.run_deploy(self.archive(extra=entry))
        self.assert_original()


class ProductionDeploymentTests(DeploymentTests):
    """同一套发布、失败和回滚场景也必须通过生产入口。"""

    environment = "production"
    deploy = staticmethod(production.deploy)


class EnvironmentIsolationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def test_invalid_environment_does_not_modify_directory(self):
        with self.assertRaisesRegex(ValueError, "Environment must"):
            deployment.deploy(self.base / "unused.tar.gz", COMMIT, self.base, environment="unknown")
        self.assertEqual(list(self.base.iterdir()), [])

    def test_same_artifact_has_separate_environment_and_release_files(self):
        metadata = {"version": "1.1", "commit": COMMIT, "builtAt": "2026-09-17T00:00:00Z", "buildId": "same-build"}
        source = self.base / "dist"
        source.mkdir()
        (source / "index.html").write_text("<html>same build</html>")
        (source / "release.json").write_text(json.dumps(metadata))
        archive = self.base / "artifact.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(source, arcname=".")

        for environment, deploy in (("staging", deployment.deploy), ("production", production.deploy)):
            root = self.base / environment
            root.mkdir()
            _, url = start_http(self, root)
            self.assertEqual(deploy(archive, COMMIT, root, url), metadata)
            self.assertEqual(json.loads((root / "environment.json").read_text())["environment"], environment)
            self.assertEqual(json.loads((root / "current" / "release.json").read_text()), metadata)

        # 两个环境使用同一份构建，但存放的是各自独立的版本文件。
        (self.base / "staging" / "current" / "index.html").write_text("<html>staging changed</html>")
        self.assertEqual((self.base / "production" / "current" / "index.html").read_text(), "<html>same build</html>")


if __name__ == "__main__":
    unittest.main()
