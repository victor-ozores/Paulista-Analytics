"""Nomes curtos de atletas e da comissão técnica, num lugar só.

O nome curto aparece nas listas e nas dicas das telas (a dica sempre traz o nome completo). Regras:
  1. vale o apelido que a súmula traz nos gols; apelido todo em maiúsculas (EVERTON) vira só com a inicial maiúscula (Everton);
  2. sem apelido, o primeiro nome mais o último sobrenome (Filho, Júnior e Neto contam como sobrenome nos atletas);
  3. nome que a súmula cortou em 33 letras e que nenhum gol ou cartão completou perde a palavra cortada;
  4. dois atletas do mesmo clube com o mesmo nome curto passam a usar nome e sobrenome e, se ainda empatarem, a inicial do nome do meio.
A comissão técnica pula os sufixos (só aparece na tela de Jogos).
"""
import unicodedata
from collections import Counter, defaultdict

PARTICULAS = {"da", "de", "do", "das", "dos", "e", "di", "du", "del", "la", "van", "von"}
SUFIXOS = {"junior", "júnior", "filho", "neto", "sobrinho"}
TAMANHO_NOME_SUMULA = 33


def simples(texto):
    """Minúsculas e sem acento, só para comparar nomes."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def completar_nome(nome_da_sumula, candidatos):
    """Nome cortado em 33 letras pela relação de jogadores -> o nome inteiro que um gol ou cartão do mesmo atleta traz, ou None.
    `candidatos`: Counter com os nomes (como vêm nos eventos). Vale o mais frequente; empate, o primeiro em ordem alfabética."""
    if len(nome_da_sumula) < TAMANHO_NOME_SUMULA:
        return None
    base = simples(nome_da_sumula)
    inteiros = sorted((-n, p) for p, n in candidatos.items() if len(p) > len(nome_da_sumula) and simples(p).startswith(base))
    return inteiros[0][1] if inteiros else None


def eh_sufixo(palavra):
    return palavra.lower().rstrip(".") in SUFIXOS


def caixa_do_apelido(apelido):
    """EVERTON -> Everton. Apelido que já tem minúsculas fica como está."""
    a = apelido.strip()
    if len(a) > 3 and a == a.upper() and a != a.lower():
        return a.title()
    return a


def sobrenome_final(partes):
    """Último sobrenome que não é partícula (se só sobrar isso, o último mesmo)."""
    sobrenomes = [p for p in partes[1:] if p.lower() not in PARTICULAS]
    return (sobrenomes or partes[1:])[-1]


def nome_curto(nome, apelido=None, truncado=False):
    if apelido:
        return caixa_do_apelido(apelido)
    partes = nome.split()
    if truncado and len(partes) > 2:
        partes = partes[:-1]
    if len(partes) == 1:
        return partes[0]
    return f"{partes[0]} {sobrenome_final(partes)}"


def nome_de_comissao(nome):
    partes = nome.split()
    while len(partes) > 2 and eh_sufixo(partes[-1]):
        partes = partes[:-1]
    return partes[0] if len(partes) == 1 else partes[0] + " " + partes[-1]


def niveis_de_desempate(a):
    """Nomes cada vez mais completos de um atleta, do mais curto ao nome inteiro."""
    nome, cortado = a.get("_nome", a["nome"]), a.get("_truncado", a["nome_truncado"])
    partes = nome.split()
    if cortado and len(partes) > 2:
        partes = partes[:-1]
    if len(partes) < 2:
        return [nome]
    primeiro, ultimo = partes[0], sobrenome_final(partes)
    meio = [p for p in partes[1:-1] if p.lower() not in PARTICULAS]
    niveis = [f"{primeiro} {ultimo}"]
    if meio:
        niveis += [f"{primeiro} {meio[0][0]}. {ultimo}", f"{primeiro} {meio[0]} {ultimo}"]
    niveis.append(nome)
    return niveis


def desambiguar(atletas):
    """Dentro de cada clube, nenhum nome curto se repete. `atletas`: dicts com id_atleta, id_clube, nome, nome_truncado e nome_curto
    (o nome_curto é ajustado no lugar; `_nome` e `_truncado`, se houver, trazem o nome já completado pelos gols e cartões).
    Só quem repete muda; quem repete passa a nome e sobrenome e, se precisar, ganha a inicial do meio."""
    por_clube = defaultdict(list)
    for a in atletas:
        por_clube[a["id_clube"]].append(a)
    for membros in por_clube.values():
        nivel = {a["id_atleta"]: -1 for a in membros}
        for _ in range(5):
            cont = Counter(a["nome_curto"] for a in membros)
            repetidos = [a for a in membros if cont[a["nome_curto"]] > 1]
            if not repetidos:
                break
            for a in repetidos:
                nivel[a["id_atleta"]] += 1
                niveis = niveis_de_desempate(a)
                a["nome_curto"] = niveis[min(nivel[a["id_atleta"]], len(niveis) - 1)]
    return atletas


def curto_por_pessoa(eventos, escalacao, atletas):
    """Nome (completo, como vem nos gols e cartões) -> nome curto do atleta, o mesmo em todas as telas.
    `eventos`, `escalacao` e `atletas` são as tabelas fato_evento, fato_escalacao e dim_atleta (listas de dicts de texto)."""
    atleta_da_camisa = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e["id_atleta"] for e in escalacao}
    curto = {a["id_atleta"]: a["nome_curto"] for a in atletas}
    saida = {}
    for e in eventos:
        if e["funcao"] == "Atleta" and e["fonte"] == "SUMULA":
            ida = atleta_da_camisa.get((e["id_partida"], e["id_clube"], e["numero_camisa"]))
            if ida is None:
                raise SystemExit(f"o evento {e['id_evento']} cita uma camisa que não está na relação de jogadores")
            if saida.setdefault(e["pessoa"], curto[ida]) != curto[ida]:
                raise SystemExit(f"o nome '{e['pessoa']}' aparece com dois atletas diferentes")
    return saida
