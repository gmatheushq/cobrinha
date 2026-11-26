"""Treina, valida, arquiva e atualiza com segurança a IA principal."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
PASTA_DADOS = BASE / "dadosTreino"
PASTA_MODELOS = BASE / "modelos"
ARQUIVO_ATUAL = BASE / "docs" / "modelo.json"
ARQUIVO_CANDIDATO = BASE / "modelo_cobrinha_candidato.pkl"
ARQUIVO_JSON_CANDIDATO = BASE / "docs" / "modelo.candidato.json"
ARQUIVO_METRICAS = BASE / "relatorio_treino.json"
VERSOES = PASTA_MODELOS / "versoes.json"

COLUNAS = [
    "fruta_frente",
    "fruta_esq",
    "rel_perigo_frente",
    "rel_perigo_esq",
    "rel_perigo_dir",
    "TamanhoCobrinha",
]

CLASSES = ["Direita", "Esquerda", "Frente"]


def contar_dados_humanos():
    """Conta exclusivamente CSVs com o prefixo da exportação humana."""
    arquivos = sorted(PASTA_DADOS.glob("dados_web_*.csv"))
    registros = 0

    for arquivo in arquivos:
        try:
            registros += len(pd.read_csv(arquivo))
        except Exception as erro:
            print(f"[AVISO] CSV ignorado: {arquivo.name}: {erro}")

    return len(arquivos), registros


def carregar_versoes():
    if not VERSOES.exists():
        return []

    with open(VERSOES, encoding="utf-8") as arq:
        dados = json.load(arq)

    if not isinstance(dados, list):
        raise RuntimeError("O índice de versões está inválido.")

    return dados


def validar_json(caminho):
    with open(caminho, encoding="utf-8") as arq:
        modelo = json.load(arq)

    if modelo.get("classes") != CLASSES:
        raise RuntimeError("Classes inválidas no JSON exportado.")

    if modelo.get("colunas") != COLUNAS:
        raise RuntimeError("Colunas inválidas no JSON exportado.")

    if modelo.get("escala") != 10000:
        raise RuntimeError("Escala inválida no JSON exportado.")

    arvores = modelo.get("arvores")

    if not isinstance(arvores, list) or len(arvores) != 300:
        raise RuntimeError("O candidato não contém as 300 árvores esperadas.")

    for arvore in arvores:
        if not all(k in arvore for k in ("f", "t", "r", "p")):
            raise RuntimeError("Árvore exportada com estrutura incompleta.")

        if not (
            len(arvore["f"]) == len(arvore["t"]) == len(arvore["r"])
        ):
            raise RuntimeError("Vetores da árvore possuem tamanhos diferentes.")

    return modelo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sem-download", action="store_true")
    args = parser.parse_args()

    if not args.sem_download:
        import baixar_dados
        baixar_dados.main()

    partidas, registros = contar_dados_humanos()

    print("\n========== BASE HUMANA ==========")
    print(f"Partidas: {partidas}")
    print(f"Registros: {registros}")

    if partidas < 10 or registros < 500:
        raise RuntimeError(
            "Dados insuficientes. São necessárias pelo menos "
            "10 partidas humanas e 500 jogadas. Modelo atual preservado."
        )

    PASTA_MODELOS.mkdir(parents=True, exist_ok=True)

    # O treinamento gera apenas um candidato; não toca no modelo publicado.
    if ARQUIVO_CANDIDATO.exists():
        ARQUIVO_CANDIDATO.unlink()

    if ARQUIVO_JSON_CANDIDATO.exists():
        ARQUIVO_JSON_CANDIDATO.unlink()

    ambiente = dict(os.environ, MPLBACKEND="Agg")

    subprocess.run(
        [sys.executable, str(BASE / "Treino.py")],
        check=True,
        cwd=BASE,
        env=ambiente,
    )

    if not ARQUIVO_CANDIDATO.exists():
        raise RuntimeError("O treinamento não gerou o modelo candidato.")

    with open(ARQUIVO_METRICAS, encoding="utf-8") as arq:
        metricas = json.load(arq)

    if metricas.get("aprovado") is not True:
        raise RuntimeError("Candidato não aprovado. Modelo atual preservado.")

    versoes = carregar_versoes()
    numero = len(versoes) + 1

    meta = {
        "versao": str(numero),
        "criado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "partidas": partidas,
        "registros": registros,
        "validacao": metricas,
    }

    import exportar_modelo_web

    exportar_modelo_web.exportar(
        str(ARQUIVO_CANDIDATO),
        str(ARQUIVO_JSON_CANDIDATO),
        meta,
    )

    # Verifica o candidato antes de fazer qualquer alteração no modelo atual.
    validar_json(ARQUIVO_JSON_CANDIDATO)

    if not ARQUIVO_ATUAL.exists():
        raise RuntimeError("Modelo principal atual não encontrado.")

    # Prepara o historico antes de alterar o modelo principal.
    versoes.append(meta)
    temporario = VERSOES.with_name("versoes.json.tmp")
    modelo_temp = ARQUIVO_ATUAL.with_name("modelo.json.rollback.tmp")

    with open(temporario, "w", encoding="utf-8") as arq:
        json.dump(versoes, arq, indent=2, ensure_ascii=False)

    nome_backup = PASTA_MODELOS / f"modelo_v{numero - 1}_anterior.json.gz"

    if not nome_backup.exists():
        with open(ARQUIVO_ATUAL, "rb") as origem:
            with gzip.open(nome_backup, "wb") as destino:
                shutil.copyfileobj(origem, destino)

    try:
        with gzip.open(nome_backup, "rb") as backup:
            json.load(backup)

        os.replace(ARQUIVO_JSON_CANDIDATO, ARQUIVO_ATUAL)

        try:
            os.replace(temporario, VERSOES)
        except Exception:
            with gzip.open(nome_backup, "rb") as origem:
                with open(modelo_temp, "wb") as destino:
                    shutil.copyfileobj(origem, destino)

            os.replace(modelo_temp, ARQUIVO_ATUAL)
            raise RuntimeError(
                "Falha ao atualizar o historico. Modelo anterior restaurado."
            )

    finally:
        if temporario.exists():
            temporario.unlink()
        if modelo_temp.exists():
            modelo_temp.unlink()

    print("\n========== ATUALIZAÇÃO CONCLUÍDA ==========")
    print(f"Modelo principal: {ARQUIVO_ATUAL}")
    print(f"Backup: {nome_backup}")
    print(f"Versão: {numero}")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print(f"\nATUALIZAÇÃO CANCELADA: {erro}", file=sys.stderr)
        sys.exit(1)
