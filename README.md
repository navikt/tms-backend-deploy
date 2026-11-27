# tms-backend-deploy

Shared GitHub Actions workflows for the team's Gradle backends and IaC
repositories. Maintain them here and call them from other repositories instead
of copying the implementation.

## Workflows

Files are in `.github/workflows/`.

| Workflow | Purpose | Required inputs |
|---|---|---|
| `reusable-build-and-deploy.yml` | Build, test and publish once, then deploy the same image to the selected clusters. | `clusters`: JSON string, e.g. `'["dev-gcp", "prod-gcp"]'` |
| `reusable-build-and-test.yml` | Build and test an application. | None |
| `reusable-deploy-revision.yml` | Build and deploy a specific revision. | `commit`: SHA; `clusters`: JSON string, e.g. `'["dev-gcp"]'` |
| `reusable-deploy-iac.yml` | Deploy an existing NAIS resource without building an application. | `cluster`: target cluster; `resource`: manifest path |
| `automerge.yaml.yml` | Merge eligible minor/patch Dependabot PRs. | None |
| `validate-workflows.yml` | Check workflow syntax in this repository. Not reusable. | None |

The `reusable-` prefix identifies workflows intended to be called by other
repositories. They run in the calling repository.

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
    uses: navikt/tms-backend-deploy/.github/workflows/reusable-build-and-deploy.yml@main
    with:
      clusters: '["dev-gcp", "prod-gcp"]'
    secrets:
      NAIS_WORKLOAD_IDENTITY_PROVIDER: ${{ secrets.NAIS_WORKLOAD_IDENTITY_PROVIDER }}
```

- Choose the trigger in the caller.
- Change `uses` to the desired workflow. Add required inputs under the job's `with:`.
- Each selected cluster in an application deployment needs a manifest at `nais/<cluster>/nais.yaml`. Use `'["dev-gcp"]'` to deploy to only one cluster.
- Application build/deploy workflows need the secret above and the caller's `NAIS_MANAGEMENT_PROJECT_ID` variable.
- Pin a commit SHA instead of `@main` for controlled updates. For a private central repository, allow caller access in its Actions settings.

## Applications with a frontend

The three application build workflows accept an optional `frontend-directory` input,
relative to the application repository root. Set it to `web-app`, for example,
to enable frontend steps. Omitting it or setting it to `''` skips all frontend
steps.

The frontend directory must contain `package.json` with `test` and `build`
scripts and a committed `pnpm-lock.yaml`. The workflows use Node 24.

For private GitHub Packages dependencies, pass the application's `READER_TOKEN`
secret with `read:packages` access to the required package.

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
    uses: navikt/tms-backend-deploy/.github/workflows/reusable-build-and-deploy.yml@main
    with:
      clusters: '["dev-gcp", "prod-gcp"]'
      frontend-directory: web-app
    secrets:
      NAIS_WORKLOAD_IDENTITY_PROVIDER: ${{ secrets.NAIS_WORKLOAD_IDENTITY_PROVIDER }}
      READER_TOKEN: ${{ secrets.READER_TOKEN }}
```


For branch builds, keep the caller's branch triggers and use this job instead:

```yaml
jobs:
  build-branch:
    permissions:
      contents: read
    uses: navikt/tms-backend-deploy/.github/workflows/reusable-build-and-test.yml@main
    with:
      frontend-directory: web-app
    secrets:
      READER_TOKEN: ${{ secrets.READER_TOKEN }}
```

## IaC repositories

Repositories ending in `-iac` can call `reusable-deploy-iac.yml` to deploy an
existing manifest without building or publishing a Docker image.

Keep the two caller workflows so changes deploy only to the matching cluster.
For example, `.github/workflows/on-push-main-<<name>>-prod-gcp.yaml`:

```yaml
name: Deploy aapen-<<name>> i prod-gcp

on:
  push:
    branches:
      - main
    paths:
      - prod-gcp/aapen-utkast.yaml

permissions:
  contents: read

jobs:
  deploy:
    uses: navikt/tms-backend-deploy/.github/workflows/reusable-deploy-iac.yml@main
    with:
      cluster: prod-gcp
      resource: ./prod-gcp/aapen-utkast.yaml
    secrets:
      NAIS_DEPLOY_APIKEY: ${{ secrets.NAIS_DEPLOY_APIKEY }}
```
