# tms-backend-deploy

Shared GitHub Actions workflows for the team's Gradle backends. Maintain them here
and call them from application repositories instead of copying the implementation.

## Workflows

Files are in `.github/workflows/`.

| Workflow | Purpose | Required inputs |
|---|---|---|
| `build-and-deploy.yml` | Build, test and publish once, then deploy the same image to the selected clusters. | `clusters`: JSON string, e.g. `'["dev-gcp", "prod-gcp"]'` |
| `on-push-to-other-branches.yaml.yml` | Build and test a branch. | None |
| `deploy-revision-dispatch.yaml.yml` | Build and deploy a specific revision. | `commit`: SHA; `clusters`: JSON string, e.g. `'["dev-gcp"]'` |
| `automerge.yaml.yml` | Merge eligible minor/patch Dependabot PRs. | None |
| `validate-workflows.yml` | Check workflow syntax in this repository. Not reusable. | None |

Build/deploy workflows run in the calling application repository.

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
      contents: read
      id-token: write
    uses: navikt/tms-backend-deploy/.github/workflows/build-and-deploy.yml@main
    with:
      clusters: '["dev-gcp", "prod-gcp"]'
    secrets:
      NAIS_WORKLOAD_IDENTITY_PROVIDER: ${{ secrets.NAIS_WORKLOAD_IDENTITY_PROVIDER }}
```

- Choose the trigger in the caller; triggers are not inherited.
- Deploy only trusted code; do not use deployment access to run untrusted pull request code.
- Change `uses` to the desired workflow. Add required inputs under the job's `with:`.
- Each selected cluster needs a manifest at `nais/<cluster>/nais.yaml`. Use `'["dev-gcp"]'` to deploy to only one cluster.
- Build/deploy workflows need the secret above and the caller's `NAIS_MANAGEMENT_PROJECT_ID` variable. Remove the example's `secrets:` block when calling branch tests or automerge.
- Use `contents: read`; build/deploy workflows also need `id-token: write`. Dependency graph submission is not enabled.
- Automerge needs `contents: write`, `pull-requests: write`, `checks: read` and `statuses: read`. Its `GITHUB_TOKEN` merges do not trigger push workflows.
- Pin a commit SHA instead of `@main` for controlled updates. For a private central repository, allow caller access in its Actions settings.