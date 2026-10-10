"""Agent skills: instructions the agent loads only when a task needs them.

A skill is a folder with a SKILL.md file. The file starts with YAML
frontmatter that has a name and a description, followed by the
instructions themselves:

    ---
    name: borough-comparison
    description: Compare NYC 311 metrics across boroughs fairly.
    ---
    # Borough comparison
    ...

The system prompt lists only each skill's name and description. When a
task matches one, the agent calls load_skill to read the full
instructions. Ten skills cost the context about as much as ten lines,
not ten documents.

This follows the Agent Skills open standard (agentskills.io), so the same
folders work in other agents that support it.
"""

from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent / "skills"


def parse_skill(path: Path) -> tuple[dict, str]:
    """Split a SKILL.md file into its frontmatter and its body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path} has no frontmatter")
    _, frontmatter, body = text.split("---", 2)
    meta = yaml.safe_load(frontmatter)
    if not meta.get("name") or not meta.get("description"):
        raise ValueError(f"{path} needs both name and description in its frontmatter")
    return meta, body.strip()


def discover_skills(skills_dir: Path = SKILLS_DIR) -> dict[str, dict]:
    """Find every skill folder and read its name and description."""
    skills = {}
    for skill_file in sorted(Path(skills_dir).glob("*/SKILL.md")):
        meta, _ = parse_skill(skill_file)
        skills[meta["name"]] = {"description": meta["description"], "path": skill_file}
    return skills


def skill_index(skills_dir: Path = SKILLS_DIR) -> str:
    """The short list of skills that goes into the system prompt."""
    skills = discover_skills(skills_dir)
    if not skills:
        return ""
    lines = [f"- {name}: {info['description']}" for name, info in skills.items()]
    return (
        "\nSkills:\n"
        "These skills hold instructions for specific kinds of tasks. Load a skill only when the task "
        "clearly matches its description; many tasks need none. To use one, call load_skill with its "
        "name before you start, then follow it.\n" + "\n".join(lines) + "\n"
    )


def load_skill(name: str) -> dict:
    """Return a skill's full instructions. This is the load_skill tool."""
    skills = discover_skills()
    if name not in skills:
        return {"error": f"No skill named {name}. Available: {', '.join(skills) or 'none'}"}
    _, body = parse_skill(skills[name]["path"])
    return {"name": name, "instructions": body}
