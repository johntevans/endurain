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
   **Check the branch's base first**: `git log --oneline origin/homelab..HEAD` must list only
   this session's commits. A worktree can start from `master` (upstream's mirror) when the
   checkout's `origin/HEAD` is stale; merging `origin/homelab` into that would carry upstream
   commits onto `homelab`. If it lists anything else, rebase this session's commits onto
   `origin/homelab` (`git rebase --onto origin/homelab <base>`) before pushing, and fix the
   checkout with `git remote set-head origin homelab`.
2. **Know what ships.** A deploy takes everything on `homelab` up to the commit, including
   other sessions' work. `homelab/deploy --dry-run` prints the running image (its tag ends in
   the commit); list `git log --oneline <running sha>..origin/homelab` and the fork migrations
   in that range (`git diff --stat <running sha> origin/homelab -- backend/app/homelab/alembic
   backend/app/alembic`). If it includes commits from another session, or a migration (which
   makes rolling back harder), tell the user what ships and get a yes before step 3.
3. **Run `homelab/deploy <commit>`** (from the repo root; give the Bash call a 600000 ms
   timeout), naming the commit you pushed rather than running it bare: with no argument it
   deploys the newest commit with a *successful* build, so a failed build of your push
   silently deploys an older one. `homelab/deploy <commit>` is also how to roll back.
   `--dry-run` resolves and checks everything without changing anything.
4. **Read its output**, don't just check the exit code. Check that its `Commit:` line is the
   commit you meant. It reports the migrations that ran, new startup errors (the known Garmin
   "Display name is not set" one is filtered out), and the probes. If it fails, show the user
   the output and the rollback line. Don't roll back on your own if a migration ran.
5. **Log the deploy** in `~/code/homelab-ops/mac-mini/endurain/README.md`. Add an entry to the
   dated list of deploys, written like the ones before it: tag, what changed (every commit
   that shipped, not just this session's), migration or not, the checks that passed, and "Not
   checked in a browser." unless someone did. Also update the **Runs:** line at the top to
   the new tag and date. `homelab/deploy` already pushed the pin commit and other work lands
   in homelab-ops too, so `git pull --rebase` before pushing.

## Data changes after a deploy

A change to production rows the user asked for (retagging activities, backfills) runs after
the deploy that makes the new values meaningful:

- Reach Postgres with `ssh -o BatchMode=yes macmini 'export PATH=$PATH:/usr/local/bin:/opt/homebrew/bin; docker exec -i endurain-postgres sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -v ON_ERROR_STOP=1"'`.
  Without the `PATH` export, `docker` is not found over a non-interactive ssh.
- Run the `SELECT` first and show the user what matches, summarized by value, before writing.
- Save the old values (`id, column`) before the write, and make the write refuse to commit
  unless it changes exactly the expected row count (a `DO` block that raises on a mismatch).
- Record it under that deploy's log entry: what changed, how many rows, and how to undo it.

Rollback notes: upstream's image (the line in the compose file's header) and homelab images
from before `acb9244` have no fork migrations and ignore the `homelab` schema, so they always
start. A later homelab image whose fork Alembic env lacks the revision in
`homelab.alembic_version` refuses to start ("Can't locate revision"). Rolling back across a
fork migration means downgrading it first; ask the user.
