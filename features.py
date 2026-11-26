"""Características e conversão de ações: equivalentes a docs/nucleo.js."""

import numpy as np

COLUNAS_ABSOLUTAS = [
    "dx",
    "dy",
    "dir_cima",
    "dir_baixo",
    "dir_esquerda",
    "dir_direita",
    "perigo_cima",
    "perigo_baixo",
    "perigo_esquerda",
    "perigo_direita",
    "TamanhoCobrinha",
]

COLUNAS_MODELO = [
    "fruta_frente",
    "fruta_esq",
    "rel_perigo_frente",
    "rel_perigo_esq",
    "rel_perigo_dir",
    "TamanhoCobrinha",
]

VETORES = {
    "Cima": (0, -1),
    "Baixo": (0, 1),
    "Esquerda": (-1, 0),
    "Direita": (1, 0),
}

COL_PERIGO = {
    "Cima": "perigo_cima",
    "Baixo": "perigo_baixo",
    "Esquerda": "perigo_esquerda",
    "Direita": "perigo_direita",
}

ACOES_RELATIVAS = ("Direita", "Esquerda", "Frente")


def direcao_da_linha(linha):
    """Recupera a direção atual a partir das quatro flags do motor."""
    flags = {
        "Cima": linha["dir_cima"],
        "Baixo": linha["dir_baixo"],
        "Esquerda": linha["dir_esquerda"],
        "Direita": linha["dir_direita"],
    }

    ativos = [nome for nome, valor in flags.items() if int(valor) == 1]

    if len(ativos) != 1:
        raise ValueError("Direção atual inválida.")

    return ativos[0]


def para_relativo(linha, direcao):
    """Mesma transformação de paraRelativo() em docs/nucleo.js."""
    hx, hy = VETORES[direcao]

    # JS: esq([x,y]) = [y,-x]
    esquerda = (hy, -hx)

    # JS: dir([x,y]) = [-y,x]
    direita = (-hy, hx)

    perigo = {
        nome: float(linha[COL_PERIGO[nome]])
        for nome in VETORES
    }

    return [
        float(linha["dx"]) * hx + float(linha["dy"]) * hy,
        float(linha["dx"]) * esquerda[0] + float(linha["dy"]) * esquerda[1],
        perigo[direcao],
        perigo[next(n for n, v in VETORES.items() if v == esquerda)],
        perigo[next(n for n, v in VETORES.items() if v == direita)],
        float(linha["TamanhoCobrinha"]),
    ]


def acao_relativa(decisao, direcao):
    """Converte uma decisão absoluta em Frente, Esquerda ou Direita."""
    if decisao not in VETORES:
        raise ValueError(f"Decisão desconhecida: {decisao}")

    hx, hy = VETORES[direcao]
    ax, ay = VETORES[decisao]

    frente = (hx, hy)
    esquerda = (hy, -hx)
    direita = (-hy, hx)
    acao = (ax, ay)

    if acao == frente:
        return "Frente"
    if acao == esquerda:
        return "Esquerda"
    if acao == direita:
        return "Direita"

    raise ValueError("A decisão representa uma meia-volta.")
