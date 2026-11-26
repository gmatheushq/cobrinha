"""Exporta uma Random Forest para o formato JSON usado pelo navegador."""

import json
import os

import joblib

from features import COLUNAS_MODELO

BASE = os.path.dirname(os.path.abspath(__file__))
ESCALA = 10000


def exportar_arvore(estimador):
    t = estimador.tree_
    n = t.node_count

    for i in range(n):
        esq = t.children_left[i]
        if esq != -1 and esq != i + 1:
            raise ValueError("Ordem de nos inesperada na arvore.")

    f, th, r, folhas = [], [], [], []

    for i in range(n):
        if t.children_left[i] == -1:
            valores = t.value[i, 0, :].astype(float)
            soma = valores.sum() or 1.0

            f.append(-1)
            th.append(len(folhas) // len(valores))
            r.append(-1)
            folhas.extend(
                int(round(v / soma * ESCALA))
                for v in valores
            )
        else:
            f.append(int(t.feature[i]))
            th.append(round(float(t.threshold[i]), 4))
            r.append(int(t.children_right[i]))

    return {"f": f, "t": th, "r": r, "p": folhas}


def exportar(caminho_modelo, caminho_saida, meta=None):
    modelo = joblib.load(caminho_modelo)

    if list(modelo.feature_names_in_) != COLUNAS_MODELO:
        raise ValueError("Colunas do modelo incompatíveis.")

    classes = [str(c) for c in modelo.classes_]

    if classes != ["Direita", "Esquerda", "Frente"]:
        raise ValueError(f"Classes inesperadas: {classes}")

    dados = {
        "classes": classes,
        "colunas": COLUNAS_MODELO,
        "escala": ESCALA,
        **(meta or {}),
        "arvores": [
            exportar_arvore(e)
            for e in modelo.estimators_
        ],
    }

    pasta = os.path.dirname(os.path.abspath(caminho_saida))
    os.makedirs(pasta, exist_ok=True)

    temporario = caminho_saida + ".tmp"

    with open(temporario, "w", encoding="utf-8") as arq:
        json.dump(dados, arq, separators=(",", ":"))

    # Confere se o arquivo gerado pode ser lido antes de disponibilizá-lo.
    with open(temporario, encoding="utf-8") as arq:
        conferido = json.load(arq)

    if len(conferido["arvores"]) != len(modelo.estimators_):
        raise ValueError("Quantidade de árvores exportadas incorreta.")

    os.replace(temporario, caminho_saida)

    print(
        f"Modelo exportado: {caminho_saida} "
        f"({os.path.getsize(caminho_saida) / 1e6:.2f} MB)"
    )


def main(meta=None, caminho_modelo=None, caminho_saida=None):
    caminho_modelo = caminho_modelo or os.path.join(
        BASE, "modelo_cobrinha.pkl"
    )
    caminho_saida = caminho_saida or os.path.join(
        BASE, "docs", "modelo.json"
    )
    exportar(caminho_modelo, caminho_saida, meta)


if __name__ == "__main__":
    main()
