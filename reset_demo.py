"""Rebuild the local synthetic database. This is a command, not a web route."""

from __future__ import annotations

import os

from app import create_app
from app.db import init_db


def main() -> None:
    database = os.environ.get("DATABASE_PATH") or os.path.join("instance", "docbooker.db")
    if os.path.exists(database):
        os.remove(database)
    init_db(database)
    print(f"Reset the synthetic demo database at {database}")


if __name__ == "__main__":
    main()
