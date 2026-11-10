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
        self.post("/api/settings", json={"ocultar_anuncios": False})
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

    def test_destaques_por_periodo_e_prioridade(self):
        import time
        agora = int(time.time() * 1000)
        dia = 24 * 3600 * 1000
        self.g.add_message("Cliente <cliente@ex.com>", "Oi hoje")
        self.g.add_message("PJe <pje@trt2.jus.br>", "Publicação no Diário Oficial", date_ms=agora - 2 * dia)
        self.g.add_message("PJe <pje@trt2.jus.br>", "Intimação - Processo 1", date_ms=agora - 5 * dia)
        self.g.add_message("Cliente <outro@ex.com>", "Antigo", date_ms=agora - 40 * dia)
        sync.sync_account(ME)
        base = "/api/threads?label=INBOX&prioridade=1&destaque=1"
        hoje_ms = int(__import__("datetime").datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        self.assertEqual(self._assuntos(base), ["Oi hoje"])
        sete = self.get(f"{base}&desde={hoje_ms - 6 * dia}")
        self.assertEqual([t["subject"] for t in sete][:2], ["Intimação - Processo 1", "Publicação no Diário Oficial"])
        self.assertEqual(len(sete), 3)
        self.assertEqual(len(self.get(f"{base}&desde={hoje_ms - 29 * dia}")), 3)
        self.assertEqual(self._assuntos(f"/api/threads?label=INBOX&destaque=0&desde={hoje_ms - 29 * dia}"), ["Antigo"])
        esp = self.get(f"{base}&desde={hoje_ms - 6 * dia}&ate={hoje_ms - 1 * dia}")
        self.assertEqual(sorted(t["subject"] for t in esp), ["Intimação - Processo 1", "Publicação no Diário Oficial"])
        self.get(f"/api/threads/{ME}/{sete[0]['thread_id']}")
        depois = self.get(f"{base}&desde={hoje_ms - 6 * dia}")
        self.assertNotEqual(depois[0]["subject"], "Intimação - Processo 1")
        self.assertEqual(self.get("/api/status")["notificacoes"]["pendentes_por_grupo"]["notificacoes"], 1)

    def test_modelos_e_ia_economica(self):
        ms = self.get("/api/modelos")
        self.assertTrue({"AUD-01", "DEF-01", "PER-03", "HTE-05", "JUL-02"} <= {m["codigo"] for m in ms})
        aud = next(m for m in ms if m["codigo"] == "AUD-02")
        self.assertIn("PROCESSO", aud["campos"])
        self.assertNotIn("REGRA", aud["corpo"])
        self.assertFalse(self.get("/api/ia/status")["configurada"])
        texto = ("INTIMAÇÃO. Fica designada audiência de conciliação telepresencial para o dia 15/12/2026 às 14h30, "
                 "no processo 0001234-56.2026.5.02.0001. Reclamante: Fulano de Tal Reclamada: Empresa Exemplo Ltda.")
        r = self.post("/api/ia/preencher", data={"codigo": "", "instrucoes": texto})
        self.assertEqual(r["codigo"], "AUD-02")
        self.assertFalse(r["uso"]["ia"])
        self.assertEqual(r["campos"]["PROCESSO"]["valor"], "0001234-56.2026.5.02.0001")
        self.assertEqual(r["campos"]["DATA"]["valor"], "15/12/2026")
        self.assertEqual(r["campos"]["HORARIO"]["valor"], "14h30")
        self.assertEqual(r["campos"]["MODALIDADE"]["valor"], "telepresencial")
        self.assertEqual(r["campos"]["RECLAMANTE"]["valor"], "Fulano de Tal")
        self.assertEqual(r["pendencias"], [])
        self.assertNotIn("[PREENCHER", r["corpo"])
        self.assertFalse(r["blocos"]["BLOCO_LINK"]["incluir"])
        r = self.post("/api/ia/preencher", data={"codigo": "AUD-02", "instrucoes": "audiência dia 15/12/2026"})
        self.assertIn("PROCESSO", r["pendencias"])
        self.assertIn("[PREENCHER: PROCESSO]", r["corpo"])
        self.assertIn("IA não configurada", r["observacoes"])

    def _cnj(self, n7="0004321", aa="2026", tr="02", o="0002"):
        dd = 98 - (int(n7 + aa + "5" + tr + o + "00") % 97)
        return f"{n7}-{dd:02d}.{aa}.5.{tr}.{o}"

    def _ia_fake(self, *respostas):
        """Cliente de IA simulado: devolve as respostas em ordem e registra as chamadas."""
        chamadas = []

        class R:
            stop_reason = "end_turn"
            def __init__(self, dados):
                self.usage = type("U", (), {"input_tokens": 700, "output_tokens": 90, "cache_read_input_tokens": 0})()
                self.content = [type("B", (), {"type": "text", "text": json.dumps(dados)})()]

        class C:
            class beta:
                class messages:
                    @staticmethod
                    def create(**kw):
                        chamadas.append(kw)
                        return R(respostas[min(len(chamadas), len(respostas)) - 1])
        return C, chamadas

    def test_ia_prompt_minimo(self):
        from gestor_email import ia
        texto = (f"Perícia de insalubridade designada para 20/01/2027 às 9h, processo {self._cnj()}. "
                 "Reclamante: Beltrano Silva. Reclamada: Empresa Exemplo Ltda. Local: Rua A, 1. Prazo para quesitos: 5 dias.")
        C, chamadas = self._ia_fake({"codigo": "PER-03", "revisao": [], "campos": [], "blocos": [], "pendencias": [], "observacoes": ""})
        ia.preencher_auto("PER-03", texto, None, [], client=C)
        kw = chamadas[0]
        self.assertLess(len(kw["system"][0]["text"]), 2500)
        pedido = kw["messages"][0]["content"][-1]["text"]
        self.assertLess(len(pedido), 7000)
        self.assertNotIn("PAR-01", pedido)
        self.assertIn("trecho", kw["system"][0]["text"])

    def test_ia_assertiva_preenche_o_que_falta_e_verifica(self):
        from gestor_email import ia
        proc = self._cnj()
        texto = (f"Perícia de insalubridade designada para 20/01/2027 às 9h, processo {proc}. "
                 "Reclamante: Beltrano Silva. Reclamada: Empresa Exemplo Ltda. Local da perícia: Rua das Flores, 100, São Paulo. "
                 "Prazo para quesitos: 5 dias.")
        # 1ª chamada: preenche o que faltou (inclui um PERITO inventado); 2ª (verificação): não consegue sustentar o PERITO
        C, chamadas = self._ia_fake(
            {"codigo": "PER-03", "revisao": [], "campos": [
                {"nome": "LOCAL", "valor": "Rua das Flores, 100, São Paulo", "trecho": "Local da perícia: Rua das Flores, 100, São Paulo"},
                {"nome": "PRAZO_QUESITOS", "valor": "5 dias", "trecho": "Prazo para quesitos: 5 dias"}],
             "blocos": [{"nome": "BLOCO_DOC_PERICIA", "incluir": False, "texto": ""}], "pendencias": [], "observacoes": ""},
            {"campos": []})
        out = ia.preencher_auto("PER-03", texto, None, [], client=C)
        self.assertEqual(out["codigo"], "PER-03")
        # o que a leitura local fez
        self.assertEqual(out["campos"]["PROCESSO"]["origem"], "documento")
        self.assertEqual(out["campos"]["DATA"]["valor"], "20/01/2027")
        self.assertEqual(out["campos"]["PARTE_A"]["valor"], "Beltrano Silva")          # derivado de RECLAMANTE
        # o que faltava foi preenchido pela IA automaticamente, com prova no documento
        self.assertEqual(out["campos"]["LOCAL"]["origem"], "ia")
        self.assertFalse(out["campos"]["LOCAL"]["verificar"])
        self.assertEqual(out["campos"]["PRAZO_QUESITOS"]["valor"], "5 dias")
        self.assertEqual(out["pendencias"], [])
        self.assertNotIn("[PREENCHER", out["corpo"])
        self.assertEqual(len(chamadas), 1)   # nada a verificar: segunda passada não é necessária

    def test_ia_nao_aceita_valor_sem_prova_e_faz_segunda_passada(self):
        from gestor_email import ia
        texto = (f"Perícia designada para 20/01/2027 às 9h, processo {self._cnj()}. Reclamante: Beltrano Silva. "
                 "Reclamada: Empresa Exemplo Ltda. Prazo para quesitos: 5 dias.")
        C, chamadas = self._ia_fake(
            {"codigo": "PER-03", "revisao": [], "campos": [
                {"nome": "LOCAL", "valor": "Fórum Trabalhista da Barra Funda", "trecho": "Fórum Trabalhista da Barra Funda"},
                {"nome": "PRAZO_QUESITOS", "valor": "5 dias", "trecho": "Prazo para quesitos: 5 dias"}],
             "blocos": [], "pendencias": [], "observacoes": ""},
            {"campos": [{"nome": "LOCAL", "valor": "", "trecho": ""}]})
        out = ia.preencher_auto("PER-03", texto, None, [], client=C)
        self.assertEqual(len(chamadas), 2)                                  # 2ª passada de verificação
        self.assertIn("LOCAL", out["pendencias"])                          # valor inventado foi descartado
        self.assertEqual(out["campos"]["LOCAL"]["origem"], "pendente")
        self.assertIn("[PREENCHER: LOCAL]", out["corpo"])
        self.assertNotIn("Barra Funda", out["corpo"])
        self.assertEqual(out["campos"]["PRAZO_QUESITOS"]["valor"], "5 dias")

    def test_ia_corrige_valor_lido_localmente_e_cnj_invalido_e_sinalizado(self):
        from gestor_email import ia
        # Número com dígito verificador errado e nome ambíguo: a IA confere os dois
        texto = ("Audiência de conciliação telepresencial dia 15/12/2026 às 14h30, processo 0001234-56.2026.5.02.0001. "
                 "Reclamante: Fulano de Tal 123 Reclamada: Empresa Exemplo Ltda.")
        C, chamadas = self._ia_fake({"codigo": "AUD-02", "revisao": [
            {"nome": "RECLAMANTE", "correto": False, "valor": "Fulano de Tal", "trecho": "Reclamante: Fulano de Tal"},
            {"nome": "PROCESSO", "correto": True, "valor": "0001234-56.2026.5.02.0001", "trecho": "processo 0001234-56.2026.5.02.0001"}],
            "campos": [], "blocos": [], "pendencias": [], "observacoes": ""})
        out = ia.preencher_auto("", texto, None, [], client=C)
        self.assertEqual(out["campos"]["RECLAMANTE"]["valor"], "Fulano de Tal")
        self.assertTrue(out["campos"]["RECLAMANTE"]["verificar"])           # corrigido pela IA: advogado confere
        self.assertIn("Fulano de Tal 123", out["campos"]["RECLAMANTE"]["corrigido_de"])
        self.assertTrue(out["campos"]["PROCESSO"].get("verificar"))        # dígitos do CNJ não batem
        self.assertIn("dígitos verificadores", out["observacoes"])

    def test_sem_chave_sinaliza_ia_indisponivel_e_prazo_interno_pela_regra(self):
        from gestor_email import ia
        texto = (f"Audiência una presencial dia 15/12/2026 às 9h30, processo {self._cnj()}. "
                 "Reclamante: Fulano de Tal Reclamada: Empresa Exemplo Ltda.")
        out = ia.preencher_auto("DEF-01", texto, None, [], prazo_interno_dias=3)
        self.assertTrue(out["ia_indisponivel"])
        self.assertEqual(out["campos"]["PRAZO_INTERNO"]["origem"], "regra")
        self.assertEqual(out["campos"]["PRAZO_INTERNO"]["valor"], "10/12/2026")   # 3 dias úteis antes de 15/12/2026 (3ª)
        out = ia.preencher_auto("DEF-01", texto, None, [])
        self.assertEqual(out["campos"]["PRAZO_INTERNO"]["origem"], "pendente")     # sem regra, nunca calcula sozinha

    def test_pdf_com_texto_local_e_imagem_pede_confirmacao(self):
        try:
            from fpdf import FPDF
        except ImportError:
            self.skipTest("fpdf2 não instalado")
        from gestor_email import ia
        pdf = FPDF()
        pdf.add_page(); pdf.set_font("Helvetica", size=11)
        for l in ("INTIMACAO - Audiencia de conciliacao telepresencial designada para 15/12/2026 as 14h30.",
                  "Processo 0001234-56.2026.5.02.0001. Reclamante: Fulano de Tal  Reclamada: Empresa Exemplo Ltda.",
                  "Compareca a parte reclamada por meio de seu representante e advogado."):
            pdf.multi_cell(0, 8, l, new_x="LMARGIN", new_y="NEXT")
        out = ia.preencher_auto("", "", None, [("intimacao.pdf", "application/pdf", bytes(pdf.output()))])
        self.assertEqual(out["codigo"], "AUD-02")
        self.assertFalse(out["uso"]["ia"])
        self.assertEqual(out["campos"]["DATA"]["valor"], "15/12/2026")

        class C:
            class beta:
                class messages:
                    @staticmethod
                    def create(**kw):
                        raise AssertionError("IA chamada sem confirmação")
        img = ia.preencher_auto("AUD-02", "", None, [("scan.png", "image/png", b"x")], client=C)
        self.assertEqual(img["precisa_visao"], ["scan.png"])

    def test_logo_da_assinatura_vai_embutida(self):
        sync.sync_account(ME)
        self.post("/api/send-as/signature", json={"account": ME, "email": ME, "use_local": True,
                  "local_signature": '<img src="/static/logo-m-dourado.png"><br>Dr. Advogado'})
        r = self.post("/api/send", data={"account": ME, "to": "a@b.com", "subject": "x",
                                         "html": '<p>Oi</p><img src="/static/logo-m-dourado.png">'})
        raw = email.message_from_bytes(self.g.sent_raw[-1], policy=policy.default)
        imgs = [p for p in raw.walk() if p.get_content_type() == "image/png"]
        self.assertEqual(len(imgs), 1)
        self.assertIn("cid:", raw.get_body(("html",)).get_content())

    def _assuntos(self, url):
        return sorted(t["subject"] for t in self.get(url))

    def test_resgate_do_spam_e_anuncios(self):
        # Histórico: já escrevemos ao cliente e ele já nos escreveu antes
        self.g.add_message(f"Dr. <{ME}>", "Contrato", labels=("SENT",), to="Cliente Antigo <antigo@cliente.com>")
        self.g.add_message("Cliente Conhecido <conhecido@cliente.com>", "Dúvida anterior", labels=("INBOX",))
        # Na caixa
        self.g.add_message("Loja <promo@loja.com>", "Oferta imperdível", labels=("INBOX", "UNREAD", "CATEGORY_PROMOTIONS"))
        self.g.add_message("Boletim <news@boletim.com>", "Novidades da semana", labels=("INBOX", "UNREAD"),
                           extra_headers=[{"name": "List-Unsubscribe", "value": "<mailto:x@y>"}])
        # No spam
        self.g.add_message("Cliente Antigo <antigo@cliente.com>", "Segue documento", labels=("SPAM", "UNREAD"))
        self.g.add_message("Cliente Conhecido <conhecido@cliente.com>", "Dúvida urgente", labels=("SPAM", "UNREAD"))
        self.g.add_message("PJe <naoresponda@trt2.jus.br>", "Intimação - Processo 1", labels=("SPAM", "UNREAD"))
        self.g.add_message("Desconhecido <alguem@golpe.com>", "Você ganhou um prêmio", labels=("SPAM", "UNREAD"))
        self.g.add_message("Marketing <marketing@agencia.com>", "Promoção de curso online", labels=("SPAM", "UNREAD"),
                           extra_headers=[{"name": "List-Unsubscribe", "value": "<mailto:x@y>"}])
        self.g.add_message("Estranho <fulano@gmail.com>", "Oi, tudo bem?", labels=("SPAM", "UNREAD"))
        sync.sync_account(ME)

        caixa = self._assuntos("/api/threads?label=INBOX")
        self.assertEqual(caixa, ["Dúvida anterior", "Dúvida urgente", "Intimação - Processo 1", "Segue documento"])
        self.assertEqual(self._assuntos("/api/threads?label=ANUNCIOS"), ["Novidades da semana", "Oferta imperdível"])
        # O que não é cliente nem notificação continua só no spam
        todos = self._assuntos("/api/threads?label=ALL")
        for fora in ("Você ganhou um prêmio", "Promoção de curso online", "Oi, tudo bem?"):
            self.assertNotIn(fora, todos)
        # Resgatados indicam a origem; a notificação entra no contador
        por_assunto = {t["subject"]: t for t in self.get("/api/threads?label=INBOX")}
        self.assertEqual(por_assunto["Segue documento"]["resgatado"], "cliente")
        self.assertEqual(por_assunto["Intimação - Processo 1"]["resgatado"], "notificacao")
        self.assertIsNone(por_assunto["Dúvida anterior"]["resgatado"])
        self.assertEqual(self.get("/api/status")["notificacoes"]["pendentes"], 1)
        # Nada foi alterado no Gmail até agora
        self.assertEqual(self.g.modify_calls, [])
        # Preferência: mostrar anúncios de volta na caixa
        self.post("/api/settings", json={"ocultar_anuncios": False})
        self.assertIn("Oferta imperdível", self._assuntos("/api/threads?label=INBOX"))

    def test_nao_spam_move_no_gmail_e_correcao_manual(self):
        self.g.add_message(f"Dr. <{ME}>", "Oi", labels=("SENT",), to="Cli <cli@x.com>")
        mid = self.g.add_message("Cli <cli@x.com>", "Resposta", labels=("SPAM", "UNREAD"))
        loja = self.g.add_message("Loja <l@loja.com>", "Oferta", labels=("INBOX", "UNREAD", "CATEGORY_PROMOTIONS"))
        sync.sync_account(ME)
        tid = self.g.msg_store[mid]["threadId"]
        self.post(f"/api/threads/{ME}/{tid}/nao-spam")
        self.assertEqual(sorted(self.g.msg_store[mid]["labelIds"]), ["INBOX", "UNREAD"])
        self.assertIn("Resposta", self._assuntos("/api/threads?label=INBOX"))
        # Falso anúncio: o usuário devolve à caixa (só local) e a correção resiste a novas sincronizações
        tl = self.g.msg_store[loja]["threadId"]
        self.assertNotIn("Oferta", self._assuntos("/api/threads?label=INBOX"))
        self.post(f"/api/threads/{ME}/{tl}/triagem", json={"valor": "inbox"})
        sync.sync_account(ME)
        self.assertIn("Oferta", self._assuntos("/api/threads?label=INBOX"))

    def test_grupos_de_empresas_e_subgrupos(self):
        e = self.post("/api/grupos", json={"nome": "Empresa Exemplo Ltda", "observacao": "Cliente desde 2020"})
        r = self.client.post("/api/grupos", headers=self.h, json={"nome": "empresa exemplo ltda"})
        self.assertEqual(r.status_code, 400)  # nome duplicado (sem diferenciar maiúsculas)
        self.post(f"/api/grupos/{e['id']}/subgrupos", json={
            "nome": "RH", "para": "Rh@Exemplo.com; gerente.rh@exemplo.com", "cc": "diretoria@exemplo.com", "cco": ""})
        self.post(f"/api/grupos/{e['id']}/subgrupos", json={"nome": "Jurídico", "para": "juridico@exemplo.com"})
        ruim = self.client.post(f"/api/grupos/{e['id']}/subgrupos", headers=self.h, json={"nome": "X", "para": "sem-arroba"})
        self.assertEqual(ruim.status_code, 400)
        vazio = self.client.post(f"/api/grupos/{e['id']}/subgrupos", headers=self.h, json={"nome": "Y"})
        self.assertEqual(vazio.status_code, 400)
        g = self.get("/api/grupos")
        self.assertEqual(len(g), 1)
        rh = next(s for s in g[0]["subgrupos"] if s["nome"] == "RH")
        self.assertEqual(rh["para"], "rh@exemplo.com, gerente.rh@exemplo.com")
        # Aparece nas sugestões de destinatário ao digitar o nome
        sug = self.get("/api/contacts?q=exemplo")
        self.assertTrue(any(c.get("grupo") and c["name"] == "Empresa Exemplo Ltda › RH" for c in sug))
        self.assertEqual(next(c for c in sug if c.get("grupo") and "RH" in c["name"])["cc"], "diretoria@exemplo.com")
        # Excluir a empresa remove os subgrupos
        self.client.delete(f"/api/grupos/{e['id']}", headers=self.h)
        self.assertEqual(self.get("/api/grupos"), [])

    def test_alerta_notificacao_sem_email_enviado(self):
        a = self.g.add_message("PJe <pje@trt2.jus.br>", "Intimação - Processo 0001234-56.2026.5.02.0001")
        b = self.g.add_message("PJe <pje@trt2.jus.br>", "Citação eletrônica - Processo 0009999-11.2026.5.02.0002")
        c = self.g.add_message("PJe <pje@trt2.jus.br>", "Publicação DJE referente ao processo 0007777-22.2026.5.02.0003")
        self.g.add_message("Cliente <cliente@ex.com>", "Conversa comum")
        sync.sync_account(ME)
        por = lambda: {t["subject"].split(" ")[0]: t["sem_envio"] for t in self.get("/api/threads?label=INBOX")}
        self.assertEqual(por(), {"Intimação": True, "Citação": True, "Publicação": True, "Conversa": False})
        # 1) Enviado pelo Gmail depois, com o mesmo assunto ("Enc: ...") -> não alerta
        self.g.add_message(f"Dr. <{ME}>", "Enc: Intimação - Processo 0001234-56.2026.5.02.0001", labels=("SENT",), to="cli@x.com")
        # 2) Enviado pelo Gmail citando só o número do processo -> não alerta
        self.g.add_message(f"Dr. <{ME}>", "Aviso ao cliente", "Processo 0007777-22.2026.5.02.0003 publicado", labels=("SENT",), to="cli@x.com")
        sync.sync_account(ME)
        self.assertEqual(por(), {"Intimação": False, "Citação": True, "Publicação": False, "Conversa": False})
        # 3) Enviado pela ferramenta a partir da notificação (encaminhamento = outra conversa) -> não alerta
        self.post("/api/send", data={"account": ME, "to": "cli@x.com", "subject": "Assunto livre", "html": "oi",
                                     "mode": "encaminhar", "ref_message_id": b})
        self.assertEqual(por()["Citação"], False)
        self.assertFalse(self.get(f"/api/threads/{ME}/{self.g.msg_store[b]['threadId']}")["sem_envio"])

    def test_prazo_interno_pela_regra_configurada(self):
        n = self._cnj()
        texto = f"Audiência una presencial dia 15/12/2026 às 9h30, processo {n}. Reclamante: Fulano de Tal Reclamada: Empresa Exemplo Ltda."
        r = self.post("/api/ia/preencher", data={"codigo": "DEF-01", "instrucoes": texto})
        self.assertEqual(r["campos"]["PRAZO_INTERNO"]["origem"], "pendente")
        self.assertEqual(self.client.post("/api/settings", headers=self.h, json={"prazo_interno_dias": "abc"}).status_code, 400)
        self.post("/api/settings", json={"prazo_interno_dias": "3"})
        r = self.post("/api/ia/preencher", data={"codigo": "DEF-01", "instrucoes": texto})
        self.assertEqual(r["campos"]["PRAZO_INTERNO"]["valor"], "10/12/2026")
        self.assertTrue(r["ia_indisponivel"])

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
