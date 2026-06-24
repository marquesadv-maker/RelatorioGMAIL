"""
Gmail Monitor — ponto de entrada principal.

Uso:
    python gmail_monitor.py              # executa análise e gera relatório
    python gmail_monitor.py --reset      # limpa estado e reprocessa tudo
"""

import sys
import os

from logger import get_logger
from state_manager import load_state, save_state, get_processed_ids, get_thread_history_id, mark_thread_processed
from gmail_client import get_gmail_service, list_threads, get_thread_detail, parse_thread
from analyzer import analyze_threads
from report_generator import generate_and_save

log = get_logger()

USER_EMAIL = "marquesadv@marquesss.com.br"
MAX_THREADS = 200  # máximo de threads a buscar por execução


def run(reset: bool = False):
    log.info("=== Iniciando Gmail Monitor ===")

    state = load_state()
    if reset:
        log.info("Reset solicitado — limpando estado anterior.")
        state = {"processed_thread_ids": [], "thread_last_modified": {}}

    processed_ids = get_processed_ids(state)
    log.info(f"Threads já processadas em execuções anteriores: {len(processed_ids)}")

    try:
        service = get_gmail_service()
    except Exception as e:
        log.error(f"Falha ao autenticar no Gmail: {e}")
        sys.exit(1)

    log.info("Buscando threads não lidas da caixa de entrada...")
    try:
        raw_threads = list_threads(service, max_results=MAX_THREADS, unread_only=True)
    except Exception as e:
        log.error(f"Falha ao listar threads: {e}")
        sys.exit(1)

    log.info(f"Total de threads não lidas encontradas: {len(raw_threads)}")

    threads_data = []
    new_or_modified = 0

    for raw in raw_threads:
        tid = raw["id"]
        current_history_id = raw.get("historyId", "")
        stored_history_id = get_thread_history_id(state, tid)

        # Processar apenas se novo ou modificado desde a última execução
        if tid in processed_ids and stored_history_id == current_history_id:
            continue

        try:
            detail = get_thread_detail(service, tid)
            parsed = parse_thread(detail, my_email=USER_EMAIL)
            if parsed:
                threads_data.append(parsed)
                mark_thread_processed(state, tid, current_history_id)
                new_or_modified += 1
        except Exception as e:
            log.warning(f"Erro ao processar thread {tid}: {e}")

    log.info(f"Threads novas ou modificadas processadas: {new_or_modified}")

    # Para gerar o relatório completo do dia, incluímos todas as threads
    # (as já processadas podem não estar em threads_data se não mudaram)
    # Solução: sempre buscar detalhes de todas para o relatório diário.
    # Mas por eficiência, fazemos uma segunda passagem apenas para threads não incluídas acima.
    included_ids = {t["thread_id"] for t in threads_data}
    for raw in raw_threads:
        tid = raw["id"]
        if tid not in included_ids:
            try:
                detail = get_thread_detail(service, tid)
                parsed = parse_thread(detail, my_email=USER_EMAIL)
                if parsed:
                    threads_data.append(parsed)
            except Exception as e:
                log.warning(f"Erro ao re-buscar thread {tid}: {e}")

    log.info(f"Total de threads para análise: {len(threads_data)}")

    results = analyze_threads(threads_data)

    log.info(
        f"Classificação — Alta: {len(results['ALTA'])} | "
        f"Média: {len(results['MÉDIA'])} | "
        f"Baixa: {len(results['BAIXA'])} | "
        f"Insatisfeitos: {len(results['dissatisfied'])} | "
        f"Sem resp >48h: {len(results['unanswered_48h'])}"
    )

    report_path = generate_and_save(results)
    log.info(f"Dashboard salvo em: {report_path}")

    save_state(state)
    log.info("Estado salvo. Execução concluída.")

    print("\n" + "=" * 60)
    print(f"Dashboard gerado: {report_path}")
    print(f"Alta: {len(results['ALTA'])} | Média: {len(results['MÉDIA'])} | "
          f"Baixa: {len(results['BAIXA'])}")
    print(f"Insatisfeitos: {len(results['dissatisfied'])} | "
          f"Sem resposta >48h: {len(results['unanswered_48h'])}")
    print("=" * 60)


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    run(reset=reset_flag)
