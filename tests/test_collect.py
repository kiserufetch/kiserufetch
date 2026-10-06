import unittest
from datetime import date

from dossier.collect import Stats, classify, collect
from dossier.github import ApiError

TODAY = date(2026, 10, 6)
EMAILS = frozenset({"me@example.com"})


def repo(name, private=False, fork=False):
    return {"full_name": f"me/{name}", "private": private, "fork": fork, "default_branch": "main"}


def commit(sha, when, email="me@example.com", login=None):
    return {"sha": sha, "author": {"login": login} if login else None,
            "commit": {"author": {"email": email, "date": when}}}


class FakeClient:
    def __init__(self, repos, commits=None, parents=None, ahead=None, errors=None):
        self.repos = repos
        self.commits = commits or {}
        self.parents = parents or {}
        self.ahead = ahead or {}
        self.errors = errors or {}
        self.calls = []

    @staticmethod
    def _repo(path):
        parts = path.split("/")
        return f"{parts[2]}/{parts[3]}"

    def get(self, path, params=None):
        self.calls.append(("get", path, params))
        name = self._repo(path)
        if name in self.errors:
            raise self.errors[name]
        return {"parent": self.parents.get(name)}

    def list(self, path, params=None, key=None):
        self.calls.append(("list", path, params))
        if path == "/user/repos":
            return self.repos
        name = self._repo(path)
        if name in self.errors:
            raise self.errors[name]
        if "/compare/" in path:
            return self.ahead[name]
        return self.commits.get(name, [])


def run(client, today=TODAY, logs=None):
    log = logs.append if logs is not None else (lambda *a: None)
    return collect(client, login="me", emails=EMAILS, today=today, log=log)


class ClassifyTest(unittest.TestCase):
    def test_user_by_login(self):
        self.assertEqual(classify(commit("a", "x", email="other@x.io", login="me"), "me", EMAILS), "user")

    def test_user_by_email_ignoring_case(self):
        self.assertEqual(classify(commit("a", "x", email="ME@Example.com"), "me", EMAILS), "user")

    def test_claude_by_email(self):
        c = commit("a", "x", email="noreply@anthropic.com", login="claude")
        self.assertEqual(classify(c, "me", EMAILS), "claude")

    def test_other_authors_are_ignored(self):
        c = commit("a", "x", email="bot@x.io", login="semantic-release-bot")
        self.assertIsNone(classify(c, "me", EMAILS))

    def test_null_author_and_missing_email_are_ignored(self):
        no_email = {"sha": "a", "author": None, "commit": {"author": {"date": "2026-10-05T00:00:00Z"}}}
        no_author = {"sha": "b", "author": None, "commit": {"author": None}}
        self.assertIsNone(classify(no_email, "me", EMAILS))
        self.assertIsNone(classify(no_author, "me", EMAILS))


class CollectTest(unittest.TestCase):
    def test_counts_repositories_by_visibility(self):
        client = FakeClient([repo("a"), repo("b", fork=True), repo("c", private=True)])
        stats = run(client)
        self.assertEqual((stats.public_repos, stats.private_repos), (2, 1))

    def test_totals_visible_claude_and_last24(self):
        client = FakeClient(
            [repo("pub"), repo("priv", private=True)],
            commits={
                "me/pub": [commit("p1", "2026-03-01T10:00:00Z")],
                "me/priv": [
                    commit("s1", "2026-10-05T12:00:00Z"),
                    commit("s2", "2026-10-05T13:00:00Z", email="noreply@anthropic.com", login="claude"),
                    commit("s3", "2026-02-01T00:00:00Z", email="someone@else.io", login="someone"),
                ],
            },
        )
        self.assertEqual(run(client), Stats(public_repos=1, private_repos=1, total=3, visible=1, claude=1, last24=2))

    def test_utc_day_boundaries(self):
        client = FakeClient([repo("r")], commits={"me/r": [
            commit("a", "2026-10-04T23:59:59Z"),
            commit("b", "2026-10-05T00:00:00Z"),
            commit("c", "2026-10-05T23:59:59Z"),
            commit("d", "2026-10-06T00:00:00Z"),
        ]})
        stats = run(client)
        self.assertEqual((stats.total, stats.last24), (4, 2))

    def test_commits_before_the_year_are_ignored(self):
        client = FakeClient([repo("r")], commits={"me/r": [
            commit("a", "2025-12-31T23:59:59Z"),
            commit("b", "2026-01-01T00:00:00Z"),
        ]})
        self.assertEqual(run(client).total, 1)

    def test_since_starts_at_new_year(self):
        client = FakeClient([repo("r")])
        run(client)
        self.assertIn(("list", "/repos/me/r/commits", {"since": "2026-01-01T00:00:00Z", "per_page": 100}),
                      client.calls)

    def test_january_first_sees_yesterday_but_starts_a_new_year(self):
        client = FakeClient([repo("r")], commits={"me/r": [
            commit("a", "2026-12-31T10:00:00Z"),
            commit("b", "2026-06-01T10:00:00Z"),
        ]})
        stats = run(client, today=date(2027, 1, 1))
        self.assertEqual((stats.total, stats.last24), (0, 1))
        self.assertIn(("list", "/repos/me/r/commits", {"since": "2026-12-31T00:00:00Z", "per_page": 100}),
                      client.calls)

    def test_fork_counts_only_commits_ahead_of_parent(self):
        client = FakeClient(
            [repo("fork", fork=True)],
            parents={"me/fork": {"owner": {"login": "up"}, "default_branch": "dev"}},
            ahead={"me/fork": [commit("mine", "2026-09-01T00:00:00Z"), commit("old", "2025-05-01T00:00:00Z")]},
            commits={"me/fork": [commit("upstream", "2026-09-02T00:00:00Z", email="noreply@anthropic.com")]},
        )
        stats = run(client)
        self.assertEqual((stats.total, stats.claude), (1, 0))
        self.assertIn(("list", "/repos/me/fork/compare/up:dev...main", {"per_page": 100}), client.calls)

    def test_fork_without_parent_uses_the_commit_list(self):
        client = FakeClient([repo("fork", fork=True)],
                            commits={"me/fork": [commit("a", "2026-09-01T00:00:00Z")]})
        self.assertEqual(run(client).total, 1)

    def test_same_commit_in_two_repos_counts_once_and_is_visible(self):
        shared = commit("same", "2026-05-05T00:00:00Z")
        client = FakeClient([repo("priv", private=True), repo("pub")],
                            commits={"me/priv": [shared], "me/pub": [shared]})
        stats = run(client)
        self.assertEqual((stats.total, stats.visible), (1, 1))

    def test_unavailable_repos_are_skipped_by_index(self):
        for error in (ApiError(403, blocked=True), ApiError(404), ApiError(409), ApiError(451)):
            with self.subTest(status=error.status):
                logs = []
                client = FakeClient([repo("ok"), repo("secret", private=True)],
                                    commits={"me/ok": [commit("a", "2026-05-05T00:00:00Z")]},
                                    errors={"me/secret": error})
                self.assertEqual(run(client, logs=logs).total, 1)
                self.assertEqual(logs, [f"skip repo #2: HTTP {error.status}"])

    def test_403_that_is_not_a_block_fails_the_run(self):
        client = FakeClient([repo("ok"), repo("secret", private=True)], errors={"me/secret": ApiError(403)})
        with self.assertRaises(ApiError) as ctx:
            run(client)
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("repo #2", str(ctx.exception))

    def test_fork_whose_parent_is_gone_is_skipped(self):
        class ParentGone(FakeClient):
            def list(self, path, params=None, key=None):
                if "/compare/" in path:
                    raise ApiError(404)
                return super().list(path, params, key)

        client = ParentGone([repo("fork", fork=True)],
                            parents={"me/fork": {"owner": {"login": "up"}, "default_branch": "main"}})
        self.assertEqual(run(client).total, 0)

    def test_rate_limit_is_not_mistaken_for_a_blocked_repo(self):
        client = FakeClient([repo("r")], errors={"me/r": ApiError(403, limited=True)})
        with self.assertRaises(ApiError) as ctx:
            run(client)
        self.assertTrue(ctx.exception.limited)

    def test_other_errors_name_the_repo_by_index_only(self):
        client = FakeClient([repo("ok"), repo("secret", private=True)], errors={"me/secret": ApiError(500)})
        with self.assertRaises(ApiError) as ctx:
            run(client)
        self.assertEqual(ctx.exception.status, 500)
        self.assertIn("repo #2", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception))
