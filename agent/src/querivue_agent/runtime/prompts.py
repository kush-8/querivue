"""Markdown prompt loading and assembly for agent roles."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

RoleName = Literal[
    "common",
    "entry_assessor",
    "supervisor",
    "sql_specialist",
    "python_specialist",
    "answer_specialist",
    "reviewer",
    "clarification_agent",
    "schema_repair",
    "single_analysis_baseline",
]

PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"

# Mapping from role name to prompt file (without .md extension)
PROMPT_FILES: dict[RoleName, str] = {
    "common": "common_policy",
    "entry_assessor": "entry_assessor",
    "supervisor": "supervisor",
    "sql_specialist": "sql_specialist",
    "python_specialist": "python_specialist",
    "answer_specialist": "answer_specialist",
    "reviewer": "reviewer",
    "clarification_agent": "clarification_agent",
    "schema_repair": "schema_repair",
    "single_analysis_baseline": "single_analysis_baseline",
}


def load_prompt(role: RoleName) -> str:
    """Load a Markdown prompt template by role name."""
    if role not in PROMPT_FILES:
        raise ValueError(f"Unknown role: {role}")

    file_path = PROMPT_DIR / f"{PROMPT_FILES[role]}.md"
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def load_prompt_bundle(roles: list[RoleName]) -> dict[str, str]:
    """Load multiple prompts and return as a dict."""
    return {role: load_prompt(role) for role in roles}


def get_common_policy() -> str:
    """Get the common policy prompt."""
    return load_prompt("common")


def assemble_role_prompt(role: RoleName) -> str:
    """Assemble a complete prompt by combining common policy with role-specific prompt."""
    common = get_common_policy()
    role_prompt = load_prompt(role)
    return f"{common}\n\n{role_prompt}"


def get_prompt_hash(prompt: str) -> str:
    """Compute SHA-256 hash of prompt content for version tracking."""
    import hashlib
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class PromptBundle:
    """Immutable prompt bundle with version tracking."""

    def __init__(
        self,
        common: str,
        role_prompts: dict[RoleName, str],
        bundle_version: str = "querivue-roles-v3",
    ) -> None:
        self._common = common
        self._role_prompts = dict(role_prompts)
        self._bundle_version = bundle_version
        self._hashes = {role: get_prompt_hash(p) for role, p in self._role_prompts.items()}
        self._common_hash = get_prompt_hash(common)

    @property
    def bundle_version(self) -> str:
        return self._bundle_version

    @property
    def common_policy(self) -> str:
        return self._common

    @property
    def common_hash(self) -> str:
        return self._common_hash

    def get_role_prompt(self, role: RoleName) -> str:
        """Get role-specific prompt (without common policy)."""
        if role not in self._role_prompts:
            raise ValueError(f"Role not in bundle: {role}")
        return self._role_prompts[role]

    def get_role_hash(self, role: RoleName) -> str:
        """Get SHA-256 hash of role prompt."""
        if role not in self._hashes:
            raise ValueError(f"Role not in bundle: {role}")
        return self._hashes[role]

    def assemble(self, role: RoleName) -> str:
        """Assemble full prompt for a role (common + role)."""
        return f"{self._common}\n\n{self._role_prompts[role]}"

    def assemble_all(self) -> dict[RoleName, str]:
        """Assemble full prompts for all roles in bundle."""
        return {role: self.assemble(role) for role in self._role_prompts}


def load_prompt_bundle_v3() -> PromptBundle:
    """Load the v3 prompt bundle with all roles."""
    common = get_common_policy()
    roles = [
        "entry_assessor",
        "supervisor",
        "sql_specialist",
        "python_specialist",
        "answer_specialist",
        "reviewer",
        "clarification_agent",
        "schema_repair",
        "single_analysis_baseline",
    ]
    role_prompts = {role: load_prompt(role) for role in roles}
    return PromptBundle(common=common, role_prompts=role_prompts)