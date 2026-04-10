from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool, tool


logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
USER_SKILLS_DIR = Path.home() / ".agents" / "skills"
LOCAL_SKILLS_DIR = ROOT_DIR / ".agents" / "skills"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
MAX_SKILL_FILE_SIZE = 10 * 1024 * 1024
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
MAX_SKILL_COMPATIBILITY_LENGTH = 500


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    skill_md_path: Path
    source_dir: Path
    source_label: str
    allowed_tools: tuple[str, ...] = ()
    compatibility: str | None = None
    license_name: str | None = None
    metadata: Mapping[str, str] | None = None
    resource_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillRuntime:
    registry: Mapping[str, SkillDefinition]
    skills_prompt: str
    skill_tools: tuple[BaseTool, ...]


def configured_skill_sources() -> list[Path]:
    return [USER_SKILLS_DIR, LOCAL_SKILLS_DIR]


def existing_skill_sources() -> list[Path]:
    return [path for path in configured_skill_sources() if path.is_dir()]


def deepagents_skill_sources() -> list[str]:
    return [
        f"{path.resolve().as_posix().rstrip('/')}/" for path in existing_skill_sources()
    ]


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    raw_frontmatter = match.group(1)
    metadata = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    body = content[match.end() :]
    return metadata, body


def _validate_skill_name(name: str, directory_name: str) -> tuple[bool, str]:
    if not name:
        return False, "name is required"
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return False, "name exceeds 64 characters"
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, "name must be lowercase alphanumeric with single hyphens only"
    for char in name:
        if char == "-":
            continue
        if (char.isalpha() and char.islower()) or char.isdigit():
            continue
        return False, "name must be lowercase alphanumeric with single hyphens only"
    if name != directory_name:
        return False, f"name '{name}' must match directory name '{directory_name}'"
    return True, ""


def _normalize_metadata(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _coerce_allowed_tools(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return tuple(token.strip(",") for token in raw.split() if token.strip(","))
    if isinstance(raw, list):
        return tuple(str(token).strip() for token in raw if str(token).strip())
    return ()


def _list_skill_resources(skill_dir: Path) -> tuple[str, ...]:
    resource_paths: list[str] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "SKILL.md":
            continue
        resource_paths.append(path.relative_to(skill_dir).as_posix())
    return tuple(resource_paths)


def _read_text_file(path: Path) -> str:
    if path.stat().st_size > MAX_SKILL_FILE_SIZE:
        raise ValueError(f"File exceeds {MAX_SKILL_FILE_SIZE} bytes: {path}")
    return path.read_text(encoding="utf-8")


def _load_skill_definition(
    skill_dir: Path, source_dir: Path, source_label: str
) -> SkillDefinition | None:
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.is_file():
        return None

    try:
        content = _read_text_file(skill_md_path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("Skipping skill at %s: %s", skill_md_path, exc)
        return None

    metadata, body = _parse_frontmatter(content)
    if not metadata:
        logger.warning(
            "Skill %s is missing YAML frontmatter; loading with fallback metadata.",
            skill_md_path,
        )

    name = str(metadata.get("name") or skill_dir.name).strip()
    is_valid, error = _validate_skill_name(name, skill_dir.name)
    if not is_valid:
        logger.warning(
            "Skill '%s' in %s does not follow Agent Skills naming rules: %s",
            name,
            skill_md_path,
            error,
        )

    description = str(metadata.get("description") or "").strip()
    if not description:
        body_lines = [line.strip() for line in body.splitlines() if line.strip()]
        description = body_lines[0] if body_lines else "No description provided."
        logger.warning(
            "Skill %s is missing a description; using a fallback description.",
            skill_md_path,
        )
    if len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        logger.warning(
            "Description for %s exceeds %d characters; truncating.",
            skill_md_path,
            MAX_SKILL_DESCRIPTION_LENGTH,
        )
        description = description[:MAX_SKILL_DESCRIPTION_LENGTH]

    compatibility = str(metadata.get("compatibility") or "").strip() or None
    if compatibility and len(compatibility) > MAX_SKILL_COMPATIBILITY_LENGTH:
        logger.warning(
            "Compatibility for %s exceeds %d characters; truncating.",
            skill_md_path,
            MAX_SKILL_COMPATIBILITY_LENGTH,
        )
        compatibility = compatibility[:MAX_SKILL_COMPATIBILITY_LENGTH]

    return SkillDefinition(
        name=name,
        description=description,
        skill_md_path=skill_md_path.resolve(),
        source_dir=source_dir.resolve(),
        source_label=source_label,
        allowed_tools=_coerce_allowed_tools(
            metadata.get("allowed-tools", metadata.get("allowed_tools"))
        ),
        compatibility=compatibility,
        license_name=str(metadata.get("license") or "").strip() or None,
        metadata=_normalize_metadata(metadata.get("metadata", {})),
        resource_paths=_list_skill_resources(skill_dir),
    )


def load_skill_registry() -> dict[str, SkillDefinition]:
    registry: dict[str, SkillDefinition] = {}
    source_labels = {
        USER_SKILLS_DIR.resolve(): "user",
        LOCAL_SKILLS_DIR.resolve(): "project",
    }

    for source_dir in existing_skill_sources():
        resolved_source = source_dir.resolve()
        source_label = source_labels.get(resolved_source, resolved_source.name)
        for child in sorted(source_dir.iterdir()):
            if not child.is_dir():
                continue
            skill = _load_skill_definition(child, resolved_source, source_label)
            if skill is not None:
                registry[skill.name] = skill

    return registry


def _format_skill_annotations(skill: SkillDefinition) -> str:
    annotations: list[str] = [f"source={skill.source_label}"]
    if skill.compatibility:
        annotations.append(f"compatibility={skill.compatibility}")
    if skill.license_name:
        annotations.append(f"license={skill.license_name}")
    return ", ".join(annotations)


def build_skills_prompt_addendum(skills_by_name: Mapping[str, SkillDefinition]) -> str:
    source_lines: list[str] = []
    configured = configured_skill_sources()
    for index, source_dir in enumerate(configured):
        suffix = " (higher priority)" if index == len(configured) - 1 else ""
        source_lines.append(f"- `{source_dir.resolve()}`{suffix}")

    if skills_by_name:
        skill_lines: list[str] = []
        for skill in sorted(skills_by_name.values(), key=lambda item: item.name):
            skill_lines.append(
                f"- **{skill.name}**: {skill.description} ({_format_skill_annotations(skill)})"
            )
            skill_lines.append(
                f"  -> Read `{skill.skill_md_path}` by calling `load_skill`"
            )
            if skill.allowed_tools:
                skill_lines.append(
                    f"  -> Preferred tools while following this skill: {', '.join(skill.allowed_tools)}"
                )
            if skill.resource_paths:
                skill_lines.append(
                    f"  -> Supporting files available on demand: {', '.join(skill.resource_paths[:8])}"
                    + (" ..." if len(skill.resource_paths) > 8 else "")
                )
    else:
        skill_lines = [
            "- No skills discovered yet.",
            "- Add skills under `~/.agents/skills/<name>/SKILL.md` or "
            f"`{LOCAL_SKILLS_DIR.resolve()}/<name>/SKILL.md`.",
        ]

    return "\n".join(
        [
            "## Skills System",
            "You have access to a skills library that provides specialized capabilities and domain knowledge.",
            "",
            "Skill locations:",
            *source_lines,
            "",
            "**Available Skills:**",
            *skill_lines,
            "",
            "**How to Use Skills (Progressive Disclosure):**",
            "1. Recognize when a skill applies by matching the user's request to a skill description.",
            "2. Read the skill's full instructions by calling `load_skill` with the exact skill name.",
            "3. Follow the workflow in `SKILL.md` before improvising your own process.",
            "4. Load supporting files with `load_skill_resource` only when `SKILL.md` points you to them or you need a specific variant, example, or script.",
            "5. If a skill lists preferred tools, stay close to those tools while following that skill.",
            "",
            "**Important:** metadata is always visible, `SKILL.md` is loaded on demand, and supporting files should remain unloaded unless they are actually needed.",
        ]
    )


def append_prompt_text(base_prompt: str, addendum: str | None) -> str:
    addendum = (addendum or "").strip()
    if not addendum:
        return base_prompt
    return f"{base_prompt.rstrip()}\n\n{addendum}"


def _resolve_skill_resource_path(skill: SkillDefinition, relative_path: str) -> Path:
    if not relative_path.strip():
        raise ValueError("relative_path is required")
    candidate = (skill.skill_md_path.parent / relative_path).resolve()
    candidate.relative_to(skill.skill_md_path.parent.resolve())
    if not candidate.is_file():
        raise ValueError(f"Skill resource not found: {relative_path}")
    return candidate


def create_skill_tools(
    skills_by_name: Mapping[str, SkillDefinition],
) -> tuple[BaseTool, BaseTool]:
    registry = dict(skills_by_name)

    @tool
    def load_skill(skill_name: str) -> str:
        """Load the full SKILL.md instructions for a named agent skill."""
        skill = registry.get(skill_name.strip())
        if skill is None:
            available = ", ".join(sorted(registry)) or "(none)"
            return f"Skill '{skill_name}' was not found. Available skills: {available}."

        resources = (
            "\n".join(f"- {path}" for path in skill.resource_paths) or "- (none)"
        )
        preferred_tools = ", ".join(skill.allowed_tools) or "(not specified)"

        return "\n".join(
            [
                "# Skill Package",
                f"Name: {skill.name}",
                f"Description: {skill.description}",
                f"Source: {skill.source_label}",
                f"Directory: {skill.skill_md_path.parent}",
                f"SKILL.md: {skill.skill_md_path}",
                f"Preferred tools: {preferred_tools}",
                "",
                "Supporting files available on demand:",
                resources,
                "",
                "Progressive disclosure guidance:",
                "- Use the SKILL.md workflow as the primary source of truth.",
                "- Do not load every supporting file by default.",
                "- Call `load_skill_resource` only for files explicitly referenced by SKILL.md or needed for the current variant.",
                "",
                "SKILL.md content:",
                _read_text_file(skill.skill_md_path),
            ]
        )

    @tool
    def load_skill_resource(skill_name: str, relative_path: str) -> str:
        """Load a supporting file from inside a named skill package."""
        skill = registry.get(skill_name.strip())
        if skill is None:
            available = ", ".join(sorted(registry)) or "(none)"
            return f"Skill '{skill_name}' was not found. Available skills: {available}."

        try:
            resource_path = _resolve_skill_resource_path(skill, relative_path)
            content = _read_text_file(resource_path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            return f"Unable to load resource '{relative_path}' from skill '{skill.name}': {exc}"

        return "\n".join(
            [
                "# Skill Resource",
                f"Skill: {skill.name}",
                f"Relative path: {relative_path}",
                f"Absolute path: {resource_path}",
                "",
                content,
            ]
        )

    return load_skill, load_skill_resource


class SkillsPromptMiddleware(AgentMiddleware):
    """Inject Agent Skills metadata into the system prompt before model calls."""

    def __init__(self, skills_prompt: str) -> None:
        self.skills_prompt = skills_prompt.strip()

    def _append_prompt(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        if not self.skills_prompt:
            return request

        system_message = request.system_message
        if system_message is None:
            new_system_message = SystemMessage(content=self.skills_prompt)
        elif isinstance(system_message.content, str):
            new_system_message = SystemMessage(
                content=append_prompt_text(system_message.content, self.skills_prompt)
            )
        else:
            content_blocks = list(system_message.content)
            content_blocks.append({"type": "text", "text": self.skills_prompt})
            new_system_message = SystemMessage(content=content_blocks)

        return request.override(system_message=new_system_message)

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler,
    ) -> ModelResponse[ResponseT]:
        return handler(self._append_prompt(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler,
    ) -> ModelResponse[ResponseT]:
        return await handler(self._append_prompt(request))


def build_skill_runtime() -> SkillRuntime:
    registry = load_skill_registry()
    if not registry:
        return SkillRuntime(registry=registry, skills_prompt="", skill_tools=())

    return SkillRuntime(
        registry=registry,
        skills_prompt=build_skills_prompt_addendum(registry),
        skill_tools=create_skill_tools(registry),
    )
