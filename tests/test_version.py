import json
import re
from pathlib import Path

import galaxus

ROOT = Path(__file__).resolve().parents[1]


def test_versions_match():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    skill = (ROOT / "skills" / "galaxus" / "SKILL.md").read_text("utf-8")
    m = re.search(r'^  version: "([^"]+)"$', skill, re.M)
    assert m, "SKILL.md frontmatter needs metadata.version"
    assert galaxus.__version__ == plugin["version"] == market["plugins"][0]["version"] == m.group(1)
