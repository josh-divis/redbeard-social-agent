"""
Export approved posts for manual publishing.

Safety: this module never calls social network APIs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent.config import AppConfig
from agent.storage import Storage

logger = logging.getLogger("redbeard.publishing")


def export_batch_approved(cfg: AppConfig, batch_id: str) -> Path | None:
    """Export approved posts in a batch to data/exports/."""
    if cfg.safety.auto_post_enabled:
        logger.error(
            "Refusing to run any publisher path while auto_post_enabled is true "
            "until a dedicated, tested publisher exists."
        )
        # Still allow export of copy-paste files — export is not posting
        pass

    storage = Storage(cfg.posts_dir, cfg.exports_dir)
    path = storage.export_approved(batch_id)
    if path:
        logger.info("Export ready: %s", path)
    return path
