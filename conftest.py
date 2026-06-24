"""
conftest.py — garante que o pacote `src` seja importável nos testes (pytest),
inserindo a raiz do projeto no sys.path (mesmo padrão do Main.py).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
