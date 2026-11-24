import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BRANCH = "workflow-sync/update-default-workflows"
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
    repositories = json.loads(path.read_text())["repositories"]
    if not repositories:
        raise ValueError("Add target repositories to .github/workflow-sync.json")
    return repositories


def sync_repository(api, repository, templates):
    prefix = f"/repos/{repository}"
    default_branch = api.request("GET", prefix)["default_branch"]
    head = api.request(
        "GET", f"{prefix}/git/ref/heads/{quote(default_branch, safe='')}"
    )["object"]["sha"]
    entries = api.request(
        "GET",
        f"{prefix}/contents/.github/workflows?{urlencode({'ref': head})}",
        allow_missing=True,
    )
    existing = {entry["name"] for entry in entries or []}
    files = {}
    for name in WORKFLOWS:
        filenames = [
            f"{name}{extension}"
            for extension in (".yml", ".yaml", ".yaml.yml")
            if f"{name}{extension}" in existing
        ]
        for filename in filenames or [f"{name}.yml"]:
            files[filename] = templates[name]
    base = api.request("GET", f"{prefix}/git/commits/{head}")
    tree = api.request(
        "POST",
        f"{prefix}/git/trees",
        {
            "base_tree": base["tree"]["sha"],
            "tree": [
                {
                    "path": f".github/workflows/{filename}",
                    "mode": "100644",
                    "type": "blob",
                    "content": content,
                }
                for filename, content in files.items()
            ],
        },
    )
    commit = api.request(
        "POST",
        f"{prefix}/git/commits",
        {
            "message": "Update default backend workflows",
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
            "title": "Update default backend workflows",
            "head": BRANCH,
            "base": default_branch,
            "body": (
                "Replaces the four standard workflow callers with defaults from "
                "navikt/tms-backend-deploy, creating any that are missing. "
                "Unrelated workflows are unchanged.\n\n"
                + "\n".join(f"- `.github/workflows/{filename}`" for filename in files)
                + "\n\nReview deployment clusters and ensure "
                "`NAIS_WORKLOAD_IDENTITY_PROVIDER` and "
                "`NAIS_MANAGEMENT_PROJECT_ID` are configured before merging."
            ),
        },
    )
    print(f"{repository}: created {pull['html_url']}")


def main():
    repositories = load_repositories(ROOT / ".github/workflow-sync.json")
    token = os.environ.get("WORKFLOW_SYNC_TOKEN")
    if not token:
        raise ValueError("WORKFLOW_SYNC_TOKEN must be set")
    templates = {
        name: (ROOT / "templates/workflows" / f"{name}.yml").read_text()
        for name in WORKFLOWS
    }
    api = GitHub(token)
    for repository in repositories:
        print(f"{repository}: updating default workflows", flush=True)
        sync_repository(api, repository, templates)


if __name__ == "__main__":
    main()
