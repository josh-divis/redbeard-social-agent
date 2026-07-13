"""
Flask dashboard for batch review and approval.

Design priorities for Pi 5 local use:
- No external CDN required for core layout (inline-friendly CSS file)
- Simple password gate via session (optional)
- Approve / reject / bulk actions without ever calling social APIs
"""

from __future__ import annotations

import logging
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from agent.config import AppConfig, load_config
from agent.models import PostStatus
from agent.publishing.exporter import export_batch_approved
from agent.storage import Storage

logger = logging.getLogger("redbeard.dashboard")

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(cfg: AppConfig | None = None) -> Flask:
    """Application factory."""
    cfg = cfg or load_config(require_api_key=False)
    cfg.ensure_directories()

    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR),
    )
    app.secret_key = cfg.dashboard.secret_key
    app.config["RED_BEARD_CFG"] = cfg

    storage = Storage(cfg.posts_dir, cfg.exports_dir)

    # ------------------------------------------------------------------
    # Auth helper (optional password)
    # ------------------------------------------------------------------

    def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if cfg.dashboard.password:
                if not session.get("authenticated"):
                    return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {
            "brand_name": (cfg.brand or {}).get("name", "RedBeard Risk"),
            "auto_post": cfg.safety.auto_post_enabled,
            "require_approval": cfg.safety.require_human_approval,
        }

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not cfg.dashboard.password:
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            pw = request.form.get("password", "")
            if pw == cfg.dashboard.password:
                session["authenticated"] = True
                nxt = request.args.get("next") or url_for("index")
                return redirect(nxt)
            error = "Incorrect password"
            logger.warning("Failed dashboard login attempt")
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login" if cfg.dashboard.password else "index"))

    @app.route("/")
    @login_required
    def index():
        batches = storage.list_batches()
        # Enrich with pending counts for the cards
        return render_template("index.html", batches=batches)

    @app.route("/batch/<batch_id>")
    @login_required
    def batch_detail(batch_id: str):
        batch = storage.load_batch(batch_id)
        if not batch:
            abort(404)
        status_filter = request.args.get("status", "all")
        platform_filter = request.args.get("platform", "all")
        posts = batch.posts
        if status_filter != "all":
            posts = [p for p in posts if p.status == status_filter]
        if platform_filter != "all":
            posts = [p for p in posts if p.platform == platform_filter]
        return render_template(
            "batch.html",
            batch=batch,
            posts=posts,
            status_filter=status_filter,
            platform_filter=platform_filter,
            counts=batch.status_counts(),
        )

    @app.route("/batch/<batch_id>/post/<post_id>")
    @login_required
    def post_detail(batch_id: str, post_id: str):
        result = storage.get_post(batch_id, post_id)
        if not result:
            abort(404)
        batch, post = result
        return render_template("post.html", batch=batch, post=post)

    @app.route("/batch/<batch_id>/post/<post_id>/action", methods=["POST"])
    @login_required
    def post_action(batch_id: str, post_id: str):
        action = request.form.get("action", "").lower()
        notes = request.form.get("notes", "").strip()
        status_map = {
            "approve": PostStatus.APPROVED,
            "reject": PostStatus.REJECTED,
            "reset": PostStatus.DRAFT,
        }
        if action not in status_map:
            flash("Unknown action", "error")
            return redirect(url_for("post_detail", batch_id=batch_id, post_id=post_id))

        post = storage.update_post_status(batch_id, post_id, status_map[action], notes=notes)
        if not post:
            flash("Post not found", "error")
            return redirect(url_for("batch_detail", batch_id=batch_id))

        flash(f"Post marked {post.status}", "success")
        # Stay in batch view for fast review flow
        return redirect(url_for("batch_detail", batch_id=batch_id, status="draft"))

    @app.route("/batch/<batch_id>/bulk", methods=["POST"])
    @login_required
    def bulk_action(batch_id: str):
        action = request.form.get("action", "").lower()
        post_ids = request.form.getlist("post_ids")
        notes = request.form.get("notes", "").strip()

        status_map = {
            "approve": PostStatus.APPROVED,
            "reject": PostStatus.REJECTED,
            "reset": PostStatus.DRAFT,
        }
        if action not in status_map or not post_ids:
            flash("Select at least one post and an action", "error")
            return redirect(url_for("batch_detail", batch_id=batch_id))

        n = storage.bulk_update_status(batch_id, post_ids, status_map[action], notes=notes)
        flash(f"Updated {n} post(s) → {status_map[action].value}", "success")
        return redirect(url_for("batch_detail", batch_id=batch_id))

    @app.route("/batch/<batch_id>/export", methods=["POST"])
    @login_required
    def export_batch(batch_id: str):
        path = export_batch_approved(cfg, batch_id)
        if path:
            flash(f"Exported approved posts → {path.name} (see data/exports/)", "success")
        else:
            flash("No approved posts to export", "error")
        return redirect(url_for("batch_detail", batch_id=batch_id))

    @app.route("/health")
    def health():
        return {
            "status": "ok",
            "app": "redbeard-social-agent",
            "auto_post_enabled": cfg.safety.auto_post_enabled,
        }

    logger.info("Dashboard app created (password_gate=%s)", bool(cfg.dashboard.password))
    return app
