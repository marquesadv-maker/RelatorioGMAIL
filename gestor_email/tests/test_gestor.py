import email
import json
import os
import shutil
import tempfile
import unittest
from email import policy
from unittest import mock

from gestor_email import auth, config, db, sync
from gestor_email.app import create_app
from gestor_email.tests.fake_gmail import FakeGmail

ME = "advogado@marquesss.com.br"


class GestorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [
            mock.patch.object(config, "DATA_DIR", self.tmp),
            mock.patch.object(config, "TOKENS_DIR", os.path.join(self.tmp, "tokens")),
            mock.patch.object(config, "DB_FILE", os.path.join(self.tmp, "t.db")),
        ]
        for p in self.patches:
            p.start()
        os.makedirs(config.TOKENS_DIR)
        with open(os.path.join(config.TOKENS_DIR, f"{ME}.json"), "w") as f:
            f.write("{}")
        self.g = FakeGmail(ME)
        self.g.label_store["Label_1"] = {"id": "Label_1", "name": "MarquesPro/Tribunal", "type": "user"}
        self.g.label_store["Label_2"] = {"id": "Label_2", "name": "Equipe/Maria Elisa", "type": "user"}
        self.svc_patch = mock.patch.object(auth, "get_service", return_value=self.g)
        self.svc_patch.start()
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        self.h = {"X-Gestor-Token": self.app.config["SESSION_TOKEN"]}

    def tearDown(self):
        self.svc_patch.stop()
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, url):
        r = self.client.get(url, headers=self.h)
        self.assertEqual(r.status_code, 200, r.data)
        return r.get_json()

    def post(self, url, **kw):
        r = self.client.post(url, headers=self.h, **kw)
        self.assertEqual(r.status_code, 200, r.data)
        return r.get_json()

    def assert_no_protected_changes(self):
        for kind, _id, body in self.g.modify_calls:
            for lst in (body.get("addLabelIds", []), body.get("removeLabelIds", [])):
                self.assertFalse(set(lst) & config.PROTECTED_LABELS, body)

    # ─── Testes ──────────────────────────────────────────────────────────

    def test_token_obrigatorio(self):
        self.assertEqual(self.client.get("/api/accounts").status_code, 403)
        self.assertEqual(self.client.get("/api/accounts", headers={"X-Gestor-Token": "x"}).status_code, 403)

    def test_sync_inicial_sem_notificacoes_e_incremental_com_regra(self):
        self.g.add_message("Cliente <cliente@ex.com>", "Antigo")
        r = sync.sync_account(ME)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM notifications")["n"], 0)
        self.assertEqual(len(db.rows("SELECT * FROM send_as")), 2)

        self.post("/api/rules", json={"account": ME, "direction": "recebido",
                                      "pattern": "@trt2.jus.br", "label_ids": ["Label_1", "UNREAD"]})
        mid = self.g.add_message("PJe <intimacao@trt2.jus.br>", "Intimação")
        sync.sync_account(ME)
        self.assertIn("Label_1", self.g.msg_store[mid]["labelIds"])
        self.assertIn("UNREAD", self.g.msg_store[mid]["labelIds"])  # continua não lida no Gmail
        self.assertIn("INBOX", self.g.msg_store[mid]["labelIds"])
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM notifications")["n"], 1)
        self.assert_no_protected_changes()

        st = self.get("/api/status")
        self.assertEqual(st["recebidas_hoje"], 2)
        self.assertEqual(st["hoje_por_etiqueta"][0]["name"], "MarquesPro/Tribunal")

    def test_abrir_nao_altera_unread_no_gmail(self):
        mid = self.g.add_message("Cliente <cliente@ex.com>", "Dúvida", attachment="doc.pdf")
        sync.sync_account(ME)
        threads = self.get("/api/threads?label=INBOX")
        self.assertFalse(threads[0]["read_local"])
        t = self.get(f"/api/threads/{ME}/{threads[0]['thread_id']}")
        self.assertIn("Olá", t["messages"][0]["body"]["text"])
        self.assertEqual(t["messages"][0]["body"]["attachments"][0]["filename"], "doc.pdf")
        self.assertIn("UNREAD", self.g.msg_store[mid]["labelIds"])
        self.assertEqual(self.g.modify_calls, [])
        self.assertTrue(self.get("/api/threads?label=INBOX")[0]["read_local"])
        self.assertTrue(self.get("/api/threads?label=INBOX")[0]["unread_gmail"])

    def test_envio_por_usuario_com_nome_assinatura_e_etiqueta_automatica(self):
        sync.sync_account(ME)
        self.post("/api/rules", json={"account": ME, "direction": "enviado",
                                      "pattern": "mariaelisa@marquesss.com.br", "label_ids": ["Label_2"]})
        r = self.post("/api/send", data={
            "account": ME, "from_email": "mariaelisa@marquesss.com.br", "to": "Fulano <f@ex.com>",
            "subject": "Teste", "html": "<p>Olá</p><div>-- <br>Maria Elisa</div>", "labels": json.dumps(["Label_1"]),
        })
        raw = email.message_from_bytes(self.g.sent_raw[-1], policy=policy.default)
        self.assertEqual(str(raw["From"]), "Maria Elisa <mariaelisa@marquesss.com.br>")
        self.assertIn("Fulano", str(raw["To"]))
        labels = self.g.msg_store[r["id"]]["labelIds"]
        self.assertIn("Label_1", labels)
        self.assertIn("Label_2", labels)
        self.assert_no_protected_changes()

    def test_remetente_nao_autorizado(self):
        sync.sync_account(ME)
        r = self.client.post("/api/send", headers=self.h, data={
            "account": ME, "from_email": "outro@ex.com", "to": "a@b.com", "subject": "x", "html": "x"})
        self.assertEqual(r.status_code, 400)

    def test_responder_e_encaminhar_com_anexo_e_etiquetas(self):
        mid = self.g.add_message("Cliente <cliente@ex.com>", "Contrato", attachment="contrato.pdf",
                                 labels=("INBOX", "UNREAD", "Label_1"), to=f"{ME}, colega@ex.com")
        sync.sync_account(ME)

        ctx = self.get(f"/api/compose-context/{ME}/{mid}?mode=responder_todos")
        self.assertEqual(ctx["subject"], "Re: Contrato")
        self.assertIn("cliente@ex.com", ctx["to"])
        self.assertIn("colega@ex.com", ctx["cc"])
        self.assertNotIn(ME, ctx["cc"])
        self.post("/api/send", data={"account": ME, "to": ctx["to"], "subject": ctx["subject"],
                                     "html": "ok" + ctx["quoted"], "mode": "responder", "ref_message_id": mid})
        raw = email.message_from_bytes(self.g.sent_raw[-1], policy=policy.default)
        self.assertEqual(raw["In-Reply-To"], f"<{mid}@x>")

        ctx = self.get(f"/api/compose-context/{ME}/{mid}?mode=encaminhar")
        self.assertEqual(ctx["subject"], "Enc: Contrato")
        self.assertIn("Mensagem encaminhada", ctx["quoted"])
        self.assertEqual(ctx["label_ids"], ["Label_1"])  # replica etiquetas
        r = self.post("/api/send", data={"account": ME, "to": "parceiro@ex.com", "subject": ctx["subject"],
                                         "html": ctx["quoted"], "mode": "encaminhar", "ref_message_id": mid,
                                         "labels": json.dumps(ctx["label_ids"])})
        raw = email.message_from_bytes(self.g.sent_raw[-1], policy=policy.default)
        names = [p.get_filename() for p in raw.iter_attachments()]
        self.assertEqual(names, ["contrato.pdf"])
        self.assertIn("Label_1", self.g.msg_store[r["id"]]["labelIds"])
        self.assertIn("UNREAD", self.g.msg_store[mid]["labelIds"])

    def test_etiquetas_de_conversa_ignoram_protegidas(self):
        mid = self.g.add_message("Cliente <cliente@ex.com>", "Oi")
        sync.sync_account(ME)
        tid = self.g.msg_store[mid]["threadId"]
        self.post("/api/threads/labels", json={"account": ME, "thread_ids": [tid],
                                                "add": ["Label_1"], "remove": ["UNREAD", "INBOX"]})
        self.assertEqual(sorted(self.g.msg_store[mid]["labelIds"]), ["INBOX", "Label_1", "UNREAD"])
        self.assert_no_protected_changes()
        by_name = self.get("/api/threads?label_nome=MarquesPro/Tribunal")
        self.assertEqual(len(by_name), 1)

    def test_history_expirado_refaz_sync(self):
        sync.sync_account(ME)
        db.set_account_state(ME, history_id="10")  # simulador responde 404
        self.g.add_message("X <x@ex.com>", "Novo")
        self.assertEqual(sync.sync_account(ME)["status"], "ok")
        self.assertEqual(len(self.get("/api/threads?label=INBOX")), 1)

    def test_contatos_e_assinatura_local(self):
        self.g.add_message("Maria Elisa <mariaelisa@marquesss.com.br>", "Oi")
        sync.sync_account(ME)
        c = self.get("/api/contacts?q=maria")
        self.assertEqual(c[0]["name"], "Maria Elisa")
        sa = self.get("/api/send-as")
        self.assertIn("OAB/SP", next(s for s in sa if s["email"] == ME)["signature"])
        self.post("/api/send-as/signature", json={"account": ME, "email": ME,
                                                  "local_signature": "Local", "use_local": True})
        sa = self.get("/api/send-as")
        self.assertEqual(next(s for s in sa if s["email"] == ME)["signature"], "Local")

    def test_contador_de_notificacoes(self):
        self.g.add_message("PJe TRT2 <pje@trt2.jus.br>", "Intimação - Processo 123")
        self.g.add_message("DJE <dje@tjsp.jus.br>", "Publicação no Diário Oficial")
        self.g.add_message("Cliente <cliente@ex.com>", "Oi, tudo bem?")
        sync.sync_account(ME)
        n = self.get("/api/status")["notificacoes"]
        self.assertEqual(n["hoje"], 2)
        self.assertEqual(n["pendentes"], 2)
        self.assertEqual({t["nome"] for t in n["por_tipo"]}, {"Intimação", "Publicação / DJE"})
        lista = self.get("/api/threads?label=ALL&tipo=TRIBUNAL")
        self.assertEqual(len(lista), 2)
        self.assertTrue(all(t["notificacao"] for t in lista))
        # Abrir no sistema reduz "pendentes" sem alterar o Gmail
        self.get(f"/api/threads/{ME}/{lista[0]['thread_id']}")
        self.assertEqual(self.get("/api/status")["notificacoes"]["pendentes"], 1)
        self.assertEqual(self.g.modify_calls, [])

    def test_lida_no_gmail_conta_como_lida_opcional(self):
        mid = self.g.add_message("Cliente <cliente@ex.com>", "Oi", labels=("INBOX", "UNREAD", "CATEGORY_PERSONAL"))
        self.g.add_message("Loja <promo@loja.com>", "Oferta", labels=("INBOX", "UNREAD", "CATEGORY_PROMOTIONS"))
        sync.sync_account(ME)
        # Lida no Gmail (outra pessoa abriu lá)
        self.g.msg_store[mid]["labelIds"].remove("UNREAD")
        self.g.history_id += 1
        self.g.hist_store.append({"id": str(self.g.history_id),
                                  "labelsRemoved": [{"message": {"id": mid}, "labelIds": ["UNREAD"]}]})
        sync.sync_account(ME)
        principal = self.get("/api/threads?label=INBOX&categoria=principal")
        self.assertEqual([t["subject"] for t in principal], ["Oi"])
        self.assertFalse(principal[0]["read_local"])          # padrão: leituras independentes
        self.assertEqual(self.get("/api/status")["nao_lidas_categoria"]["promocoes"], 1)
        self.post("/api/settings", json={"lida_no_gmail_conta_como_lida": True})
        self.assertTrue(self.get("/api/threads?label=INBOX&categoria=principal")[0]["read_local"])
        self.assertEqual(self.get("/api/status")["nao_lidas_categoria"]["principal"], 0)
        r = self.client.get("/api/threads?label=INBOX&limit=1", headers=self.h)
        self.assertEqual(r.headers["X-Total-Count"], "2")
        self.assertEqual(self.g.modify_calls, [])            # nunca altera o Gmail

    def test_anexo_svg_nunca_inline(self):
        mid = self.g.add_message("X <x@ex.com>", "Img")
        r = self.client.get(f"/api/attachment/{ME}/{mid}/a1?inline=1&tipo=image/svg%2Bxml&nome=a.svg", headers=self.h)
        self.assertTrue(r.headers["Content-Disposition"].startswith("attachment"))
        self.assertEqual(r.mimetype, "application/octet-stream")
        self.assertIn("sandbox", r.headers["Content-Security-Policy"])

    def test_pagina_com_csp_e_nonce(self):
        r = self.client.get("/")
        csp = r.headers["Content-Security-Policy"]
        nonce = csp.split("'nonce-")[1].split("'")[0]
        self.assertIn(f'nonce="{nonce}"', r.get_data(as_text=True))
        self.assertNotIn("__TOKEN__", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
