"""DocBooker Flask application."""

from __future__ import annotations

import hmac
import os
import secrets

from flask import Flask, g, jsonify, render_template, request, session

from . import conversation, knowledge
from .db import connect, init_db
from .timeutil import hospital_now

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def create_app(overrides: dict | None = None) -> Flask:
    overrides = dict(overrides or {})
    _load_env(os.path.join(ROOT, ".env"))
    instance = os.path.join(ROOT, "instance")
    os.makedirs(instance, exist_ok=True)

    app = Flask(
        __name__,
        template_folder=os.path.join(ROOT, "templates"),
        static_folder=os.path.join(ROOT, "static"),
    )
    testing = bool(overrides.get("TESTING"))
    secret = overrides.get("SECRET_KEY") or os.environ.get("SECRET_KEY") or ""
    if not secret:
        secret = "test-secret" if testing else _local_secret(os.path.join(instance, "secret_key"))

    prefix = (overrides.get("URL_PREFIX") or os.environ.get("URL_PREFIX") or "").rstrip("/")
    database = overrides.get("DATABASE") or os.environ.get("DATABASE_PATH") or os.path.join(
        instance, "docbooker.db"
    )
    app.config.update(
        SECRET_KEY=secret,
        DATABASE=database,
        URL_PREFIX=prefix,
        SECTIONS=knowledge.load_sections(
            overrides.get("KNOWLEDGE_PATH") or os.path.join(ROOT, "data", "hospital_knowledge.md")
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_PATH=prefix or "/",
        SESSION_COOKIE_NAME="docbooker_session",
        MAX_CONTENT_LENGTH=20_000,
        JSON_SORT_KEYS=False,
        TESTING=testing,
        DEBUG=False,
    )
    app.config.update(overrides)
    app.config["DEBUG"] = False
    app.debug = False
    if str(os.environ.get("COOKIE_SECURE", "")).lower() in {"1", "true", "yes"}:
        app.config["SESSION_COOKIE_SECURE"] = True

    init_db(app.config["DATABASE"])
    if prefix:
        app.wsgi_app = _PrefixMiddleware(app.wsgi_app, prefix)

    @app.after_request
    def secure_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self'; style-src 'self'; "
            "script-src 'self'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.teardown_appcontext
    def close_db(_error):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="docbooker")

    @app.get("/api/bootstrap")
    def bootstrap():
        _ensure_session()
        conn = get_conn()
        now = hospital_now()
        conv = conversation.load_conversation(conn, session["sid"])
        payload = conversation.opening(conn, conv, now)
        conversation.save_conversation(conn, session["sid"], conv, now)
        payload["csrf_token"] = session["csrf"]
        return jsonify(payload)

    @app.post("/api/chat")
    def chat():
        if not _csrf_ok():
            return jsonify(error="Invalid or missing CSRF token."), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Expected a JSON object."), 400
        message = body.get("message", "")
        button = body.get("button", "")
        if not isinstance(message, str) or not isinstance(button, str):
            return jsonify(error="Invalid message."), 400
        _ensure_session()
        conn = get_conn()
        now = hospital_now()
        conv = conversation.load_conversation(conn, session["sid"])
        try:
            payload = conversation.handle_turn(
                conn,
                conv,
                message,
                button,
                app.config["SECTIONS"],
                now,
            )
            conversation.save_conversation(conn, session["sid"], conv, now)
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            app.logger.error("chat handler error: %s", exc.__class__.__name__)
            error = {"error": "The demo could not complete that step."}
            if app.config.get("TESTING"):
                error["error_type"] = exc.__class__.__name__
            return jsonify(error), 500
        payload["csrf_token"] = session["csrf"]
        return jsonify(payload)

    return app


def get_conn():
    if "db" not in g:
        g.db = connect(current_database())
    return g.db


def current_database() -> str:
    from flask import current_app

    return current_app.config["DATABASE"]


def _ensure_session() -> None:
    if not session.get("sid"):
        session["sid"] = secrets.token_urlsafe(32)
    if not session.get("csrf"):
        session["csrf"] = secrets.token_urlsafe(32)


class _PrefixMiddleware:
    """Mount the app at URL_PREFIX before routing runs."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or ""
        if path == self.prefix or path.startswith(self.prefix + "/"):
            rest = path[len(self.prefix):] or "/"
            environ["PATH_INFO"] = rest if rest.startswith("/") else "/" + rest
        environ["SCRIPT_NAME"] = self.prefix
        return self.app(environ, start_response)


def _csrf_ok() -> bool:
    sent = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf", "")
    if not isinstance(sent, str) or not isinstance(expected, str):
        return False
    if not sent or not expected or len(sent) != len(expected):
        return False
    return hmac.compare_digest(sent, expected)


def _local_secret(path: str) -> str:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            existing = handle.read().strip()
        if existing:
            return existing
    generated = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(generated)
    return generated


def _load_env(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
