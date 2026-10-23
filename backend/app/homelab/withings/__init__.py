"""Homelab fork: Withings as the source of body weight.

Withings has an official OAuth 2.0 API, so unlike Eight Sleep no password is
stored: the owner approves access once in a browser (``cli link``), the public
callback exchanges the code for tokens, and the tokens are kept encrypted with
``FERNET_KEY`` in ``homelab.withings_tokens``. Every refresh returns a NEW
refresh token that replaces the old one, which is why they live in the database
and not in ``.env``.

Configured by ``WITHINGS_CLIENT_ID``, ``WITHINGS_CLIENT_SECRET`` and
``WITHINGS_REDIRECT_URI`` (the callback as registered in the Withings
developer dashboard).
"""
