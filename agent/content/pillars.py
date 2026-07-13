"""
Content pillar definitions and batch mix planning.

Maps the four strategic pillars to concrete angle seeds so generation
stays on-brand for Arizona trade businesses without sounding repetitive.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from agent.models import Pillar, Platform


# Seed angles keep outputs varied across batches without hard-coding full posts.
PILLAR_SEEDS: dict[str, list[str]] = {
    Pillar.PROBLEM_SOLUTION.value: [
        "Office manager locked out of email the morning payroll runs",
        "Tech's phone has all the customer texts and no backup",
        "Insurance questionnaire asking about MFA and the shop has none",
        "Shared Facebook login for the company page among five people",
        "Old laptop still has admin rights and QuickBooks",
        "Vendor emailed a 'past due invoice' PDF that wasn't real",
        "Dispatch software down during a 115° Phoenix afternoon rush",
        "Former employee still has access to the Google Workspace",
        "Ransomware scare story from a peer contractor (anonymized)",
        "Wi-Fi password written on the whiteboard in the break room",
        "GC requiring proof of cyber controls before bid award",
        "Home-office computer doubles as kids' gaming PC",
    ],
    Pillar.EDUCATIONAL.value: [
        "What MFA actually is in plain English (and why SMS is better than nothing)",
        "3-2-1 backup rule for a 12-truck shop",
        "How to check if your business email was in a breach",
        "Password manager vs sticky notes — 10-minute setup",
        "Who should be an admin on your Google/Microsoft account",
        "What to ask an MSP before you sign (trade-shop edition)",
        "Cyber insurance questionnaire: the five questions that trip contractors up",
        "Separating personal and company phones for field techs",
        "Safe way to share job photos with customers",
        "End-of-year IT checklist for Arizona trade owners",
        "How phishing texts target HVAC/plumbing dispatchers",
        "Simple offboarding checklist when a tech leaves",
    ],
    Pillar.LOCAL_BTS.value: [
        "Monday morning in Mesa — coffee and ticket triage for trade shops",
        "Why East Valley shops get hit with the same scams as big Phoenix firms",
        "Summer heat + after-hours emergency calls = rushed clicks on bad links",
        "Walking a plumbing shop through their first Cyber Risk Snapshot",
        "What we notice on a first visit to a 20-year-old electrical company",
        "Behind the scenes: writing a plain-English risk report (no jargon)",
        "Supporting a GC's insurance renewal from the East Valley",
        "Trade school grads vs. career techs — different tech habits, same risks",
        "Local networking: what owners actually want to hear about IT",
        "Rainy monsoon week = more people working from home on weak setups",
        "A day supporting HVAC dispatch during a heat wave",
        "Why 'we'll do IT later' is an Arizona small-business classic",
    ],
    Pillar.OPINION.value: [
        "Your cousin who 'knows computers' is not a security plan",
        "Most MSPs talk like lawyers — trades need wrench-talk",
        "If your IT guy can't explain it in one sentence, push back",
        "Cyber insurance without basic controls is just expensive paper",
        "Buying new laptops won't fix a shared password culture",
        "Compliance checkboxes ≠ actually being hard to hack",
        "Free consumer antivirus is not a business strategy",
        "The real cost of downtime for a plumbing company isn't the software fee",
        "Stop waiting for a perfect IT plan — start with MFA this week",
        "Big enterprise security tools on a 8-person shop is theater",
        "If you wouldn't leave the shop unlocked, don't leave the inbox open",
        "Month-to-month IT support beats a 36-month contract you don't understand",
    ],
}


@dataclass(frozen=True)
class ContentSlot:
    """One planned post slot in a batch."""

    pillar: str
    platform: str
    industry: str
    seed_angle: str


def weighted_pillar_choices(pillars_cfg: dict[str, Any], n: int, rng: random.Random) -> list[str]:
    """Sample n pillars according to configured weights."""
    keys: list[str] = []
    weights: list[float] = []
    for key, meta in pillars_cfg.items():
        if not isinstance(meta, dict):
            continue
        keys.append(key)
        weights.append(float(meta.get("weight", 0.25)))
    if not keys:
        keys = [p.value for p in Pillar]
        weights = [1.0] * len(keys)

    # Normalize and sample with replacement for variety
    total = sum(weights) or 1.0
    probs = [w / total for w in weights]
    return rng.choices(keys, weights=probs, k=n)


def enabled_platforms(platforms_cfg: dict[str, Any]) -> list[str]:
    """Return platform keys that are enabled."""
    out: list[str] = []
    for key, meta in platforms_cfg.items():
        if isinstance(meta, dict) and meta.get("enabled", True):
            out.append(key)
        elif meta is True:
            out.append(key)
    if not out:
        out = [p.value for p in Platform]
    return out


def plan_batch_slots(
    *,
    posts_per_batch: int,
    pillars_cfg: dict[str, Any],
    platforms_cfg: dict[str, Any],
    industries: list[str],
    seed: int | None = None,
) -> list[ContentSlot]:
    """
    Build a balanced list of ContentSlots for one generation run.

    Spreads platforms round-robin, picks pillars by weight, and rotates
    industries and seed angles so batches don't feel copy-pasted.
    """
    rng = random.Random(seed)
    platforms = enabled_platforms(platforms_cfg)
    if not industries:
        industries = ["HVAC", "Plumbing", "Electrical", "Construction"]

    pillars = weighted_pillar_choices(pillars_cfg, posts_per_batch, rng)
    # Prefer roughly even platform distribution
    platform_cycle = [platforms[i % len(platforms)] for i in range(posts_per_batch)]
    rng.shuffle(platform_cycle)

    used_angles: dict[str, set[str]] = {k: set() for k in PILLAR_SEEDS}
    slots: list[ContentSlot] = []

    for i in range(posts_per_batch):
        pillar = pillars[i]
        platform = platform_cycle[i]
        industry = industries[i % len(industries)]
        # Slight shuffle of industry
        if rng.random() < 0.35:
            industry = rng.choice(industries)

        seeds = PILLAR_SEEDS.get(pillar, PILLAR_SEEDS[Pillar.EDUCATIONAL.value])
        available = [s for s in seeds if s not in used_angles[pillar]]
        if not available:
            used_angles[pillar].clear()
            available = list(seeds)
        angle = rng.choice(available)
        used_angles[pillar].add(angle)

        slots.append(
            ContentSlot(
                pillar=pillar,
                platform=platform,
                industry=industry,
                seed_angle=angle,
            )
        )

    return slots
