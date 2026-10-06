import json
import unittest
import urllib.error
from email.message import Message

from dossier.github import ApiError, GitHubClient, next_link


def headers(**values):
    msg = Message()
    for key, value in values.items():
        msg[key.replace("_", "-")] = value
    return msg


class FakeResponse:
    def __init__(self, body, hdrs=None):
        self._body = json.dumps(body).encode()
        self.headers = hdrs if hdrs is not None else headers()

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(status, hdrs=None):
    return urllib.error.HTTPError(
        "https://api.github.com/repos/me/secret", status, "error", hdrs if hdrs is not None else headers(), None
    )


class FakeOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def client(opener, sleeps=None):
    sleep = sleeps.append if sleeps is not None else (lambda seconds: None)
    return GitHubClient("tok", opener=opener, sleep=sleep, log=lambda *a: None)


class ClientTest(unittest.TestCase):
    def test_get_sends_auth_and_api_version(self):
        opener = FakeOpener(FakeResponse({"ok": 1}))
        self.assertEqual(client(opener).get("/user"), {"ok": 1})
        request = opener.requests[0]
        self.assertEqual(request.full_url, "https://api.github.com/user")
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")
        self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")

    def test_list_follows_next_links_and_encodes_params(self):
        opener = FakeOpener(
            FakeResponse([1, 2], headers(Link='<https://api.github.com/user/repos?page=2>; rel="next", '
                                              '<https://api.github.com/user/repos?page=2>; rel="last"')),
            FakeResponse([3]),
        )
        self.assertEqual(client(opener).list("/user/repos", {"per_page": 100}), [1, 2, 3])
        self.assertEqual(opener.requests[0].full_url, "https://api.github.com/user/repos?per_page=100")
        self.assertEqual(opener.requests[1].full_url, "https://api.github.com/user/repos?page=2")

    def test_list_with_key_collects_nested_items(self):
        opener = FakeOpener(
            FakeResponse({"commits": ["a"]}, headers(Link='<https://api.github.com/x?page=2>; rel="next"')),
            FakeResponse({"commits": ["b"]}),
        )
        self.assertEqual(client(opener).list("/repos/a/b/compare/x...y", key="commits"), ["a", "b"])

    def test_server_errors_are_retried(self):
        sleeps = []
        opener = FakeOpener(http_error(502), http_error(503), FakeResponse({"ok": 1}))
        self.assertEqual(client(opener, sleeps).get("/user"), {"ok": 1})
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_three_retries(self):
        opener = FakeOpener(*[http_error(500) for _ in range(4)])
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/user")
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(len(opener.requests), 4)

    def test_rate_limited_403_is_retried_and_flagged(self):
        opener = FakeOpener(*[http_error(403, headers(x_ratelimit_remaining="0")) for _ in range(4)])
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/user")
        self.assertTrue(ctx.exception.limited)
        self.assertEqual(len(opener.requests), 4)

    def test_client_errors_fail_immediately(self):
        for status in (401, 403, 404, 409, 451):
            with self.subTest(status=status):
                opener = FakeOpener(http_error(status))
                with self.assertRaises(ApiError) as ctx:
                    client(opener).get("/repos/me/secret")
                self.assertEqual(ctx.exception.status, status)
                self.assertFalse(ctx.exception.limited)
                self.assertEqual(len(opener.requests), 1)

    def test_network_errors_are_retried_then_reported_as_status_0(self):
        opener = FakeOpener(*[urllib.error.URLError("down") for _ in range(4)])
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/user")
        self.assertEqual(ctx.exception.status, 0)

    def test_error_text_never_contains_the_url(self):
        opener = FakeOpener(http_error(404))
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/repos/me/secret")
        self.assertNotIn("secret", str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)


class NextLinkTest(unittest.TestCase):
    def test_parses_next_and_ignores_others(self):
        self.assertEqual(next_link('<https://a/2>; rel="next", <https://a/9>; rel="last"'), "https://a/2")
        self.assertIsNone(next_link('<https://a/1>; rel="prev"'))
        self.assertIsNone(next_link(None))
