"""
Funções utilitárias compartilhadas entre os módulos e o pipeline.
"""

from pathlib import Path

import pandas as pd

# ── Diretórios ────────────────────────────────────────────────────────────────
# As saídas do pipeline são segmentadas por público em outputs/comercial e
# outputs/operacional (ver Main.py). FIGURES/TABLES servem apenas aos notebooks de
# EDA (via save_fig).
ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
TABLES = OUTPUTS / "tables"

# Garante que os diretórios usados pelos notebooks existam
for _dir in (DATA_PROCESSED, FIGURES, TABLES):
    _dir.mkdir(parents=True, exist_ok=True)


# ── Leitura de dados ──────────────────────────────────────────────────────────
# Coluna de comissão: a base de produção traz duas colunas candidatas. Damos
# preferência à coluna 'COMISSÃO' e caímos para a total apenas se ela não existir.
COMISSAO_COLS = ["COMISSÃO", "COMISSÃO TOTAL (CORRET + CO-CORRET)"]


def get_comissao_col(df) -> str:
    """Retorna o nome da coluna de comissão presente no DataFrame (fonte única
    de verdade, antes duplicada em functions/quality/analise_temporal)."""
    for col in COMISSAO_COLS:
        if col in df.columns:
            return col
    return COMISSAO_COLS[-1]


def load_excel(path, **kwargs):
    """Lê um Excel usando a engine rápida `calamine` e, em caso de falha,
    cai para `openpyxl`. Centraliza o try/except antes repetido nos notebooks."""
    try:
        return pd.read_excel(path, engine="calamine", **kwargs)
    except Exception:
        return pd.read_excel(path, engine="openpyxl", **kwargs)


def save_fig(fig, filename: str, subdir: str = "figures", **kwargs):
    """Salva uma figura matplotlib/plotly em outputs/<subdir>/."""
    out = OUTPUTS / subdir / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    # Suporte a matplotlib e plotly
    if hasattr(fig, "savefig"):
        fig.savefig(out, bbox_inches="tight", **kwargs)
    elif hasattr(fig, "write_image"):
        fig.write_image(str(out), **kwargs)
    else:
        raise TypeError(f"Tipo de figura não suportado: {type(fig)}")
    print(f"✅ Figura salva em: {out.relative_to(ROOT)}")
    return out
