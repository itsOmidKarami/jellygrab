"""Single source of truth for sidecar version + plugin↔sidecar API contract.

`API_VERSION` is the major version of the HTTP API the plugin talks to. Bump it
only when removing or breaking-changing an `/api/*` route the plugin uses.
Adding new routes or new optional fields does not require a bump.

`BUILD_VERSION` tracks the sidecar package release and is published as the
GHCR image tag. It's injected at Docker build time from the git tag (see
`release-sidecar.yml` and `sidecar/Dockerfile`); local/dev runs report
`"dev"` so an unreleased build is obvious from `/api/version`.
"""

import os

API_VERSION = 1
BUILD_VERSION = os.getenv("JELLYGRAB_BUILD_VERSION", "dev")
