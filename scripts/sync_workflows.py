import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BRANCH = "workflow-sync/add-missing-workflows"
WORKFLOWS = (
    "on-push-to-main",
    "on-push-to-other-branches",
    "deploy-revision-dispatch",
    "deploy-branch-gh-cli",
)


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, data=None, allow_missing=False):
        request = Request(
            f"https://api.github.com{path}",
            method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "tms-backend-workflow-sync",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            raise RuntimeError(
                f"{method} {path}: HTTP {error.code}: "
                f"{error.read().decode(errors='replace')}"
            ) from error
        except URLError as error:
            raise RuntimeError(f"{method} {path}: {error.reason}") from error
        except TimeoutError as error:
            raise RuntimeError(f"{method} {path}: request timed out") from error


def load_repositories(path):
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object with a repositories list")
    repositories = config.get("repositories")
    if not isinstance(repositories, list) or any(
        not isinstance(repo, str)
        or not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo)
        or repo.split("/")[1] in (".", "..")
        for repo in repositories
    ):
        raise ValueError("repositories must be a list of owner/repository strings")
    if len(repositories) != len(set(repo.lower() for repo in repositories)):
        raise ValueError("repositories must not contain duplicates")
    return repositories


def missing_workflows(entries):
    existing = {entry["name"] for entry in entries}
    return [
        name
        for name in WORKFLOWS
        if not any(
            f"{name}{extension}" in existing
            for extension in (".yml", ".yaml", ".yaml.yml")
        )
    ]


def sync_repository(api, repository, templates, dry_run):
    prefix = f"/repos/{repository}"
    metadata = api.request("GET", prefix)
    if metadata["archived"] or metadata["disabled"]:
        raise RuntimeError("Repository is archived or disabled")
    default_branch = metadata["default_branch"]
    head = api.request(
        "GET", f"{prefix}/git/ref/heads/{quote(default_branch, safe='')}"
    )["object"]["sha"]
    entries = api.request(
        "GET",
        f"{prefix}/contents/.github/workflows?{urlencode({'ref': head})}",
        allow_missing=True,
    )
    missing = missing_workflows(entries if entries is not None else [])
    if not missing:
        print(f"{repository}: all workflows exist")
        return
    print(f"{repository}: missing {', '.join(missing)}")
    if dry_run:
        return

    owner = metadata["owner"]["login"]
    pulls = api.request(
        "GET",
        f"{prefix}/pulls?"
        + urlencode({"state": "open", "head": f"{owner}:{BRANCH}"}),
    )
    if pulls:
        print(f"{repository}: existing pull request {pulls[0]['html_url']}")
        return
    branch = api.request(
        "GET", f"{prefix}/git/ref/heads/{quote(BRANCH, safe='')}", allow_missing=True
    )
    if branch is not None:
        raise RuntimeError(
            f"Branch {BRANCH} already exists without an open PR; "
            "review and remove that branch before retrying"
        )

    base = api.request("GET", f"{prefix}/git/commits/{head}")
    tree = api.request(
        "POST",
        f"{prefix}/git/trees",
        {
            "base_tree": base["tree"]["sha"],
            "tree": [
                {
                    "path": f".github/workflows/{name}.yml",
                    "mode": "100644",
                    "type": "blob",
                    "content": templates[name],
                }
                for name in missing
            ],
        },
    )
    commit = api.request(
        "POST",
        f"{prefix}/git/commits",
        {
            "message": "Add missing shared backend workflow callers",
            "tree": tree["sha"],
            "parents": [head],
        },
    )
    api.request(
        "POST",
        f"{prefix}/git/refs",
        {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]},
    )
    pull = api.request(
        "POST",
        f"{prefix}/pulls",
        {
            "title": "Add missing shared backend workflows",
            "head": BRANCH,
            "base": default_branch,
            "body": (
                "Adds only missing workflow callers from "
                "navikt/tms-backend-deploy. Existing workflow files are unchanged.\n\n"
                + "\n".join(f"- `.github/workflows/{name}.yml`" for name in missing)
                + "\n\nReview deployment clusters and ensure "
                "`NAIS_WORKLOAD_IDENTITY_PROVIDER` and "
                "`NAIS_MANAGEMENT_PROJECT_ID` are configured before merging."
            ),
        },
    )
    print(f"{repository}: created {pull['html_url']}")


def main():
    repositories = load_repositories(ROOT / ".github/workflow-sync.json")
    if not repositories:
        raise ValueError("Add target repositories to .github/workflow-sync.json")
    token = os.environ.get("WORKFLOW_SYNC_TOKEN")
    if not token:
        raise ValueError("WORKFLOW_SYNC_TOKEN must be set")
    dry_run_value = os.environ.get("DRY_RUN", "true")
    if dry_run_value not in ("true", "false"):
        raise ValueError("DRY_RUN must be true or false")
    templates = {
        name: (ROOT / "templates/workflows" / f"{name}.yml").read_text()
        for name in WORKFLOWS
    }
    api = GitHub(token)
    failures = []
    for repository in repositories:
        try:
            sync_repository(api, repository, templates, dry_run_value == "true")
        except RuntimeError as error:
            print(f"{repository}: ERROR: {error}", file=sys.stderr)
            failures.append(repository)
    if failures:
        raise RuntimeError(f"Workflow sync failed for: {', '.join(failures)}")


if __name__ == "__main__":
    main()
