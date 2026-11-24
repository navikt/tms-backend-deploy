from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from sync_workflows import BRANCH, WORKFLOWS, load_repositories, main, sync_repository


class WorkflowSyncTest(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.templates = {name: f"template for {name}" for name in WORKFLOWS}

    def sync(self, entries):
        self.api.request.side_effect = [
            {"default_branch": "main"},
            {"object": {"sha": "head"}},
            entries,
            {"tree": {"sha": "base-tree"}},
            {"sha": "new-tree"},
            {"sha": "new-commit"},
            {},
            {"html_url": "https://github.com/navikt/example/pull/1"},
        ]
        sync_repository(self.api, "navikt/example", self.templates)
        return [
            call.args for call in self.api.request.call_args_list
            if call.args[0] == "POST"
        ]

    def test_existing_workflows_are_replaced_without_adding_duplicate_extensions(self):
        extensions = (".yml", ".yaml", ".yaml.yml", ".yml")
        entries = [
            {"name": name + extension}
            for name, extension in zip(WORKFLOWS, extensions)
        ]
        writes = self.sync(entries + [{"name": "unrelated.yml"}])
        self.assertEqual(
            writes[0][2],
            {
                "base_tree": "base-tree",
                "tree": [
                    {
                        "path": f".github/workflows/{name}{extension}",
                        "mode": "100644",
                        "type": "blob",
                        "content": self.templates[name],
                    }
                    for name, extension in zip(WORKFLOWS, extensions)
                ],
            },
        )
        self.assertEqual(writes[1][2]["parents"], ["head"])
        self.assertEqual(
            writes[2][2], {"ref": f"refs/heads/{BRANCH}", "sha": "new-commit"}
        )
        self.assertEqual(writes[3][2]["base"], "main")

    def test_missing_workflows_are_created_alongside_existing_workflows(self):
        writes = self.sync([{"name": WORKFLOWS[0] + ".yaml"}])
        self.assertEqual(
            [entry["path"] for entry in writes[0][2]["tree"]],
            [f".github/workflows/{WORKFLOWS[0]}.yaml"]
            + [f".github/workflows/{name}.yml" for name in WORKFLOWS[1:]],
        )

    def test_repository_without_workflow_directory_gets_all_four(self):
        writes = self.sync(None)
        self.assertEqual(
            [entry["path"] for entry in writes[0][2]["tree"]],
            [f".github/workflows/{name}.yml" for name in WORKFLOWS],
        )

    def test_empty_repository_list_reports_configuration_error(self):
        with patch("pathlib.Path.read_text", return_value='{"repositories": []}'):
            with self.assertRaisesRegex(ValueError, "Add target repositories"):
                load_repositories(Path("config.json"))

    def test_main_updates_each_listed_repository(self):
        with (
            patch("sync_workflows.load_repositories", return_value=["navikt/a", "navikt/b"]),
            patch.dict("os.environ", {"WORKFLOW_SYNC_TOKEN": "test"}),
            patch("pathlib.Path.read_text", return_value="template"),
            patch("sync_workflows.GitHub"),
            patch("sync_workflows.sync_repository") as sync,
        ):
            main()
            self.assertEqual(
                [call.args[1] for call in sync.call_args_list], ["navikt/a", "navikt/b"]
            )


if __name__ == "__main__":
    unittest.main()
