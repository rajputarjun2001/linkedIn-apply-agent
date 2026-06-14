"""AI prompt templates."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template by filename."""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {name}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **kwargs: str) -> str:
    """Render a prompt template without interpreting JSON braces."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", value)
    return result
