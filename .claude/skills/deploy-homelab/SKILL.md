---
name: deploy-homelab
description: Deploy (or redeploy, or roll back) the Endurain homelab fork to production on macmini. Use when the user asks to deploy, ship, release, push to production/the homelab, redeploy, or roll back Endurain.
---

# Deploy the homelab fork

Production runs the image built from branch `homelab`. `homelab/deploy` does the whole release
(see its header and homelab/README.md → Release to production). The user asking to deploy is
the go-ahead; don't ask again.

1. **Get the change onto `homelab`.** Commit the work (explicit paths, Conventional Commits),
   then fast-forward `homelab`: `git fetch origin homelab`, check
   `git merge-base --is-ancestor origin/homelab HEAD`, then `git push origin HEAD:homelab`.
   Never force-push `homelab`. If it has moved on, merge `origin/homelab` in first.
   The push starts the **Homelab image** workflow, but only for changes under `backend/`,
   `frontend/`, `docker/` or the workflow file. Docs-only commits build nothing and need no deploy.
2. **Run `homelab/deploy`** (from the repo root; give the Bash call a 600000 ms timeout). With
   no argument it waits for any running image build, then deploys the newest successful one.
   `homelab/deploy <commit>` deploys that commit's image, which is also how to roll back.
   `--dry-run` resolves and checks everything without changing anything.
3. **Read its output**, don't just check the exit code. It reports the migrations that ran,
   new startup errors (the known Garmin "Display name is not set" one is filtered out), and
   the probes. If it fails, show the user the output and the rollback line. Don't roll back
   on your own if a migration ran.
4. **Log the deploy** in `~/code/homelab-ops/mac-mini/endurain/README.md`. Add an entry to the
   dated list of deploys, written like the ones before it: tag, what changed, migration or
   not, the checks that passed, and "Not checked in a browser." unless someone did. Commit
   and push homelab-ops.

Rollback notes: upstream's image (the line in the compose file's header) and homelab images
from before `acb9244` have no fork migrations and ignore the `homelab` schema, so they always
start. A later homelab image whose fork Alembic env lacks the revision in
`homelab.alembic_version` refuses to start ("Can't locate revision"). Rolling back across a
fork migration means downgrading it first; ask the user.
