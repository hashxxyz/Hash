from pathlib import Path
KNOWLEDGE_DIR=Path(__file__).parent/"knowledge"
KNOWN_FILES=[KNOWLEDGE_DIR/"HAMID_FORMAT.md",KNOWLEDGE_DIR/"PROJECT_RULES.md"]
def load_knowledge():
    return {p.name:p.read_text(encoding="utf-8") for p in KNOWN_FILES if p.exists()}
