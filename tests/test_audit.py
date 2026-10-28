import copy
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from boundary.cli import atomic_json
from boundary.config import build_url, document, operations, validate
from boundary.engine import MISSING, Client, audit, pointer, public_url


class API(BaseHTTPRequestHandler):
    mode = "strict"
    owner_calls = 0
    requests = 0

    def do_GET(self):
        type(self).requests += 1
        owner = self.headers.get("Authorization") == "Bearer owner-test-credential"
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/outside")
            self.end_headers()
            return
        status = 200
        if self.mode == "strict" and not owner:
            status = 403
            body = {"error": "forbidden"}
        elif self.mode == "ambiguous" and not owner:
            body = {"error": "not authenticated"}
        elif self.mode == "large":
            body = {"padding": "x" * 300000, "id": 42}
        else:
            identifier = 42
            if self.mode == "unstable" and owner:
                type(self).owner_calls += 1
                identifier = 42 + type(self).owner_calls
            body = {"id": identifier, "private": {"email": "private-person@tests.invalid"}}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


class FastClock:
    def __init__(self):
        self.value = 0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds + 0.0001


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), API)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        API.mode = "strict"
        API.owner_calls = 0
        API.requests = 0
        self.config = {
            "schema": 1,
            "base_url": "http://127.0.0.1:" + str(self.server.server_port),
            "identities": {
                "owner": {"headers_env": {"Authorization": "BOUNDARY_TEST_OWNER"}},
                "other": {"headers_env": {"Authorization": "BOUNDARY_TEST_OTHER"}},
                "anonymous": {"anonymous": True},
            },
            "cases": [
                {
                    "name": "object-access",
                    "method": "GET",
                    "path": "/objects/{id}",
                    "path_params": {"id": 42},
                    "allow": ["owner"],
                    "deny": ["other", "anonymous"],
                    "resource_pointer": "/id",
                    "resource_value": 42,
                }
            ],
            "rate": 20,
            "timeout_seconds": 2,
        }
        self.credentials = {
            "owner": {"Authorization": "Bearer owner-test-credential"},
            "other": {"Authorization": "Bearer other-test-credential"},
        }

    def run_audit(self, **options):
        clock = FastClock()
        return audit(
            self.config,
            authorized=True,
            overrides=self.credentials,
            clock=clock.now,
            sleep=clock.sleep,
            **options,
        )

    def test_correct_authorization_passes_real_http_matrix(self):
        report = self.run_audit()
        self.assertTrue(report["complete"])
        self.assertEqual(report["summary"]["pass"], 3)
        self.assertEqual(report["summary"]["violation"], 0)
        self.assertEqual(report["requests"], 4)

    def test_cross_identity_resource_access_is_confirmed(self):
        API.mode = "vulnerable"
        report = self.run_audit()
        self.assertEqual(report["summary"]["violation"], 2)
        result = report["cases"][0]["results"][1]
        self.assertEqual(result["findings"][0]["rule"], "unauthorized-resource-access")
        self.assertTrue(report["cases"][0]["resource_reference_stable"])

    def test_200_error_page_is_review_not_confirmed_violation(self):
        API.mode = "ambiguous"
        report = self.run_audit()
        self.assertEqual(report["summary"]["violation"], 0)
        self.assertEqual(report["summary"]["review"], 2)

    def test_unstable_reference_downgrades_confirmation(self):
        API.mode = "unstable"
        self.config["cases"][0].pop("resource_value")
        report = self.run_audit()
        self.assertFalse(report["cases"][0]["resource_reference_stable"])
        self.assertEqual(report["summary"]["violation"], 0)

    def test_forbidden_field_presence_without_exposing_its_value(self):
        API.mode = "vulnerable"
        case = self.config["cases"][0]
        case["allow"] = ["owner", "other"]
        case["deny"] = ["anonymous"]
        case["forbidden_fields"] = {"other": ["/private/email"]}
        report = self.run_audit()
        encoded = json.dumps(report)
        self.assertNotIn("private-person@tests.invalid", encoded)
        findings = report["cases"][0]["results"][1]["findings"]
        self.assertEqual(findings[0]["pointers"], ["/private/email"])

    def test_report_redacts_credentials_and_query_values(self):
        API.mode = "vulnerable"
        self.config["cases"][0]["query"] = {"token": "private-query-token"}
        report = self.run_audit()
        encoded = json.dumps(report)
        for private in [
            "owner-test-credential",
            "other-test-credential",
            "private-query-token",
            "private-person@tests.invalid",
        ]:
            self.assertNotIn(private, encoded)
        self.assertIn("REDACTED", encoded)

    def test_missing_session_fails_before_any_http(self):
        with self.assertRaises(ValueError):
            audit(self.config, authorized=True, overrides={})
        self.assertEqual(API.requests, 0)

    def test_authorization_confirmation_is_required(self):
        with self.assertRaises(ValueError):
            audit(self.config, overrides=self.credentials)
        self.assertEqual(API.requests, 0)

    def test_mutations_need_both_configuration_and_run_opt_in(self):
        self.config["cases"][0]["method"] = "DELETE"
        for enabled in [False, True]:
            self.config["allow_mutations"] = enabled
            with self.assertRaises(ValueError):
                self.run_audit()
        self.assertEqual(API.requests, 0)

    def test_redirects_are_not_followed(self):
        self.config["cases"][0]["path"] = "/redirect"
        self.config["cases"][0]["path_params"] = {}
        report = self.run_audit()
        self.assertEqual(report["summary"]["inconclusive"], 3)
        self.assertTrue(
            all(item["response"]["status"] == 302 for item in report["cases"][0]["results"])
        )

    def test_large_response_is_bounded_and_not_confirmed(self):
        API.mode = "large"
        report = self.run_audit()
        self.assertEqual(report["summary"]["violation"], 0)
        self.assertEqual(report["summary"]["inconclusive"], 1)
        for result in report["cases"][0]["results"]:
            self.assertTrue(result["response"]["truncated"])
            self.assertEqual(result["response"]["bytes_captured"], 256 * 1024)

    def test_cancellation_writes_only_completed_cases(self):
        stopped = threading.Event()
        stopped.set()
        report = self.run_audit(cancel=stopped)
        self.assertFalse(report["complete"])
        self.assertEqual(report["cases"], [])

    def test_origin_and_path_injection_are_rejected(self):
        for url in [
            "file:///private",
            "https://user:secret@api.test",
            "https://api.test/?secret=value",
        ]:
            value = copy.deepcopy(self.config)
            value["base_url"] = url
            with self.assertRaises(ValueError):
                validate(value)
        for route in ["//outside.test/", "/../private", "/x?token=secret", "/x\\private"]:
            value = copy.deepcopy(self.config)
            value["cases"][0]["path"] = route
            with self.assertRaises(ValueError):
                validate(value)

    def test_unknown_or_unassigned_identity_is_rejected(self):
        self.config["cases"][0]["deny"] = ["other"]
        with self.assertRaises(ValueError):
            validate(self.config)

    def test_header_injection_and_host_override_are_rejected(self):
        for header in ["Host", "Content-Length", "Bad\r\nHeader"]:
            value = copy.deepcopy(self.config)
            value["identities"]["owner"]["headers_env"] = {header: "TEST_TOKEN"}
            with self.assertRaises(ValueError):
                validate(value)

    def test_runtime_header_newlines_are_rejected(self):
        self.credentials["owner"]["Authorization"] = "Bearer private\r\nInjected: yes"
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertEqual(API.requests, 0)

    def test_path_parameters_are_encoded(self):
        self.config["cases"][0]["path_params"] = {"id": "a/b?x=y"}
        url = build_url(validate(self.config), self.config["cases"][0])
        self.assertTrue(url.endswith("/objects/a%2Fb%3Fx%3Dy"))

    def test_json_pointer_escaping_and_arrays(self):
        value = {"a/b": {"~key": [{"id": 0}]}}
        self.assertEqual(pointer(value, "/a~1b/~0key/0/id"), 0)
        self.assertIs(pointer(value, "/a~1b/missing"), MISSING)

    def test_openapi_import_lists_operations_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "openapi.json"
            path.write_text(
                json.dumps(
                    {
                        "openapi": "3.1.0",
                        "paths": {
                            "/objects/{id}": {
                                "get": {"operationId": "readObject"},
                                "parameters": [],
                            }
                        },
                    }
                )
            )
            result = operations(path)
            self.assertEqual(result[0]["parameters"], ["id"])
            self.assertEqual(result[0]["method"], "GET")
            self.assertEqual(API.requests, 0)

    def test_yaml_import_is_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unsafe.yaml"
            path.write_text("!!python/object/apply:os.system ['echo unsafe']")
            with self.assertRaises(ValueError):
                document(path)

    def test_atomic_report_file_contains_no_body(self):
        API.mode = "vulnerable"
        report = self.run_audit()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            atomic_json(path, report)
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded["tool"], "Boundary")
            self.assertNotIn("private-person@tests.invalid", path.read_text())

    def test_network_error_is_inconclusive(self):
        client = Client(1)
        result = client.request("GET", "http://127.0.0.1:1/", {}, MISSING)
        self.assertIsNone(result["status"])
        self.assertIsNotNone(result["error"])

    def test_public_url_preserves_names_but_not_values(self):
        url = public_url("https://api.test/x?token=private&a=1")
        self.assertNotIn("private", url)
        self.assertIn("token=", url)

    def test_enabled_mutations_execute_once_per_identity_without_reference_replay(self):
        self.config["cases"][0]["method"] = "DELETE"
        self.config["allow_mutations"] = True

        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers, body):
                self.calls.append(method)
                return {
                    "status": 200,
                    "error": None,
                    "truncated": False,
                    "json": {"id": 42},
                    "duration_ms": 1,
                    "bytes_captured": 9,
                    "body_sha256": "test",
                }

        client = FakeClient()
        report = self.run_audit(client=client, allow_mutations=True)
        self.assertEqual(client.calls, ["DELETE", "DELETE", "DELETE"])
        self.assertFalse(report["cases"][0]["resource_reference_stable"])
        self.assertEqual(API.requests, 0)

    def test_nan_body_is_rejected_before_network(self):
        self.config["cases"][0]["method"] = "POST"
        self.config["cases"][0]["body"] = {"amount": float("nan")}
        with self.assertRaises(ValueError):
            validate(self.config)
        self.assertEqual(API.requests, 0)
