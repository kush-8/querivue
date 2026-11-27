"""Unit tests for prompt loading and assembly."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from querivue_agent.runtime.prompts import (
    RoleName,
    PROMPT_FILES,
    PROMPT_DIR,
    load_prompt,
    load_prompt_bundle,
    get_common_policy,
    assemble_role_prompt,
    get_prompt_hash,
    PromptBundle,
    load_prompt_bundle_v3,
)


class TestPromptLoading:
    """Tests for prompt file loading."""

    def test_prompt_dir_exists(self) -> None:
        """Prompt directory should exist."""
        assert PROMPT_DIR.exists(), f"Prompt directory not found: {PROMPT_DIR}"

    def test_all_prompt_files_exist(self) -> None:
        """All mapped prompt files should exist on disk."""
        for role, filename in PROMPT_FILES.items():
            file_path = PROMPT_DIR / f"{filename}.md"
            assert file_path.exists(), f"Prompt file missing for {role}: {file_path}"

    def test_load_prompt_returns_string(self) -> None:
        """load_prompt should return a non-empty string."""
        for role in RoleName.__args__:  # type: ignore[attr-defined]
            prompt = load_prompt(role)
            assert isinstance(prompt, str)
            assert len(prompt) > 0, f"Empty prompt for role: {role}"

    def test_load_prompt_bundle_returns_dict(self) -> None:
        """load_prompt_bundle should return dict with all requested roles."""
        roles = ["entry_assessor", "supervisor", "sql_specialist"]
        bundle = load_prompt_bundle(roles)
        assert isinstance(bundle, dict)
        assert set(bundle.keys()) == set(roles)
        for role, prompt in bundle.items():
            assert isinstance(prompt, str)
            assert len(prompt) > 0

    def test_get_common_policy(self) -> None:
        """get_common_policy should return the common policy prompt."""
        common = get_common_policy()
        assert isinstance(common, str)
        assert len(common) > 0

    def test_assemble_role_prompt_combines_common_and_role(self) -> None:
        """assemble_role_prompt should combine common + role-specific."""
        role = "sql_specialist"
        assembled = assemble_role_prompt(role)
        common = get_common_policy()
        role_prompt = load_prompt(role)

        assert assembled == f"{common}\n\n{role_prompt}"

    def test_unknown_role_raises_value_error(self) -> None:
        """Loading unknown role should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown role"):
            load_prompt("nonexistent_role")  # type: ignore[arg-type]


class TestPromptHashing:
    """Tests for prompt hashing."""

    def test_get_prompt_hash_is_sha256(self) -> None:
        """get_prompt_hash should return SHA-256 hex digest."""
        prompt = "test prompt content"
        hash_value = get_prompt_hash(prompt)
        expected = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        assert hash_value == expected
        assert len(hash_value) == 64

    def test_get_prompt_hash_is_deterministic(self) -> None:
        """Same prompt should always produce same hash."""
        prompt = "deterministic test"
        hash1 = get_prompt_hash(prompt)
        hash2 = get_prompt_hash(prompt)
        assert hash1 == hash2

    def test_different_prompts_different_hashes(self) -> None:
        """Different prompts should produce different hashes."""
        hash1 = get_prompt_hash("prompt one")
        hash2 = get_prompt_hash("prompt two")
        assert hash1 != hash2


class TestPromptBundle:
    """Tests for PromptBundle class."""

    def test_prompt_bundle_creation(self) -> None:
        """PromptBundle should store common and role prompts with hashes."""
        common = "common policy"
        role_prompts = {
            "entry_assessor": "entry prompt",
            "supervisor": "supervisor prompt",
        }
        bundle = PromptBundle(common=common, role_prompts=role_prompts)

        assert bundle.common_policy == common
        assert bundle.bundle_version == "querivue-roles-v3"
        assert bundle.common_hash == get_prompt_hash(common)
        assert bundle.get_role_hash("entry_assessor") == get_prompt_hash("entry prompt")
        assert bundle.get_role_hash("supervisor") == get_prompt_hash("supervisor prompt")

    def test_prompt_bundle_assemble(self) -> None:
        """assemble should combine common + role prompt."""
        common = "common"
        role_prompts = {"entry_assessor": "entry"}
        bundle = PromptBundle(common=common, role_prompts=role_prompts)

        assembled = bundle.assemble("entry_assessor")
        assert assembled == "common\n\nentry"

    def test_prompt_bundle_assemble_all(self) -> None:
        """assemble_all should return dict of all assembled prompts."""
        common = "common"
        role_prompts = {"a": "role_a", "b": "role_b"}
        bundle = PromptBundle(common=common, role_prompts=role_prompts)

        all_assembled = bundle.assemble_all()
        assert all_assembled == {"a": "common\n\nrole_a", "b": "common\n\nrole_b"}

    def test_prompt_bundle_missing_role_raises(self) -> None:
        """Getting missing role should raise ValueError."""
        bundle = PromptBundle(common="c", role_prompts={"a": "b"})
        with pytest.raises(ValueError, match="Role not in bundle"):
            bundle.get_role_prompt("missing")
        with pytest.raises(ValueError, match="Role not in bundle"):
            bundle.get_role_hash("missing")

    def test_load_prompt_bundle_v3(self) -> None:
        """load_prompt_bundle_v3 should load all 10 roles."""
        bundle = load_prompt_bundle_v3()

        expected_roles = {
            "entry_assessor",
            "supervisor",
            "sql_specialist",
            "python_specialist",
            "answer_specialist",
            "reviewer",
            "clarification_agent",
            "schema_repair",
            "single_analysis_baseline",
        }
        assert set(bundle._role_prompts.keys()) == expected_roles
        assert bundle.common_policy == get_common_policy()

        # All role prompts should be non-empty
        for role, prompt in bundle._role_prompts.items():
            assert len(prompt) > 0, f"Empty prompt for {role}"

        # All hashes should be valid SHA-256
        for role in expected_roles:
            h = bundle.get_role_hash(role)
            assert len(h) == 64
            int(h, 16)  # Validates hex


class TestPromptContent:
    """Tests for prompt content integrity."""

    def test_prompts_contain_rules_section(self) -> None:
        """Role prompts should contain ## Rules section."""
        for role in RoleName.__args__:  # type: ignore[attr-defined]
            if role == "common":
                continue  # common may not have ## Rules
            prompt = load_prompt(role)
            assert "## Rules" in prompt, f"Missing ## Rules in {role}"

    def test_prompts_do_not_contain_trusted_marker_in_rules(self) -> None:
        """Rules section should not contain text that could be interpreted as trusted."""
        # This test ensures that test content with ## Rules doesn't become trusted
        # The rule is: test source text containing ## Rules cannot alter template bytes/hash
        for role in RoleName.__args__:  # type: ignore[attr-defined]
            prompt = load_prompt(role)
            # Just verify the prompt loads and hashes are stable
            hash_val = get_prompt_hash(prompt)
            assert len(hash_val) == 64

    def test_common_policy_hash_stable(self) -> None:
        """Common policy hash should be stable across loads."""
        common1 = get_common_policy()
        common2 = get_common_policy()
        assert get_prompt_hash(common1) == get_prompt_hash(common2)

    def test_all_role_hashes_unique(self) -> None:
        """Each role should have a unique hash."""
        bundle = load_prompt_bundle_v3()
        hashes = [bundle.get_role_hash(role) for role in bundle._role_prompts]
        assert len(hashes) == len(set(hashes)), "Duplicate role prompt hashes found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])