# Homelab fork of Endurain

This is John's fork of [endurain-project/endurain](https://github.com/endurain-project/endurain),
for features the training-analysis project needs that upstream will not build (upstream is in
a declared feature freeze, with its roadmap on social/ActivityPub). It runs in production on
the homelab Mac mini at `https://tempo.thegainzlab.com` and `https://tempo.thegainzlab.dev`.

**Two repos, split by where a fix lands.** This repo holds the app. The deployment — compose
file, `.env` template, nginx vhosts, backups, Gatus and Healthchecks — lives in
[`johntevans/homelab-ops`](https://github.com/johntevans/homelab-ops) under
`mac-mini/endurain/`, and its README is the operational reference (Garmin linking traps, the
`.dev` hostname trick, the import bugs found during the Strava backfill). A feature is fixed
here; a port, env var or vhost is fixed there.

Everything the fork adds lives under `homelab/`, in `backend/app/homelab/` (fork backend code
and its database migrations; the image only ships `backend/`), in
`frontend/src/features/activityTags/`, `frontend/src/features/trainingLog/` and
`frontend/src/features/lapIntensity/` and their `activityTags.json` / `trainingLog.json` /
`lapIntensity.json` locale files, in
`frontend/vite.config.homelab.ts`, in `backend/app/.gitignore`, in
`.github/workflows/homelab-image.yml` and in `CLAUDE.md`. Keep it that way where possible:
**a new file never conflicts with an upstream merge; an edit to an upstream file can.** The
unavoidable edits to upstream files are small and marked with a `homelab fork` comment, so
`git grep -il "homelab fork" -- backend/app frontend/src` lists the upstream files to check after
a merge.

## Branches

| Branch | What | Rules |
|---|---|---|
| `homelab` | **the default branch**, and what production runs | Started at upstream `v0.19.3` (the deployed release). Commit here, push, CI builds the image |
| `master` | a clean mirror of upstream `master` | Never commit to it. Update with `git fetch upstream && git push origin upstream/master:master` |

The `upstream` remote is fetch-only: its push URL is set to `DISABLE`, so nothing from this
checkout can be pushed to endurain-project (GitHub would refuse anyway; this account has read
access only there). In a fresh clone, set it up again with
`git remote add upstream https://github.com/endurain-project/endurain.git && git remote set-url --push upstream DISABLE`.
Contributions to upstream go only through a pull request opened on purpose.

**Take upstream releases by MERGING a tag, never by rebasing:**

```sh
git fetch upstream --tags
git checkout homelab && git merge v0.19.4     # resolve, run tests, push
```

Rebasing rewrites the commits that deployed images were built from — each image carries its
commit in `org.opencontainers.image.revision` — and needs a force-push. Merging keeps every
deployed revision reachable. Read the release notes first; a release that says "back up your
DB" means a schema migration (see Database below).

**Bug fixes that upstream would want go upstream.** Branch from `upstream/master`, open a PR
against endurain-project, and the fix comes back with the next release tag; every one merged is
one fewer diff to carry. Candidates found so far, documented in homelab-ops
`mac-mini/endurain/README.md`: TCX lap pace stored in km/h (3.6× too fast), one bad file
silently ending a Strava bulk import, `tcxreader`'s `only_gps=True` dropping indoor sessions,
and a fractional FIT `total_ascent` failing the `int` schema. If one is needed in production
before upstream releases it, cherry-pick it onto `homelab`; git drops the duplicate on the next
merge.

## The database: the one decision that is hard to undo

The backend runs `alembic upgrade head` on every start (`main.py`, `_run_alembic_migrations`).
If the fork adds a revision to upstream's chain:

- **Upstream's image can no longer start against the database.** Its Alembic does not know the
  fork's revision and refuses to run, so "roll back to vanilla Endurain" stops being a digest
  change.
- **Upstream's next migration branches from the same parent**, giving two heads to merge on
  every release that touches the schema.

So, for fork features:

1. **Never add a revision to `backend/app/alembic/versions/`, and never alter an upstream table.**
2. Store fork data in **fork-owned tables in their own Postgres schema** (e.g. `homelab`),
   keyed to upstream ids (`activities.id`, `users.id`). Upstream never sees them, so the
   upstream image keeps working against the same database.
3. Manage that schema with **a second Alembic environment** (its own `script_location` and
   `version_table`), run at startup after upstream's. See below.
4. Derived numbers (training load, PRs, pace zones) that can be recomputed from upstream's
   tables are better computed than stored. A table you don't create is one you never migrate.

### The `homelab` schema and its Alembic environment

| Piece | Where |
|---|---|
| Fork models (own `HomelabBase`, `MetaData(schema="homelab")`) | `backend/app/homelab/database.py`, `backend/app/homelab/*/models.py` |
| Alembic environment (`env.py`, revisions in `versions/`) | `backend/app/homelab/alembic/` |
| Version table | `homelab.alembic_version` (upstream's stays `public.alembic_version`) |
| Startup hook | `homelab.db_migrations.run_homelab_migrations()`, called in `main.py` right after `_run_alembic_migrations()` |
| CLI config (not read at runtime) | `backend/app/homelab/alembic.ini` |

- **Startup.** `main.py` runs upstream's `alembic upgrade head`, then the fork's. Like
  upstream's, a failure aborts startup. `env.py` creates the `homelab` schema if it is missing
  (the version table lives in it), so the first start of a fork image against a production copy
  that has never seen the fork just works; `hl0001` also runs `CREATE SCHEMA IF NOT EXISTS`.
  `docker/Dockerfile` copies all of `backend/app`, so the environment ships in the image.
- **Fork models use their own declarative base**, not `core.database.Base`, so upstream's
  autogenerate and `create_all` never see them. A foreign key into upstream's tables (e.g.
  `activities.id ... ON DELETE CASCADE`) can't be declared on such a model; write it by hand in
  the migration. The fork `env.py` limits autogenerate to the `homelab` schema and ignores those
  hand-written FKs, so `alembic check` stays clean.
- **Rolling back to vanilla Endurain** keeps working: upstream's image ignores the `homelab`
  schema. To remove the fork's data entirely: `DROP SCHEMA homelab CASCADE`.
- **Backups**: the nightly `pg_dump` dumps the whole database, `homelab` included.

**Adding a revision.** Use readable ids (`hl0002`, `hl0003`, ...). From `backend/app`, with a
database to compare against (the dev stack, or a throwaway Postgres):

```sh
uv run --no-sync alembic -c homelab/alembic.ini revision --rev-id hl0002 -m "what changed"
# or, with DB_* env vars pointing at a database at the current head:
uv run --no-sync alembic -c homelab/alembic.ini revision --autogenerate --rev-id hl0002 -m "..."
uv run --no-sync alembic -c homelab/alembic.ini check      # model vs database
```

Every table and index takes `schema="homelab"`; never reference upstream tables except by
foreign key. `backend/tests/homelab/test_migrations.py` checks the chain and the SQL it emits.
The backend tests run on SQLite, where `ATTACH DATABASE ':memory:' AS homelab` stands in for
the schema (see `backend/tests/homelab/test_activity_tags.py`).

**Tables so far:**

| Table | Holds | Revision |
|---|---|---|
| `homelab.activity_tags` | Activity tags: `(activity_id → activities.id ON DELETE CASCADE, tag ∈ race/workout/long_run/nsm_short/nsm_medium/nsm_long, created_at)`, PK `(activity_id, tag)` | `hl0001`, CHECK widened by `hl0002` |
| `homelab.lap_intensity_overrides` | The owner's lap intensity corrections: `(lap_id → activity_laps.id ON DELETE CASCADE, intensity ∈ FIT's active/interval/warmup/cooldown/recovery/rest/other, updated_at)`, PK `lap_id` | `hl0003` |

**Lap intensity and training-log quality.** A lap's effective intensity is its override, else
the recorded `activity_laps.intensity`, else `active` (FIT's default, what a lap of an
unstructured run is). The default is applied when reading, not written into upstream's table,
so the ~7,000 laps imported without an intensity (GPX, TCX, Strava) need no backfill and stay
as imported. The training log's quality time and distance are the laps with an effective
intensity of `active` or `interval` (Garmin marks structured reps `active` and every lap of a
free run `interval`), counted only for activities tagged race, workout or NSM; such an activity
with no laps counts whole. A long run counts only when it is also tagged workout.

The tag keys match Strava's run `workout_type` (1 race, 2 long run, 3 workout). A later
Strava-sourced comparison should store Strava's value in its own table (for example
`homelab.activity_strava_workout_type`) rather than as rows here, so the user's own tags and
Strava's stay separately comparable.

### Fork-only activity types

`activities.activity_type` is a plain integer that upstream numbers sequentially (1–47 as of
v0.19.3), so the fork's own types start at **1001**. Taking upstream's next number would let a
later release reuse it, and every activity already stored with it would silently change type.
No migration is involved; the id only needs adding to the two mappings, both marked
`homelab fork`: `ACTIVITY_ID_TO_NAME` / `ACTIVITY_NAME_TO_ID` in
`backend/app/activities/activity/utils.py` and `ACTIVITY_TYPE_LABEL_KEYS` (plus
`NON_DISTANCE_TYPES` where it applies) in `frontend/src/features/activities/utils/activityType.ts`,
with an English label in `activities.json` (other locales fall back to it). Tests are in
`backend/tests/homelab/test_activity_types.py` and `frontend/src/__tests__/homelabActivityTypes.spec.ts`.

| Id | Type |
|---|---|
| 1001 | Physical therapy |

On a rollback to vanilla Endurain these activities show as "Workout" in the frontend (and
"Unknown" in the backend's per-type counts); nothing fails.

### Speed and pace streams

Upstream's FIT importer ignores the record's `enhanced_speed` and derives speed from the
distance between consecutive 1 s GPS fixes, which is mostly position error: on a 9:23/mi run
the samples swing from 7:00 to 14:12 (1st–99th percentile) where the watch's own speed stays
within 8:33–11:03. The fork's importer (`_handle_record_frame` in `utils_fit.py`, marked
`homelab fork`) stores the device speed and keeps GPS only as the fallback. Indoor runs with a
device speed now also get a speed/pace stream.

**Backfill for older imports.** `backend/app/homelab/fit_speed_backfill.py` re-reads each
activity's `processed/<id>.fit` and rewrites only its existing speed (5) and pace (6) stream rows,
cut to the activity's start/end. It only parses record messages, because the importer's session
handler geocodes over the network. Data only, no schema; a rollback to vanilla keeps working.
In the backend container, from `/app/backend` (about 6 min for 1,400 files):

```sh
python -m homelab.fit_speed_backfill                    # dry run, prints counts
python -m homelab.fit_speed_backfill --apply [--activity-id N]
```

Run on the dev copy on 2026-10-16 (`updated 1403, not_fit 69`: the GPX/TCX imports keep their
GPS-derived streams). **Not yet run on production**; it is needed once after the first deploy
that contains the importer change.

**Pace chart.** `frontend/src/features/activities/utils/homelabPaceChart.ts` shapes the pace chart
like Garmin's: faster pace on top, a y-axis from the 1st–99th percentile snapped to clock-friendly
steps, speed-averaged smoothing (5 samples, or 21 when the series is GPS-derived), a dashed
average-pace line, and at most six x-axis labels on every stream chart. It needs the chart
provider options `yRange`, `xMaxTicks` and a series' `legend: false` (upstream edits in
`useChartProvider.ts` and `chartJsChartProvider.ts`).

## Dev stack

Runs on the Claude session host (`johns-mac-mini-old`) in OrbStack, with a **copy of
production** in it. One script drives it:

```sh
homelab/dev/dev up          # first run: build the image, copy prod, start
homelab/dev/dev seed        # re-copy prod (last night's dump); --fresh for a live pg_dump
homelab/dev/dev down | logs [svc] | psql | status | rebuild | reset
```

| URL | Serves |
|---|---|
| `http://johns-mac-mini-old.local:5173` | **use this.** Vite dev server: frontend from this checkout, hot-reloaded, proxying `/api` and the media mounts to the backend |
| `http://johns-mac-mini-old.local:8092` | the backend directly: backend code from this checkout (auto-reload) plus the frontend baked into `endurain-dev:local` at its last build. `/docs` is the live OpenAPI UI |

Log in with your **production** username and password; it is a copy of the production DB.

- **Backend edits apply on save** (uvicorn reload). A change to `backend/pyproject.toml` or
  `uv.lock` needs `dev rebuild`. **Frontend edits hot-reload**; `package-lock.json` changes are
  picked up on the next frontend container start.
- **The copy can never talk to Garmin or Strava.** `dev seed` nulls every Garmin and Strava
  token before the backend starts, and `dev up` refuses to start if one is present. The
  backend pulls Garmin on startup and hourly, and a second session from the home IP is what
  got Garmin's 429s in October 2026. The dev `FERNET_KEY` also differs from production's, so a
  token copied in by any other route would not decrypt. To work on the Garmin integration
  itself, link a dev session deliberately and expect it to compete with production's.
- **Seeding is read-only on macmini**: an `scp` of `kopia-hot/endurain.dump` (or `pg_dump`
  with `--fresh`) and an `rsync` pull of `backend/data/`.
- **Whichever checkout last ran `dev up` is what is served.** The compose project name is
  fixed, so a session in a worktree repoints the stack at its own tree.
- **Data lives outside `~/code`**, in `~/.local/share/endurain-dev` (secrets in its `.env`,
  ~1.5 GB of photos and files) and two Docker volumes, because `~/code` is a Kopia source.
- Running a migration in dev (see Database) changes only the dev copy; `dev seed` resets it.
- OrbStack on this host also holds the **old homelab's 27 containers, all `restart=no`**, left
  from the September 2026 migration. Starting OrbStack does not start them; don't start them.

## Release to production

**`homelab/deploy` does steps 2–4** once the push has built an image: it waits for the build,
pins the tag and digest in homelab-ops (commit and push), takes the dump, pulls, restarts,
waits for healthy, lists the migrations that ran and any new startup errors, and probes both
hostnames. `homelab/deploy <commit>` deploys or rolls back to that commit's image, and
`--dry-run` checks without changing anything. It refuses to run if production's compose file
has drifted from homelab-ops. In a Claude session, `/deploy-homelab` wraps it. The steps by
hand:

1. Push to `homelab`. The **Homelab image** workflow runs the backend and frontend tests and
   then pushes `ghcr.io/johntevans/endurain:<upstream tag>-homelab-<sha7>` plus a moving
   `homelab` tag. The run summary prints the exact `image:` line to use, with its digest.
2. In homelab-ops, set that line in `mac-mini/endurain/docker-compose.yml` (pinned by digest,
   per that repo's convention), commit, and copy the file to `macmini:~/Server/endurain/`.
3. On macmini: take a dump first
   (`~/Server/kopia/hooks/pre-endurain-pgdump.sh`), then
   `docker compose pull && docker compose up -d`, and watch `docker compose logs -f endurain`
   until startup completes.
4. Check: Gatus `endurain` green, a login on both hostnames, and if the frontend's
   `window.env` keys changed, the hand-written `/env.js` in the `.dev` nginx vhost
   (`pi4-core/nginx/sites-available/endurain` in homelab-ops).

**Rollback** is the previous digest in the compose file, or upstream's
`ghcr.io/endurain-project/endurain:<tag>@<digest>`, which works only while the Database rules
above have been kept.
