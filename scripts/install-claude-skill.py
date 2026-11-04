#!/usr/bin/env python3
"""Install the factory skill and launcher without changing Claude authentication or permissions."""

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / ".claude/skills/build-mi"
target = Path.home() / ".claude/skills/build-mi"
if target.exists() or target.is_symlink():
    backup = (
        Path.home()
        / ".claude/skill-backups"
        / ("build-mi-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(target, backup)
    if target.is_symlink():
        target.unlink()
    else:
        shutil.rmtree(target)
shutil.copytree(source, target)
(target / "references").mkdir(exist_ok=True)
(target / "references/factory-root.txt").write_text(str(ROOT) + "\n")
launcher = Path.home() / ".local/bin/mi-factory"
if launcher.exists():
    backup = launcher.with_name("mi-factory.backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(launcher, backup)
launcher.parent.mkdir(parents=True, exist_ok=True)
import shlex

launcher.write_text("#!/usr/bin/env bash\nexec " + shlex.quote(str(ROOT / "mi")) + ' "$@"\n')
launcher.chmod(0o755)
print("Installed /build-mi for Claude Code and the mi-factory command.")
print("Existing AI Core routing and permission settings were preserved.")
