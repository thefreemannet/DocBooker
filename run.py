"""Start DocBooker on this computer. Debug mode stays off.

The default host is localhost. Set FLASK_HOST only when a reverse proxy on
another machine on the LAN must reach this process.
"""

from __future__ import annotations

import os

from app import create_app


def main() -> None:
    app = create_app()
    port = int(os.environ.get("FLASK_PORT", "5000"))
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
