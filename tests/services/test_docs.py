"""La documentacion compila y no tiene enlaces rotos (E2-M9b).

- Cada bloque Mermaid del repositorio compila con mermaid-cli
  (`tools/mermaid/check-mermaid.mjs`). Se omite si Node o las dependencias de
  `tools/mermaid/` no estan instaladas (`cd tools/mermaid && npm install`).
- Ningun enlace interno de la Wiki (`docs/wiki/`) esta roto, incluidas las citas
  de archivo y linea del codigo (`tools/check_wiki_links.py`).
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MERMAID = ROOT / "tools" / "mermaid"
NODE = shutil.which("node")


def run(command, cwd):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=600)


def test_la_wiki_no_tiene_enlaces_rotos():
    result = run([sys.executable, str(ROOT / "tools" / "check_wiki_links.py")], ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    NODE is None or not (MERMAID / "node_modules" / "@mermaid-js" / "mermaid-cli").is_dir(),
    reason="Requiere Node y `npm install` en tools/mermaid/",
)
def test_cada_bloque_mermaid_compila():
    result = run([NODE, "check-mermaid.mjs"], MERMAID)
    assert result.returncode == 0, result.stdout + result.stderr
