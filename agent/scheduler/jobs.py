"""
Scheduled job entrypoints.

Production scheduling on the Raspberry Pi is done with system cron (or
systemd timers). These functions are what cron invokes — they load config,
run one unit of work, log clearly, and exit non-zero on hard failure so
monitoring tools can alert.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from agent.config import load_config
from agent.content.generator import ContentGenerator
from agent.logging_setup import setup_logging
from agent.storage import Storage

logger = logging.getLogger("redbeard.jobs")


def run_generate_job(
    *,
    count: int | None = None,
    label: str = "",
    seed: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Generate a review batch. Intended for:
      python -m agent.cli generate
      or cron: 0 8 * * 1,4 cd /path && .venv/bin/python -m agent.cli generate
    """
    cfg = load_config(require_api_key=not dry_run)
    setup_logging(cfg)
    logger.info("=== generate job start dry_run=%s ===", dry_run)

    if cfg.safety.auto_post_enabled:
        logger.warning(
            "AUTO_POST is somehow enabled — forcing off for this run (v1 safety)"
        )

    try:
        gen = ContentGenerator(cfg, allow_missing_llm=dry_run)
        batch = gen.generate_batch(
            count=count,
            label=label,
            seed=seed,
            dry_run=dry_run,
        )
    except Exception:
        logger.exception("Generate job failed")
        raise

    counts = batch.status_counts()
    summary = {
        "batch_id": batch.id,
        "counts": counts,
        "path": str(cfg.posts_dir / f"{batch.id}.json"),
    }
    logger.info("=== generate job done %s ===", summary)
    return summary


def run_status_job() -> dict[str, Any]:
    """Print/return a summary of pending review work (useful for cron mail)."""
    cfg = load_config(require_api_key=False)
    setup_logging(cfg)
    storage = Storage(cfg.posts_dir, cfg.exports_dir)
    batches = storage.list_batches()

    pending_posts = 0
    pending_batches = 0
    for entry in batches:
        counts = entry.get("counts") or {}
        draft = int(counts.get("draft", 0))
        if draft:
            pending_batches += 1
            pending_posts += draft

    summary = {
        "total_batches": len(batches),
        "batches_with_drafts": pending_batches,
        "draft_posts": pending_posts,
        "auto_post_enabled": cfg.safety.auto_post_enabled,
        "dashboard": f"http://{cfg.dashboard.host}:{cfg.dashboard.port}/",
    }
    logger.info("Status: %s", summary)
    return summary


def main_generate() -> None:
    """Module-level cron entry: python -m agent.scheduler.jobs"""
    try:
        run_generate_job()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main_generate()
