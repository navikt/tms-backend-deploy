from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from sync_workflows import (
    BRANCH,
    GitHub,
    WORKFLOWS,
    load_repositories,
    main,
    sync_repository,
)


class WorkflowSyncTest(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.templates = {name: f"template for {name}" for name in WORKFLOWS}
        self.metadata = {
            "archived": False,
            "disabled": False,
            "default_branch": "main",
            "owner": {"login": "navikt"},
        }

    def responses(self, entries, *extra):
        self.api.request.side_effect = [
            self.metadata,
            {"object": {"sha": "head"}},
            entries,
            *extra,
        ]

    def test_existing_extensions_are_preserved(self):
        self.responses(
            [
                {"name": name + extension}
                for name, extension in zip(
                    WORKFLOWS, (".yml", ".yaml", ".yaml.yml", ".yml")
                )
            ]
        )
        sync_repository(self.api, "navikt/example", self.templates, False)
        self.assertEqual(self.api.request.call_count, 3)

    def test_dry_run_without_workflow_directory_does_not_write(self):
        self.responses(None)
        sync_repository(self.api, "navikt/example", self.templates, True)
        self.assertEqual(self.api.request.call_count, 3)

    def test_only_missing_files_are_committed_together(self):
        self.responses(
            [{"name": WORKFLOWS[0] + ".yaml"}],
            [],
            None,
            {"tree": {"sha": "base-tree"}},
            {"sha": "new-tree"},
            {"sha": "new-commit"},
            {},
            {"html_url": "https://github.com/navikt/example/pull/1"},
        )
        sync_repository(self.api, "navikt/example", self.templates, False)
        writes = [
            call.args for call in self.api.request.call_args_list
            if call.args[0] == "POST"
        ]
        self.assertEqual(len(writes), 4)
        self.assertEqual(writes[0][2]["base_tree"], "base-tree")
        self.assertEqual(
            writes[0][2]["tree"],
            [
                {
                    "path": f".github/workflows/{name}.yml",
                    "mode": "100644",
                    "type": "blob",
                    "content": self.templates[name],
                }
                for name in WORKFLOWS[1:]
            ],
        )
        self.assertEqual(writes[1][2]["parents"], ["head"])
        self.assertEqual(
            writes[2][2], {"ref": f"refs/heads/{BRANCH}", "sha": "new-commit"}
        )
        self.assertEqual(writes[3][2]["base"], "main")

    def test_existing_pull_request_does_not_create_another(self):
        self.responses([], [{"html_url": "https://github.com/navikt/example/pull/1"}])
        sync_repository(self.api, "navikt/example", self.templates, False)
        self.assertEqual(self.api.request.call_count, 4)

    def test_orphaned_sync_branch_requires_explicit_cleanup(self):
        self.responses([], [], {"object": {"sha": "old-commit"}})
        with self.assertRaisesRegex(RuntimeError, "already exists without an open PR"):
            sync_repository(self.api, "navikt/example", self.templates, False)
        self.assertEqual(self.api.request.call_count, 5)

    def test_api_failure_is_not_treated_as_missing_workflows(self):
        self.responses(RuntimeError("HTTP 403"))
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            sync_repository(self.api, "navikt/example", self.templates, False)
        self.assertEqual(self.api.request.call_count, 3)

    def test_repository_list_validation(self):
        for value in ('["navikt/example", "NAVIKT/example"]', '["../example"]', '"repo"'):
            with self.subTest(value=value), patch(
                "pathlib.Path.read_text", return_value='{"repositories":' + value + "}"
            ):
                with self.assertRaises(ValueError):
                    load_repositories(Path("config.json"))

    def test_failure_does_not_stop_remaining_repositories(self):
        with (
            patch("sync_workflows.load_repositories", return_value=["navikt/a", "navikt/b"]),
            patch.dict("os.environ", {"WORKFLOW_SYNC_TOKEN": "test", "DRY_RUN": "false"}),
            patch("pathlib.Path.read_text", return_value="template"),
            patch("sync_workflows.GitHub"),
            patch("sync_workflows.sync_repository") as sync,
        ):
            sync.side_effect = [RuntimeError("HTTP 403"), None]
            with self.assertRaisesRegex(RuntimeError, "Workflow sync failed for: navikt/a"):
                main()
            self.assertEqual(
                [call.args[1] for call in sync.call_args_list], ["navikt/a", "navikt/b"]
            )

    def test_http_errors_only_allow_explicit_missing_responses(self):
        for status, allow_missing in ((404, True), (404, False), (403, True)):
            with self.subTest(status=status, allow_missing=allow_missing):
                error = HTTPError(
                    "https://api.github.com/test", status, "error", {}, BytesIO(b"error")
                )
                with patch("sync_workflows.urlopen", side_effect=error):
                    if status == 404 and allow_missing:
                        self.assertIsNone(
                            GitHub("test").request("GET", "/test", allow_missing=True)
                        )
                    else:
                        with self.assertRaisesRegex(RuntimeError, f"HTTP {status}"):
                            GitHub("test").request(
                                "GET", "/test", allow_missing=allow_missing
                            )


if __name__ == "__main__":
    unittest.main()
