import json
import threading
import unittest
from http.client import HTTPConnection

from server import VERSION, create_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(self, path, method="GET"):
        connection = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            connection.close()

    def test_root_identifies_service(self):
        status, _, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["service"], "cicd-lab")

    def test_health(self):
        status, headers, body = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(dict(headers)["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_version_matches_release(self):
        status, _, body = self.request("/version")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"version": VERSION})

    def test_unknown_paths_do_not_expose_files(self):
        for path in ("/missing", "/server.py", "/../VERSION", "/.git/config"):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(body), {"error": "not_found"})

    def test_head_has_no_body(self):
        status, headers, body = self.request("/health", method="HEAD")
        self.assertEqual(status, 200)
        self.assertGreater(int(dict(headers)["Content-Length"]), 0)
        self.assertEqual(body, b"")
