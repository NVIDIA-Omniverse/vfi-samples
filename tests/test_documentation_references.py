import re
from pathlib import Path


def test_value_clip_sequencer_guide_references_existing_script():
    """Verify that VALUE_CLIP_SEQUENCER_GUIDE.md only references existing .py files."""
    repo_root = Path(__file__).resolve().parent.parent
    guide_path = repo_root / "scripts" / "animation" / "VALUE_CLIP_SEQUENCER_GUIDE.md"
    script_dir = repo_root / "scripts" / "animation"

    assert guide_path.exists(), f"Guide not found: {guide_path}"

    guide_text = guide_path.read_text(encoding="utf-8")
    py_refs = re.findall(r"\`([a-zA-Z_][a-zA-Z0-9_]*\\.py)\`", guide_text)

    missing = [name for name in set(py_refs) if not (script_dir / name).exists()]
    assert not missing, (
        f"VALUE_CLIP_SEQUENCER_GUIDE.md references missing script(s): {missing}"
