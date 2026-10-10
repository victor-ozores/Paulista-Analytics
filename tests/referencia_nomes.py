"""Nome curto de cada pessoa dos gols e cartões, recalculado direto das tabelas tratadas (sem usar scripts/nomes.py).

Regra que as telas seguem: a pessoa do gol ou do cartão é o atleta da camisa citada na relação de jogadores do jogo,
e o nome mostrado é o `nome_curto` dele em `dim_atleta` (o mesmo em todas as telas).
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"


def curto_das_pessoas(eventos=None):
    eventos = eventos if eventos is not None else ler_csv(PROC / "fato_evento.csv")
    atleta_da_camisa = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e["id_atleta"] for e in ler_csv(PROC / "fato_escalacao.csv")}
    curto = {a["id_atleta"]: a["nome_curto"] for a in ler_csv(PROC / "dim_atleta.csv")}
    saida = {}
    for e in eventos:
        if e["funcao"] == "Atleta" and e["fonte"] == "SUMULA":
            saida[e["pessoa"]] = curto[atleta_da_camisa[(e["id_partida"], e["id_clube"], e["numero_camisa"])]]
    return saida
