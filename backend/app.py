"""UrjaSense AI - Flask application factory.

Run locally from the project root:
    python -m database.database_config      # create tables + sample data
    python -m backend.app                   # http://localhost:5000
"""
import logging
import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, redirect, request
from flask_cors import CORS

from backend.config import Config
from backend.utils.validation import ValidationError
from database.database_config import make_engine

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
log = logging.getLogger("urjasense")


def create_app(overrides: dict | None = None, engine=None) -> Flask:
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        log.warning("SECRET_KEY not set: using a random key for this process (tokens reset on restart).")
    app.config["JSON_AS_ASCII"] = False          # keep Hindi text readable
    app.json.ensure_ascii = False
    app.engine = engine or make_engine()
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"].split(",")}})

    from backend.routes.admin_routes import bp as admin_bp
    from backend.routes.auth_routes import bp as auth_bp
    from backend.routes.lineman_routes import bp as lineman_bp
    from backend.routes.public_routes import bp as public_bp
    from backend.routes.user_routes import bp as user_bp
    for b in (public_bp, auth_bp, user_bp, lineman_bp, admin_bp):
        app.register_blueprint(b)

    @app.before_request
    def _https():
        if app.config["FORCE_HTTPS"] and request.headers.get("X-Forwarded-Proto", "https") != "https":
            return redirect(request.url.replace("http://", "https://", 1), code=301)

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if app.config["FORCE_HTTPS"]:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    from backend.services.incident_service import ServiceError

    @app.errorhandler(ValidationError)
    def _val(e):
        return jsonify(error=e.message, field=e.field), 400

    @app.errorhandler(ServiceError)
    def _svc(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(404)
    def _404(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found"), 404
        return app.send_static_file("index.html")

    @app.errorhandler(405)
    def _405(e):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(Exception)
    def _500(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify(error=e.description), e.code
        log.exception("Unhandled error")
        return jsonify(error="Internal server error"), 500

    @app.route("/")
    def _index():
        return app.send_static_file("index.html")

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")),
                     debug=os.getenv("FLASK_DEBUG", "0") == "1")
