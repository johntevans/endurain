# Endurain — homelab fork

John's fork of Endurain (self-hosted training log: FastAPI + SQLAlchemy/Alembic backend in
`backend/app`, Vue 3 + Vite frontend in `frontend/`). **Read [homelab/README.md](homelab/README.md)
first**: branches, the database rule, the dev stack and how a change reaches production.

- **Commit on `homelab` and push.** No PRs for fork work. `master` mirrors upstream and is
  never committed to. Stage by explicit path, never `git add -A`, since several sessions can
  share this checkout. Upstream uses Conventional Commits (`feat:`, `fix(scope):`), so follow it.
- **Never add an Alembic revision to upstream's chain or alter an upstream table.** Fork data
  goes in fork-owned tables in a separate Postgres schema. This is what keeps upstream merges
  and a rollback to vanilla Endurain possible. See homelab/README.md → Database.
- **Prefer new files to edits of upstream files**; every edited upstream line is a future merge
  conflict. Bugs upstream would want go upstream as a PR from `upstream/master`.
- **Try changes in the dev stack** (`homelab/dev/dev up`, then
  `http://johns-mac-mini-old.local:5173`). It holds a copy of production with the Garmin and
  Strava tokens removed. Don't put them back.
- **Production changes only when the user asks for a deploy.** It runs on `macmini` from an
  image pinned by digest in homelab-ops `mac-mini/endurain/docker-compose.yml`. When the user
  asks to deploy, redeploy or roll back, use the `/deploy-homelab` skill, which runs
  `homelab/deploy`. Don't deploy on your own initiative. Reading production (`ssh macmini`,
  its logs, a read-only `psql`) is fine.
- Operational knowledge about the deployment (Garmin linking traps, the `.dev` hostname's
  `/env.js` trick, the Strava import bugs, monitoring) is in homelab-ops
  `mac-mini/endurain/README.md`, cloned at `~/code/homelab-ops`.
- Backend tests (~30 s, 4000+):
  `cd backend && uv sync --python 3.13 --frozen --no-dev --group test --no-install-project && uv run --no-sync pytest`.
  3.13 matches the image; they need Homebrew `libmagic` (installed). Frontend:
  `docker exec endurain-dev-frontend npx vitest run` and `npx vue-tsc --build` (Node is not
  installed on this host; the dev frontend container has it).
