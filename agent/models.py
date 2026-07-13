"""
Domain models for posts, batches, and review workflow.

Posts are stored as JSON on disk for reliability on a Pi (no DB required).
Statuses enforce the human-in-the-loop pipeline: draft → approved | rejected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    """Return timezone-aware UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PostStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"
    # Reserved for a future publisher — never set by generation in v1
    PUBLISHED = "published"


class Platform(str, Enum):
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"


class Pillar(str, Enum):
    PROBLEM_SOLUTION = "problem_solution"
    EDUCATIONAL = "educational"
    LOCAL_BTS = "local_bts"
    OPINION = "opinion"


@dataclass
class Post:
    """A single social post draft awaiting human review."""

    id: str
    batch_id: str
    platform: str
    pillar: str
    industry: str
    title: str
    body: str
    hashtags: list[str] = field(default_factory=list)
    cta: str = ""
    status: str = PostStatus.DRAFT.value
    notes: str = ""  # reviewer notes
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    reviewed_at: str | None = None
    model: str = ""
    prompt_version: str = "1.0"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        batch_id: str,
        platform: str,
        pillar: str,
        industry: str,
        title: str,
        body: str,
        hashtags: list[str] | None = None,
        cta: str = "",
        model: str = "",
        extra: dict[str, Any] | None = None,
    ) -> "Post":
        return cls(
            id=str(uuid4()),
            batch_id=batch_id,
            platform=platform,
            pillar=pillar,
            industry=industry,
            title=title,
            body=body,
            hashtags=hashtags or [],
            cta=cta,
            model=model,
            extra=extra or {},
        )

    def mark(self, status: PostStatus | str, notes: str = "") -> None:
        self.status = status.value if isinstance(status, PostStatus) else status
        if notes:
            self.notes = notes
        self.updated_at = utc_now_iso()
        self.reviewed_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Post":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def display_text(self) -> str:
        """Full copy suitable for paste into a social network."""
        parts = [self.body.strip()]
        if self.hashtags:
            tags = " ".join(
                t if t.startswith("#") else f"#{t}" for t in self.hashtags
            )
            parts.append(tags)
        return "\n\n".join(p for p in parts if p)


@dataclass
class Batch:
    """A generation run producing multiple posts for review."""

    id: str
    created_at: str
    label: str
    posts: list[Post] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, label: str = "", meta: dict[str, Any] | None = None) -> "Batch":
        ts = utc_now_iso()
        batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        return cls(
            id=batch_id,
            created_at=ts,
            label=label or f"Batch {ts[:10]}",
            posts=[],
            meta=meta or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "label": self.label,
            "meta": self.meta,
            "posts": [p.to_dict() for p in self.posts],
            "counts": self.status_counts(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Batch":
        posts = [Post.from_dict(p) for p in data.get("posts", [])]
        return cls(
            id=data["id"],
            created_at=data.get("created_at", utc_now_iso()),
            label=data.get("label", ""),
            posts=posts,
            meta=data.get("meta", {}) or {},
        )

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for post in self.posts:
            counts[post.status] = counts.get(post.status, 0) + 1
        counts["total"] = len(self.posts)
        return counts

    def pending_posts(self) -> list[Post]:
        return [p for p in self.posts if p.status == PostStatus.DRAFT.value]
