"""
JSON file storage for batches and posts.

Design goals for Raspberry Pi reliability:
- Atomic writes (temp file + rename) to avoid corruption on power loss
- One file per batch for simple backups and git-friendly exports
- Index file for fast batch listing without loading every post body
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from agent.models import Batch, Post, PostStatus, utc_now_iso

logger = logging.getLogger("redbeard.storage")


class Storage:
    """Filesystem-backed repository for content batches."""

    def __init__(self, posts_dir: Path, exports_dir: Path | None = None):
        self.posts_dir = Path(posts_dir)
        self.exports_dir = Path(exports_dir) if exports_dir else self.posts_dir.parent / "exports"
        self.posts_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.posts_dir / "index.json"

    # ------------------------------------------------------------------
    # Low-level IO
    # ------------------------------------------------------------------

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        """Write JSON atomically via temp file in the same directory."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _batch_path(self, batch_id: str) -> Path:
        # Sanitize id to a safe filename
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in batch_id)
        return self.posts_dir / f"{safe}.json"

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def _load_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            with self.index_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt index.json, rebuilding: %s", exc)
            return self.rebuild_index()

    def _save_index(self, entries: list[dict[str, Any]]) -> None:
        # Newest first
        entries = sorted(entries, key=lambda e: e.get("created_at", ""), reverse=True)
        self._atomic_write_json(self.index_path, entries)

    def rebuild_index(self) -> list[dict[str, Any]]:
        """Scan posts_dir and rebuild index.json."""
        entries: list[dict[str, Any]] = []
        for path in self.posts_dir.glob("batch_*.json"):
            try:
                batch = self.load_batch_from_path(path)
                entries.append(self._index_entry(batch))
            except Exception as exc:
                logger.error("Skip unreadable batch %s: %s", path, exc)
        self._save_index(entries)
        logger.info("Rebuilt index with %d batches", len(entries))
        return entries

    def _index_entry(self, batch: Batch) -> dict[str, Any]:
        counts = batch.status_counts()
        return {
            "id": batch.id,
            "label": batch.label,
            "created_at": batch.created_at,
            "counts": counts,
        }

    def _upsert_index(self, batch: Batch) -> None:
        entries = self._load_index()
        entries = [e for e in entries if e.get("id") != batch.id]
        entries.append(self._index_entry(batch))
        self._save_index(entries)

    # ------------------------------------------------------------------
    # Batch CRUD
    # ------------------------------------------------------------------

    def save_batch(self, batch: Batch) -> Path:
        path = self._batch_path(batch.id)
        self._atomic_write_json(path, batch.to_dict())
        self._upsert_index(batch)
        logger.info("Saved batch %s (%d posts) → %s", batch.id, len(batch.posts), path)
        return path

    def load_batch(self, batch_id: str) -> Batch | None:
        path = self._batch_path(batch_id)
        if not path.exists():
            # Try linear search (in case of filename edge cases)
            for p in self.posts_dir.glob("*.json"):
                if p.name == "index.json":
                    continue
                try:
                    b = self.load_batch_from_path(p)
                    if b.id == batch_id:
                        return b
                except Exception:
                    continue
            return None
        return self.load_batch_from_path(path)

    def load_batch_from_path(self, path: Path) -> Batch:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return Batch.from_dict(data)

    def list_batches(self) -> list[dict[str, Any]]:
        entries = self._load_index()
        if not entries:
            entries = self.rebuild_index()
        return entries

    def get_post(self, batch_id: str, post_id: str) -> tuple[Batch, Post] | None:
        batch = self.load_batch(batch_id)
        if not batch:
            return None
        for post in batch.posts:
            if post.id == post_id:
                return batch, post
        return None

    def update_post_status(
        self,
        batch_id: str,
        post_id: str,
        status: PostStatus | str,
        notes: str = "",
    ) -> Post | None:
        batch = self.load_batch(batch_id)
        if not batch:
            return None
        for post in batch.posts:
            if post.id == post_id:
                post.mark(status, notes=notes)
                self.save_batch(batch)
                logger.info(
                    "Post %s in %s → %s",
                    post_id,
                    batch_id,
                    post.status,
                )
                return post
        return None

    def bulk_update_status(
        self,
        batch_id: str,
        post_ids: list[str],
        status: PostStatus | str,
        notes: str = "",
    ) -> int:
        batch = self.load_batch(batch_id)
        if not batch:
            return 0
        id_set = set(post_ids)
        updated = 0
        for post in batch.posts:
            if post.id in id_set:
                post.mark(status, notes=notes)
                updated += 1
        if updated:
            self.save_batch(batch)
        return updated

    # ------------------------------------------------------------------
    # Exports (approved posts for manual publishing)
    # ------------------------------------------------------------------

    def export_approved(self, batch_id: str) -> Path | None:
        """
        Write a human-readable + JSON export of approved posts.
        Does not publish anywhere — safe copy-paste pack only.
        """
        batch = self.load_batch(batch_id)
        if not batch:
            return None

        approved = [
            p for p in batch.posts if p.status in (PostStatus.APPROVED.value, PostStatus.EXPORTED.value)
        ]
        if not approved:
            logger.warning("No approved posts to export in %s", batch_id)
            return None

        stamp = utc_now_iso().replace(":", "").replace("+00:00", "Z")
        base = self.exports_dir / f"{batch.id}_approved_{stamp}"

        # JSON
        json_path = Path(str(base) + ".json")
        payload = {
            "batch_id": batch.id,
            "exported_at": utc_now_iso(),
            "count": len(approved),
            "posts": [p.to_dict() for p in approved],
        }
        self._atomic_write_json(json_path, payload)

        # Markdown copy-paste pack
        md_path = Path(str(base) + ".md")
        lines = [
            f"# RedBeard Risk — Approved Posts",
            f"",
            f"**Batch:** {batch.id}",
            f"**Exported:** {utc_now_iso()}",
            f"**Count:** {len(approved)}",
            f"",
            "---",
            "",
        ]
        for i, post in enumerate(approved, 1):
            lines.extend(
                [
                    f"## {i}. {post.platform.upper()} — {post.title}",
                    f"",
                    f"- Pillar: `{post.pillar}`",
                    f"- Industry: `{post.industry}`",
                    f"- Status: `{post.status}`",
                    f"- ID: `{post.id}`",
                    f"",
                    "### Copy-paste body",
                    f"",
                    "```",
                    post.display_text(),
                    "```",
                    f"",
                    "---",
                    f"",
                ]
            )
            post.mark(PostStatus.EXPORTED)

        md_path.write_text("\n".join(lines), encoding="utf-8")
        self.save_batch(batch)
        logger.info("Exported %d approved posts → %s", len(approved), md_path)
        return md_path
