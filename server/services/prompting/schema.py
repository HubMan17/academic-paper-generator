from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class OutlineMode(str, Enum):
    FULL = "full"
    STRUCTURE = "structure"
    LOCAL = "local"


@dataclass
class Budget:
    max_input_tokens_approx: int
    max_output_tokens: int
    soft_char_limit: int
    estimated_input_tokens: int = 0


@dataclass
class FactRef:
    fact_id: str
    reason: str
    weight: Optional[float] = None


@dataclass
class ContextLayer:
    global_context: str = ""
    outline_excerpt: str = ""
    outline_points: str = ""
    facts_slice: str = ""
    summaries: str = ""
    constraints: str = ""


@dataclass
class RenderedPrompt:
    system: str
    user: str


@dataclass
class DebugInfo:
    selected_fact_refs: list[FactRef] = field(default_factory=list)
    selection_reason: str = ""
    trims_applied: list[str] = field(default_factory=list)


@dataclass
class ContextPack:
    section_key: str
    layers: ContextLayer
    rendered_prompt: RenderedPrompt
    budget: Budget
    debug: DebugInfo


@dataclass
class SectionSpec:
    key: str
    fact_tags: list[str] = field(default_factory=list)
    fact_keys: list[str] = field(default_factory=list)
    outline_mode: OutlineMode = OutlineMode.FULL
    needs_summaries: bool = True
    style_profile: str = "academic"
    target_chars: tuple[int, int] = (3000, 6000)
    constraints: list[str] = field(default_factory=list)
