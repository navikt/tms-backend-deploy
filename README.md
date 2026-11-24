# tms-backend-deploy

Shared GitHub Actions workflows for the team's Gradle backends. Maintain them here
and call them from application repositories instead of copying the implementation.

## Workflows

Files are in `.github/workflows/`.

| Workflow | Purpose | Required inputs |
|---|---|---|
| `default-build-and-deploy.yml` | Build, test and publish once, then deploy the same image to the selected clusters. | `clusters`: JSON string, e.g. `'["dev-gcp", "prod-gcp"]'` |
| `default-build-branch.yml` | Build and test a branch. | None |
| `default-deploy-revision.yml` | Build and deploy a specific revision. | `commit`: SHA; `clusters`: JSON string, e.g. `'["dev-gcp"]'` |
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
    uses: navikt/tms-backend-deploy/.github/workflows/default-build-and-deploy.yml@main
    with:
      clusters: '["dev-gcp", "prod-gcp"]'
    secrets:
      NAIS_WORKLOAD_IDENTITY_PROVIDER: ${{ secrets.NAIS_WORKLOAD_IDENTITY_PROVIDER }}
```

- Choose the trigger in the caller; triggers are not inherited.
- Deploy only trusted code; do not use deployment access to run untrusted pull request code.
- Change `uses` to the desired workflow. Add required inputs under the job's `with:`.
- Each selected cluster needs a manifest at `nais/<cluster>/nais.yaml`. Use `'["dev-gcp"]'` to deploy to only one cluster.
- Build/deploy workflows need the secret above and the caller's `NAIS_MANAGEMENT_PROJECT_ID` variable. Branch tests do not need that secret, but can use `READER_TOKEN` for frontend dependencies (see below). Automerge does not need the example's `secrets:` block.
- Use `contents: read`; build/deploy workflows also need `id-token: write`. Dependency graph submission is not enabled.
- Automerge needs `contents: write`, `pull-requests: write`, `checks: read` and `statuses: read`. Its `GITHUB_TOKEN` merges do not trigger push workflows.
- Pin a commit SHA instead of `@main` for controlled updates. For a private central repository, allow caller access in its Actions settings.

## Applications with a frontend

All three default workflows accept an optional `frontend-directory` input,
relative to the application repository root. Set it to `web-app`, for example,
to enable frontend steps. Omitting it or setting it to `''` skips all frontend
steps; existing backend-only callers do not need changes.

The frontend directory must contain `package.json` with `test` and `build`
scripts and a committed `pnpm-lock.yaml`. The workflows use Node 24 and pnpm 10,
install dependencies with `--frozen-lockfile --strict-peer-dependencies=false`,
then run the frontend tests and build after the Gradle build. Deployment workflows
build the frontend before publishing the Docker image; the application's
Dockerfile must include the generated frontend files.

For private GitHub Packages dependencies, pass the application's `READER_TOKEN`
secret with `read:packages` access to the required packages. It is exposed as
`NODE_AUTH_TOKEN` during installation. Keep the application's npm registry
configuration for its package scopes. Omit `READER_TOKEN` if it is not needed.

Example caller for main:

```yaml
name: Build and deploy main

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    uses: navikt/tms-backend-deploy/.github/workflows/default-build-and-deploy.yml@main
    with:
      clusters: '["dev-gcp", "prod-gcp"]'
      frontend-directory: web-app
    secrets:
      NAIS_WORKLOAD_IDENTITY_PROVIDER: ${{ secrets.NAIS_WORKLOAD_IDENTITY_PROVIDER }}
      READER_TOKEN: ${{ secrets.READER_TOKEN }}
```

Set `frontend-directory` and pass `READER_TOKEN` in each frontend application's
caller, including manual branch deployment and revision deployment. Manual branch
deployment uses `default-build-and-deploy.yml`; revision deployment uses
`default-deploy-revision.yml` with its existing `commit` and `clusters` inputs.
The deployment secret, project variable, and cluster manifests described above
are still required.

For branch builds, keep the caller's branch triggers and use this job instead:

```yaml
jobs:
  build-branch:
    permissions:
      contents: read
    uses: navikt/tms-backend-deploy/.github/workflows/default-build-branch.yml@main
    with:
      frontend-directory: web-app
    secrets:
      READER_TOKEN: ${{ secrets.READER_TOKEN }}
```