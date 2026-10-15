"""Homelab fork additions to the Endurain backend.

Everything here is fork-owned. Its data lives in fork-owned tables in the
``homelab`` Postgres schema, managed by a second Alembic environment
(``homelab/alembic``) that runs at startup after upstream's. Upstream never
sees these tables, so upstream's image keeps working against the same
database. See ``homelab/README.md`` (repository root) -> Database.
"""
