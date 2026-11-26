"""Read the administrator-mounted identity shared by every DB client in this container."""

import os
from pathlib import Path

IDENTITY = Path("/run/keiba/database")
PROFILES = {
    "keiba_nlp": ("nlp_app", "nlp_viewer", 8786),
    "keiba_nlp_trial": ("nlp_trial_app", "nlp_trial_viewer", 8787),
}


def database():
    name = IDENTITY.read_text().strip()
    if name not in PROFILES or os.environ.get("NLP_DATABASE", name) != name:
        raise ValueError("Database setting conflicts with the mounted NLP profile")
    return name


def credentials(reader=False):
    name = database()
    user = PROFILES[name][int(reader)]
    return dict(host="192.168.0.14", dbname=name, user=user,
                password=(Path("/run/secrets") / user).read_text().strip())


def trial():
    return database() == "keiba_nlp_trial"
