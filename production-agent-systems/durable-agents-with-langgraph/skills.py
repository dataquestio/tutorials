"""Skills: instructions the agent loads only when a task needs them.

Each skill is a folder under skills/ with a SKILL.md file. The YAML
frontmatter at the top of SKILL.md holds the skill's name and description.
The system prompt lists only those two fields; the full body is loaded on
demand with the load_skill tool, so unused skills cost almost no context.
"""

from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent / "skills"


def parse_skill(path):
    """Split SKILL.md into its frontmatter dict and its markdown body."""
    text = path.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body.strip()


def discover_skills():
    """Find every skill and return {name: {"description": ..., "path": ...}}."""
    found = {}
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta, _ = parse_skill(path)
        found[meta["name"]] = {"description": meta["description"], "path": path}
    return found


def skill_index():
    """The short list of skills that goes into the system prompt."""
    lines = [f"- {name}: {info['description']}" for name, info in discover_skills().items()]
    return "\n".join(lines) if lines else "(no skills installed)"


def load_skill(name):
    """Return the full instructions of one skill."""
    skills = discover_skills()
    if name not in skills:
        return {"error": f"Unknown skill: {name}. Available: {', '.join(skills)}"}
    _, body = parse_skill(skills[name]["path"])
    return {"name": name, "instructions": body}
