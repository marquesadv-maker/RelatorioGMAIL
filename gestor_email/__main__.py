"""
Inicia o Gestor de E-mail em http://127.0.0.1:5055

Uso:
    python -m gestor_email            # inicia servidor e abre o navegador
    python -m gestor_email --sem-navegador
"""
import logging
import os
import sys
import threading
import webbrowser

from . import config
from .app import create_app
from .sync import SyncLoop


def main():
    os.makedirs(config.TOKENS_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    SyncLoop().start()
    url = f"http://127.0.0.1:{config.PORT}/"
    if "--sem-navegador" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Gestor de E-mail disponível em {url}  (Ctrl+C para encerrar)")
    app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
