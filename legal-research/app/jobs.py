"""Tarefas em segundo plano (indexação, importações) com progresso consultável pela interface."""
import threading
import traceback
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


class Progresso:
    def __init__(self, job: Dict[str, Any]):
        self.job = job

    def __call__(self, feito: Optional[int] = None, total: Optional[int] = None, mensagem: Optional[str] = None, **extra):
        with _lock:
            if feito is not None:
                self.job["feito"] = feito
            if total is not None:
                self.job["total"] = total
            if mensagem is not None:
                self.job["mensagem"] = mensagem
            self.job.update(extra)


def iniciar(tipo: str, fn: Callable[[Progresso], Any], descricao: str = "") -> Dict[str, Any]:
    job = {"id": uuid.uuid4().hex[:12], "tipo": tipo, "descricao": descricao, "status": "executando", "feito": 0, "total": 0,
           "mensagem": "", "resultado": None, "erro": None, "inicio": datetime.now().isoformat(timespec="seconds"), "fim": None}
    with _lock:
        _jobs[job["id"]] = job

    def run():
        try:
            res = fn(Progresso(job))
            with _lock:
                job["resultado"] = res
                job["status"] = "concluido"
        except Exception as e:  # noqa
            with _lock:
                job["erro"] = f"{e}"
                job["status"] = "erro"
                job["traceback"] = traceback.format_exc()[-1500:]
        finally:
            with _lock:
                job["fim"] = datetime.now().isoformat(timespec="seconds")

    threading.Thread(target=run, daemon=True).start()
    return dict(job)


def obter(jid: str) -> Optional[Dict[str, Any]]:
    with _lock:
        j = _jobs.get(jid)
        return dict(j) if j else None


def listar():
    with _lock:
        return sorted((dict(j) for j in _jobs.values()), key=lambda j: j["inicio"], reverse=True)[:30]
