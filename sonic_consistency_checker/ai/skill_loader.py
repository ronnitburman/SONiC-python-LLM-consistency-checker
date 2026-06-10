"""Skill loader — reads skill documents from .pi/skills/ on demand.

Skills are Markdown files that the agent can load at runtime to gain
domain knowledge.  New skills are auto-discovered — just drop a directory
under .pi/skills/ with a SKILL.md file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sonic_consistency_checker.ai.models import SkillInfo

# Resolve the project root from this file's location
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = _PROJECT_ROOT / ".pi" / "skills"


def list_skills() -> list[SkillInfo]:
    """Discover all available skill documents."""
    skills: list[SkillInfo] = []

    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            skills.append(
                SkillInfo(
                    name=skill_dir.name,
                    path=str(skill_file),
                    size=os.path.getsize(skill_file),
                )
            )

    return skills


def read_skill(name: str) -> str:
    """Load a skill's full Markdown content.

    Args:
        name: The skill directory name (e.g. "sonic").

    Returns:
        The full content of SKILL.md, or an error message if not found.
    """
    skill_file = SKILLS_DIR / name / "SKILL.md"

    if not skill_file.exists():
        available = [s.name for s in list_skills()]
        return (
            f"Skill '{name}' not found. "
            f"Available skills: {', '.join(available) if available else 'none'}."
        )

    content = skill_file.read_text(encoding="utf-8")

    # If the skill is large (>20KB), return a summary instead
    size_kb = len(content) // 1024
    if size_kb > 30:
        return _summarize_skill(name, content)

    return content


def _summarize_skill(name: str, content: str) -> str:
    """Extract key sections from a large skill file to save tokens."""
    lines = content.split("\n")
    sections: dict[str, list[str]] = {}
    current_section = "header"

    for line in lines:
        if line.startswith("## "):
            current_section = line.strip("# ").strip()
            sections[current_section] = []
        elif current_section in sections:
            sections[current_section].append(line)
        elif current_section not in sections:
            sections[current_section] = [line]

    # Keep the most relevant sections for diagnostic use
    keep = [
        "Redis Database Layout",
        "Core Containers",
        "Service Categories and Control Flows",
        "Key CLI Commands",
        "Architecture",
    ]

    summary_parts: list[str] = [
        f"# {name} skill (summarized — full content available on demand)\n"
    ]
    for section_name in keep:
        if section_name in sections:
            summary_parts.append(f"\n## {section_name}\n")
            summary_parts.append("\n".join(sections[section_name]))

    return "\n".join(summary_parts)
