"""Treinamento seguro da IA principal com partidas humanas do D1."""

import glob
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit

from features import (
    COLUNAS_ABSOLUTAS,
    COLUNAS_MODELO,
    ACOES_RELATIVAS,
    direcao_da_linha,
    para_relativo,
    acao_relativa,
)

BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_DADOS = os.path.join(BASE, "dadosTreino")
ARQUIVO_MODELO_ATUAL = os.path.join(BASE, "docs", "modelo.json")
ARQUIVO_CANDIDATO = os.path.join(BASE, "modelo_cobrinha_candidato.pkl")
ARQUIVO_METRICAS = os.path.join(BASE, "relatorio_treino.json")

MIN_PARTIDAS = 10
MIN_JOGADAS = 500
MIN_F1 = 0.25
TOLERANCIA_F1 = 0.02
TOLERANCIA_ACURACIA = 0.03


def carregar_partidas():
    arquivos = sorted(glob.glob(os.path.join(PASTA_DADOS, "dados_web_*.csv")))

    if not arquivos:
        raise RuntimeError(
            "Nenhuma partida humana encontrada em dadosTreino/dados_web_*.csv."
        )

    registros = []
    partidas_validas = 0

    for arquivo in arquivos:
        try:
            df = pd.read_csv(arquivo)
        except Exception as erro:
            print(f"[AVISO] CSV ignorado: {os.path.basename(arquivo)}: {erro}")
            continue

        obrigatorias = set(COLUNAS_ABSOLUTAS + ["decisao"])
        if not obrigatorias.issubset(df.columns):
            print(f"[AVISO] Colunas ausentes: {os.path.basename(arquivo)}")
            continue

        linhas_partida = []

        for _, linha in df.iterrows():
            try:
                direcao = direcao_da_linha(linha)
                x = para_relativo(linha, direcao)
                y = acao_relativa(str(linha["decisao"]), direcao)

                if not np.all(np.isfinite(x)):
                    continue

                linhas_partida.append({
                    "features": x,
                    "decisao": y,
                    "partida": os.path.basename(arquivo),
                })
            except (ValueError, TypeError, KeyError):
                continue

        if linhas_partida:
            registros.extend(linhas_partida)
            partidas_validas += 1

    if not registros:
        raise RuntimeError("Nenhuma jogada válida foi encontrada nos CSVs.")

    X = pd.DataFrame(
        [r["features"] for r in registros],
        columns=COLUNAS_MODELO,
    )
    y = pd.Series([r["decisao"] for r in registros], name="decisao")
    grupos = pd.Series([r["partida"] for r in registros], name="partida")

    return X, y, grupos, partidas_validas


def prever_json(modelo, X):
    """Executa a inferência do modelo JSON atual, igual ao motor JS."""
    classes = modelo["classes"]
    k = len(classes)
    previsoes = []

    for _, linha in X.iterrows():
        x = linha.to_numpy(dtype=float)
        soma = np.zeros(k, dtype=float)

        for arvore in modelo["arvores"]:
            no = 0

            while arvore["f"][no] >= 0:
                if x[arvore["f"][no]] <= arvore["t"][no]:
                    no += 1
                else:
                    no = arvore["r"][no]

            base = int(arvore["t"][no]) * k
            soma += np.asarray(arvore["p"][base:base + k], dtype=float)

        previsoes.append(classes[int(np.argmax(soma))])

    return previsoes


def salvar_metricas(dados):
    with open(ARQUIVO_METRICAS, "w", encoding="utf-8") as arq:
        json.dump(dados, arq, indent=2, ensure_ascii=False)


def main():
    X, y, grupos, partidas = carregar_partidas()

    quantidade = len(X)
    classes_presentes = set(y.unique())

    print(f"Partidas válidas: {partidas}")
    print(f"Jogadas válidas: {quantidade}")
    print(f"Classes: {sorted(classes_presentes)}")

    if partidas < MIN_PARTIDAS:
        raise RuntimeError(
            f"Treinamento bloqueado: são necessárias {MIN_PARTIDAS} partidas; "
            f"foram encontradas {partidas}."
        )

    if quantidade < MIN_JOGADAS:
        raise RuntimeError(
            f"Treinamento bloqueado: são necessárias {MIN_JOGADAS} jogadas; "
            f"foram encontradas {quantidade}."
        )

    if classes_presentes != set(ACOES_RELATIVAS):
        raise RuntimeError(
            "Treinamento bloqueado: o conjunto precisa conter as três ações "
            f"{list(ACOES_RELATIVAS)}."
        )

    # Busca uma divisão por partida que preserve as três classes nos dois lados.
    divisao = None
    separador = GroupShuffleSplit(
        n_splits=500,
        test_size=0.20,
        random_state=42,
    )

    for treino, teste in separador.split(X, y, grupos):
        if len(set(grupos.iloc[teste])) < 2:
            continue
        if set(y.iloc[treino].unique()) != set(ACOES_RELATIVAS):
            continue
        if set(y.iloc[teste].unique()) != set(ACOES_RELATIVAS):
            continue
        divisao = (treino, teste)
        break

    if divisao is None:
        raise RuntimeError(
            "Não foi possível separar partidas mantendo as três ações "
            "nos conjuntos de treino e validação."
        )

    treino, teste = divisao

    modelo_teste = RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
    )

    modelo_teste.fit(X.iloc[treino], y.iloc[treino])
    pred_novo = modelo_teste.predict(X.iloc[teste])

    acc_novo = accuracy_score(y.iloc[teste], pred_novo)
    f1_novo = f1_score(y.iloc[teste], pred_novo, average="macro")

    # Compara com o modelo atualmente utilizado no navegador.
    with open(ARQUIVO_MODELO_ATUAL, encoding="utf-8") as arq:
        modelo_atual = json.load(arq)

    if modelo_atual.get("colunas") != COLUNAS_MODELO:
        raise RuntimeError("As colunas do modelo atual não correspondem ao treinamento.")

    pred_atual = prever_json(modelo_atual, X.iloc[teste])
    acc_atual = accuracy_score(y.iloc[teste], pred_atual)
    f1_atual = f1_score(y.iloc[teste], pred_atual, average="macro")

    aprovado = (
        f1_novo >= MIN_F1
        and f1_novo >= f1_atual - TOLERANCIA_F1
        and acc_novo >= acc_atual - TOLERANCIA_ACURACIA
    )

    metricas = {
        "aprovado": bool(aprovado),
        "partidas": int(partidas),
        "jogadas": int(quantidade),
        "jogadas_treino": int(len(treino)),
        "jogadas_validacao": int(len(teste)),
        "partidas_validacao": int(len(set(grupos.iloc[teste]))),
        "classes": sorted(classes_presentes),
        "novo": {
            "acuracia": float(acc_novo),
            "f1_macro": float(f1_novo),
        },
        "atual": {
            "acuracia": float(acc_atual),
            "f1_macro": float(f1_atual),
        },
        "criterios": {
            "f1_minimo": MIN_F1,
            "tolerancia_f1": TOLERANCIA_F1,
            "tolerancia_acuracia": TOLERANCIA_ACURACIA,
        },
    }

    salvar_metricas(metricas)

    print("\n========== VALIDAÇÃO ==========")
    print(f"Modelo atual:  acurácia={acc_atual:.4f} | F1={f1_atual:.4f}")
    print(f"Modelo novo:   acurácia={acc_novo:.4f} | F1={f1_novo:.4f}")
    print(f"Resultado: {'APROVADO' if aprovado else 'REPROVADO'}")

    if not aprovado:
        raise RuntimeError(
            "O candidato não atingiu os critérios. O modelo principal não será alterado."
        )

    # Depois da validação, treina o candidato final com todas as partidas.
    modelo_final = RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
    )
    modelo_final.fit(X, y)

    if list(modelo_final.classes_) != ["Direita", "Esquerda", "Frente"]:
        raise RuntimeError("Ordem de classes inesperada no modelo final.")

    joblib.dump(modelo_final, ARQUIVO_CANDIDATO)
    print(f"\nCandidato salvo em: {ARQUIVO_CANDIDATO}")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print(f"\nERRO: {erro}", file=sys.stderr)
        sys.exit(1)
