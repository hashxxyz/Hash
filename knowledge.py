from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

def load_knowledge():
    parts = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        parts.append(f"### {path.name}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)
