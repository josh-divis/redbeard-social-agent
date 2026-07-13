"""Unit tests that run without an API key."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.content.pillars import plan_batch_slots
from agent.models import Batch, Post, PostStatus
from agent.storage import Storage


def test_post_display_text_includes_hashtags():
    p = Post.create(
        batch_id="b1",
        platform="linkedin",
        pillar="educational",
        industry="HVAC",
        title="Test",
        body="Hello shop.",
        hashtags=["ArizonaTrades", "#MesaAZ"],
    )
    text = p.display_text()
    assert "Hello shop." in text
    assert "#ArizonaTrades" in text
    assert "#MesaAZ" in text


def test_storage_roundtrip(tmp_path: Path):
    posts_dir = tmp_path / "posts"
    exports_dir = tmp_path / "exports"
    store = Storage(posts_dir, exports_dir)

    batch = Batch.create(label="Test batch")
    batch.posts.append(
        Post.create(
            batch_id=batch.id,
            platform="facebook",
            pillar="opinion",
            industry="Plumbing",
            title="T",
            body="Body text",
        )
    )
    store.save_batch(batch)

    loaded = store.load_batch(batch.id)
    assert loaded is not None
    assert loaded.id == batch.id
    assert len(loaded.posts) == 1
    assert loaded.posts[0].body == "Body text"

    post_id = loaded.posts[0].id
    store.update_post_status(batch.id, post_id, PostStatus.APPROVED, notes="LGTM")
    loaded2 = store.load_batch(batch.id)
    assert loaded2.posts[0].status == "approved"
    assert loaded2.posts[0].notes == "LGTM"

    path = store.export_approved(batch.id)
    assert path is not None
    assert path.exists()


def test_plan_batch_slots_count_and_platforms():
    slots = plan_batch_slots(
        posts_per_batch=9,
        pillars_cfg={
            "problem_solution": {"weight": 0.3},
            "educational": {"weight": 0.3},
            "local_bts": {"weight": 0.2},
            "opinion": {"weight": 0.2},
        },
        platforms_cfg={
            "linkedin": {"enabled": True},
            "facebook": {"enabled": True},
            "instagram": {"enabled": True},
        },
        industries=["HVAC", "Plumbing", "Electrical"],
        seed=42,
    )
    assert len(slots) == 9
    platforms = {s.platform for s in slots}
    assert platforms <= {"linkedin", "facebook", "instagram"}
    assert all(s.seed_angle for s in slots)
