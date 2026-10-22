"""Homelab fork: Eight Sleep as the source of sleep data.

Eight Sleep has no public API. This talks to the private endpoints its mobile
app uses (the same ones the Home Assistant integration and pyEight use), so it
can break whenever Eight Sleep changes them; a stalled sync is what the
homelab-ops ``endurain-garmin`` Healthchecks check watches for.

Configured by two environment variables, ``EIGHT_SLEEP_EMAIL`` and
``EIGHT_SLEEP_PASSWORD``. When they are set, Eight Sleep owns sleep: the
upstream Garmin health sync skips its sleep fetch, because both write one row
per date and would otherwise overwrite each other. Nothing is stored in the
database except the ``health_sleep`` rows themselves (``source='eight_sleep'``).
"""
