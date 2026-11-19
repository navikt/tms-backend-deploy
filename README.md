# tms-backend-deploy

Shared GitHub Actions workflows for the team's Gradle backends. Maintain them here
and call them from application repositories instead of copying the implementation.

## Workflows

Files are in `.github/workflows/`.

| Workflow | Purpose | Required inputs |
|---|---|---|
| `on-push-to-main.yml` | Build, test, publish an image and deploy to clusters with a NAIS manifest. | None |
| `on-push-to-other-branches.yaml.yml` | Build and test a branch. | None |
| `deploy-branch-gh-cli.yml` | Build and deploy a branch to one cluster. | `cluster`: `dev-gcp` or `prod-gcp` |
| `deploy-revision-dispatch.yaml.yml` | Build and deploy a specific revision. | `commit`: SHA; `clusters`: JSON string, e.g. `'["dev-gcp"]'` |
| `automerge.yaml.yml` | Merge eligible minor/patch Dependabot PRs. | None |
| `validate-workflows.yml` | Check workflow syntax in this repository. Not reusable. | None |

Application build/deploy jobs are skipped in this central repository.

## Use in a project

Create a caller in the application's `.github/workflows/`, for example:

```yaml
name: Build and deploy main

on:
  push:
    branches: [main]

jobs:
  deploy:
    permissions:
      contents: write
      id-token: write
    uses: navikt/tms-backend-deploy/.github/workflows/on-push-to-main.yml@main
    secrets:
      NAIS_WORKLOAD_IDENTITY_PROVIDER: ${{ secrets.NAIS_WORKLOAD_IDENTITY_PROVIDER }}
```

- Choose the trigger in the caller; triggers are not inherited.
- Change `uses` to the desired workflow. Add required inputs under the job's `with:`.
- Build/deploy workflows need the secret above and the caller's `NAIS_MANAGEMENT_PROJECT_ID` variable. Remove the example's `secrets:` block when calling branch tests or automerge.
- Use `contents: read` for branch tests and revision/branch deployments. Deployments also need `id-token: write`. Main builds need the permissions shown above.
- Automerge needs `contents: write`, `pull-requests: write`, `checks: read` and `statuses: read`. Its `GITHUB_TOKEN` merges do not trigger push workflows.
- Pin a commit SHA instead of `@main` for controlled updates. For a private central repository, allow caller access in its Actions settings.