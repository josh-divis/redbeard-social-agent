"""
Post batch generator.

Plans content slots across pillars/platforms, calls the LLM for each,
validates output, and persists a Batch for human review.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.config import AppConfig
from agent.content.pillars import ContentSlot, plan_batch_slots
from agent.content.prompts import PROMPT_VERSION, batch_system_prompt, build_user_prompt
from agent.llm.client import LLMClient, LLMError
from agent.models import Batch, Post
from agent.storage import Storage

logger = logging.getLogger("redbeard.generator")


class ContentGenerator:
    """Generate reviewable social post batches."""

    def __init__(
        self,
        cfg: AppConfig,
        storage: Storage | None = None,
        llm: LLMClient | None = None,
        *,
        allow_missing_llm: bool = False,
    ):
        self.cfg = cfg
        self.storage = storage or Storage(cfg.posts_dir, cfg.exports_dir)
        self._llm = llm
        self._allow_missing_llm = allow_missing_llm
        if llm is None and not allow_missing_llm:
            if cfg.llm is None or not cfg.llm.api_key:
                raise RuntimeError("LLM is not configured — set XAI_API_KEY in .env")
            self._llm = LLMClient(cfg.llm)

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            if self.cfg.llm is None or not self.cfg.llm.api_key:
                raise RuntimeError("LLM is not configured — set XAI_API_KEY in .env")
            self._llm = LLMClient(self.cfg.llm)
        return self._llm

    def generate_batch(
        self,
        *,
        count: int | None = None,
        label: str = "",
        seed: int | None = None,
        dry_run: bool = False,
    ) -> Batch:
        """
        Generate a full batch of posts.

        dry_run: plan slots and return batch without LLM calls (for testing mix).
        """
        gen = self.cfg.generation or {}
        posts_per_batch = int(count if count is not None else gen.get("posts_per_batch", 12))

        slots = plan_batch_slots(
            posts_per_batch=posts_per_batch,
            pillars_cfg=self.cfg.pillars,
            platforms_cfg=self.cfg.platforms,
            industries=self.cfg.industries,
            seed=seed,
        )

        batch = Batch.create(
            label=label or f"Auto batch ({posts_per_batch} posts)",
            meta={
                "prompt_version": PROMPT_VERSION,
                "model": self.cfg.llm.model if self.cfg.llm else "",
                "provider": self.cfg.llm.provider if self.cfg.llm else "",
                "seed": seed,
                "dry_run": dry_run,
                "slot_count": len(slots),
            },
        )

        logger.info(
            "Generating batch %s — %d slots dry_run=%s",
            batch.id,
            len(slots),
            dry_run,
        )

        failures = 0
        for idx, slot in enumerate(slots, 1):
            logger.info(
                "[%d/%d] %s | %s | %s",
                idx,
                len(slots),
                slot.platform,
                slot.pillar,
                slot.industry,
            )
            if dry_run:
                post = Post.create(
                    batch_id=batch.id,
                    platform=slot.platform,
                    pillar=slot.pillar,
                    industry=slot.industry,
                    title=f"[DRY RUN] {slot.seed_angle[:60]}",
                    body=f"(dry run) Seed angle: {slot.seed_angle}",
                    hashtags=["redbeardrisk"],
                    model="dry-run",
                    extra={"seed_angle": slot.seed_angle},
                )
                batch.posts.append(post)
                continue

            try:
                post = self._generate_one(batch.id, slot)
                batch.posts.append(post)
            except LLMError as exc:
                failures += 1
                logger.error("Failed slot %d: %s", idx, exc)
                # Placeholder so the human sees the gap
                batch.posts.append(
                    Post.create(
                        batch_id=batch.id,
                        platform=slot.platform,
                        pillar=slot.pillar,
                        industry=slot.industry,
                        title="[GENERATION FAILED]",
                        body=f"Generation failed for angle: {slot.seed_angle}\nError: {exc}",
                        model=self.cfg.llm.model if self.cfg.llm else "",
                        extra={"seed_angle": slot.seed_angle, "error": str(exc)},
                    )
                )

        batch.meta["failures"] = failures
        path = self.storage.save_batch(batch)
        logger.info(
            "Batch complete id=%s posts=%d failures=%d path=%s",
            batch.id,
            len(batch.posts),
            failures,
            path,
        )
        return batch

    def _generate_one(self, batch_id: str, slot: ContentSlot) -> Post:
        platform_meta = (self.cfg.platforms or {}).get(slot.platform, {}) or {}
        style = str(platform_meta.get("style", ""))
        max_chars = int(platform_meta.get("max_chars", 2200))

        user_prompt = build_user_prompt(
            pillar=slot.pillar,
            platform=slot.platform,
            industry=slot.industry,
            seed_angle=slot.seed_angle,
            brand=self.cfg.brand,
            services=self.cfg.services,
            platform_style=style,
        )

        data = self.llm.chat_json(
            system=batch_system_prompt(),
            user=user_prompt,
        )
        return self._post_from_llm(batch_id, slot, data, max_chars=max_chars)

    def _post_from_llm(
        self,
        batch_id: str,
        slot: ContentSlot,
        data: dict[str, Any],
        *,
        max_chars: int,
    ) -> Post:
        title = str(data.get("title") or slot.seed_angle[:80]).strip()
        body = str(data.get("body") or "").strip()
        cta = str(data.get("cta") or "").strip()
        hook = str(data.get("hook") or "").strip()

        raw_tags = data.get("hashtags") or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.replace(",", " ").split() if t.strip()]
        hashtags: list[str] = []
        for t in raw_tags:
            t = str(t).strip().lstrip("#")
            if t and t not in hashtags:
                hashtags.append(t)

        if not body:
            raise LLMError("Model returned empty body")

        # Soft truncate to platform max (prefer not to mid-word cut if possible)
        if len(body) > max_chars:
            logger.warning(
                "Body length %d exceeds max %d for %s — truncating",
                len(body),
                max_chars,
                slot.platform,
            )
            body = body[: max_chars - 1].rsplit(" ", 1)[0] + "…"

        # Append CTA to body if model left it separate and body doesn't already include it
        if cta and cta not in body:
            # Keep cta field for UI; body stays clean for editability
            pass

        model_name = self.cfg.llm.model if self.cfg.llm else ""
        return Post.create(
            batch_id=batch_id,
            platform=slot.platform,
            pillar=slot.pillar,
            industry=slot.industry,
            title=title,
            body=body,
            hashtags=hashtags,
            cta=cta,
            model=model_name,
            extra={
                "seed_angle": slot.seed_angle,
                "hook": hook,
                "prompt_version": PROMPT_VERSION,
            },
        )
