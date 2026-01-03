from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from services.pipeline.specs import SectionBudget


class ProfileName(str, Enum):
    FAST = "fast"
    DEFAULT = "default"
    HEAVY = "heavy"


@dataclass
class GenerationProfile:
    name: str
    description: str

    default_budget: SectionBudget
    target_words_multiplier: float = 1.0

    model: str | None = None
    temperature: float = 0.7

    max_facts: int = 30
    summary_bullets: tuple[int, int] = (5, 8)

    overrides: dict[str, Any] = field(default_factory=dict)

    def get_budget_for_section(self, section_key: str) -> SectionBudget:
        if section_key in self.overrides:
            override = self.overrides[section_key]
            return SectionBudget(
                max_input_tokens=override.get("max_input_tokens", self.default_budget.max_input_tokens),
                max_output_tokens=override.get("max_output_tokens", self.default_budget.max_output_tokens),
                temperature=override.get("temperature", self.default_budget.temperature),
            )
        return self.default_budget

    def get_target_words(self, base_min: int, base_max: int) -> tuple[int, int]:
        return (
            int(base_min * self.target_words_multiplier),
            int(base_max * self.target_words_multiplier),
        )


PROFILE_FAST = GenerationProfile(
    name="fast",
    description="Quick generation with smaller outputs",
    default_budget=SectionBudget(
        max_input_tokens=2000,
        max_output_tokens=1000,
        temperature=0.5,
    ),
    target_words_multiplier=0.6,
    max_facts=15,
    summary_bullets=(3, 5),
)


PROFILE_DEFAULT = GenerationProfile(
    name="default",
    description="Balanced generation with standard outputs",
    default_budget=SectionBudget(
        max_input_tokens=4000,
        max_output_tokens=2000,
        temperature=0.7,
    ),
    target_words_multiplier=1.0,
    max_facts=30,
    summary_bullets=(5, 8),
)


PROFILE_HEAVY = GenerationProfile(
    name="heavy",
    description="Thorough generation with larger outputs",
    default_budget=SectionBudget(
        max_input_tokens=6000,
        max_output_tokens=3000,
        temperature=0.8,
    ),
    target_words_multiplier=1.5,
    max_facts=50,
    summary_bullets=(7, 10),
    overrides={
        "implementation": {
            "max_input_tokens": 8000,
            "max_output_tokens": 4000,
        },
        "architecture": {
            "max_input_tokens": 7000,
            "max_output_tokens": 3500,
        },
    },
)


PROFILES: dict[str, GenerationProfile] = {
    "fast": PROFILE_FAST,
    "default": PROFILE_DEFAULT,
    "heavy": PROFILE_HEAVY,
}


def get_profile(name: str) -> GenerationProfile:
    if name not in PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {list(PROFILES.keys())}")
    return PROFILES[name]


def list_profiles() -> list[str]:
    return list(PROFILES.keys())
