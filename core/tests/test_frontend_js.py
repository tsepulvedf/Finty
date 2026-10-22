"""Tests de los modulos de presentacion de JavaScript (E2-M8b).

Corren con el runner que trae Node (`node --test`), sin dependencias: si Node no
esta instalado en la maquina, se omiten. Hoy cubren `format.js`.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent
TESTS_JS = RAIZ / "frontend" / "tests" / "js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node no esta instalado")
def test_los_tests_de_javascript_pasan():
    archivos = sorted(str(p) for p in TESTS_JS.glob("*.test.mjs"))
    assert archivos
    resultado = subprocess.run(
        [NODE, "--test", *archivos], capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
