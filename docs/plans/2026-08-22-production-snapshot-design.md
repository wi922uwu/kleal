# Production snapshot synchronization

## Goal

Capture the source currently deployed on the Kleal production server in the
`wi922uwu/kleal` repository. The pull request must make the deployed Expo app
and matching backend reproducible without copying secrets or runtime user data.

## Source of truth

- Expo application: `/opt/kleal/kleal-app` on `157.230.52.87`
- Matching backend: `/opt/kleal/kleal-ms` on `157.230.52.87`
- Target repository: `wi922uwu/kleal`
- Target branch: `main`

The server directories do not contain Git metadata, so the synchronization is
file-based. Source files are copied from production into a clean clone of
`main`, then reviewed and tested before publication.

## Safety boundaries

- Exclude `.env` files, credentials, API keys, SSH material, logs, caches,
  dependencies, build output, uploaded media, databases, and runtime stores.
- Preserve the production directory split as `kleal-app/` and `kleal-ms/`.
- Do not modify or restart production while preparing the pull request.
- Inspect the complete diff and stage only the intended snapshot and docs.

## Documentation

The root README will describe the product, repository layout, application data
flow, current production host and endpoints, systemd services, ports, local
startup, deployment context, implemented flows, and collaboration rules. It
will explicitly state which configuration and data are intentionally absent.

## Verification

- Scan the diff for secrets and prohibited runtime files.
- Run the matching backend test suite and Python compilation checks available
  in the snapshot.
- Install the Expo dependencies from the lockfile, run TypeScript checks, and
  export Android and iOS bundles.
- Compare key deployed source hashes with the captured files before publishing.

