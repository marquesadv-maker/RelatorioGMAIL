---
name: modelos-de-e-mails-marques
description: "Elabora e padroniza e-mails jurídicos e processuais do Marques Advogados S/S a partir de documentos em PDF ou imagem PNG (inclusive escaneados/fotografados) — decisões, sentenças, acórdãos, intimações, notificações, atas, laudos, comunicados de audiência e perícia, acordos e HTE. A Skill lê e interpreta o arquivo, extrai os dados relevantes, seleciona automaticamente o modelo adequado entre os cadastrados (audiências, perícias, correspondente, HTE, julgamentos, documentos), adapta o texto ao caso concreto e sinaliza dados ausentes ou ilegíveis, sem inventar informações, prazos, valores, links ou dados processuais. Use SEMPRE que o usuário anexar um documento processual e pedir para 'fazer o e-mail', 'montar o e-mail conforme o modelo', 'padronizar o e-mail', 'comunicar o cliente/empresa', 'avisar da audiência/perícia', 'informar a decisão', ou enviar um PDF/print de intimação, sentença, ata, laudo ou notificação — mesmo que não cite a palavra 'modelo'."
---

Versão 6.0 — leitura de PDF/PNG, formato de saída com dados extraídos, grupo HTE
e julgamentos detalhados. Mantém integralmente as regras e modelos da versão 5.0.

ESCOPO: comunicações processuais, audiências, defesa/documentos, perícias,
acordos, correspondentes, decisões, execução e comunicações correlatas ao cliente.
Não incluir e-mails internos de RH, folha, financeiro administrativo ou marketing
apenas porque apareçam no fluxograma da Controladoria.

1. OBJETIVO

Esta Skill deve analisar o documento fornecido pelo usuário e elaborar o e-mail
correspondente conforme os modelos cadastrados neste próprio arquivo.

Fluxo obrigatório:

DOCUMENTO → IDENTIFICAÇÃO → EXTRAÇÃO → SELEÇÃO DO MODELO → ADAPTAÇÃO → CONFERÊNCIA → E-MAIL FINAL

Comando padrão:

Faça o e-mail conforme nosso modelo.

A Skill deve selecionar automaticamente o modelo adequado entre os cadastrados.

1-A. LEITURA DE DOCUMENTOS EM PDF E PNG

O documento de origem quase sempre chega como PDF ou imagem (PNG, JPG, print de
tela ou foto). Antes de qualquer coisa, é preciso realmente LER o arquivo — não
supor o conteúdo pelo nome nem pelo que o usuário escreveu na mensagem.

Como ler cada tipo:

PDF com texto selecionável (peças, intimações, sentenças geradas pelo sistema):
abrir o arquivo e ler o conteúdo diretamente. Em PDFs longos, ler as páginas que
contêm o ato relevante (cabeçalho do processo, dispositivo da decisão, data e
horário da audiência/perícia, prazos), sem parar na primeira página se a
informação essencial estiver adiante.

PDF escaneado ou imagem (PNG/JPG, foto de documento, print): o arquivo é uma
imagem. Observar visualmente o documento e transcrever mentalmente os campos
relevantes. Ler com atenção carimbos, assinaturas, datas manuscritas, números de
processo e valores, que costumam ser os pontos mais sujeitos a erro de leitura.

Por que isso importa: um número de processo, uma data de audiência ou um valor
lidos errado geram um e-mail incorreto que vai para o cliente ou para a empresa.
A precisão da leitura é a base de tudo o que vem depois.

Quando um dado essencial estiver ILEGÍVEL, cortado, borrado, sobreposto por
carimbo ou ausente na imagem, NÃO adivinhar e NÃO completar por dedução. Registrar
o ponto no campo "Observações sobre dados não identificados ou inconsistentes"
(ver seção 48) e, se o dado for indispensável ao modelo, pedir confirmação antes
de finalizar.

Se o usuário anexar mais de um documento (por exemplo, intimação + ata + laudo),
identificar qual é o ato que motiva a comunicação e usá-lo como base, aproveitando
os demais apenas como fonte complementar de dados.

Se nenhum arquivo estiver efetivamente anexado, mas o usuário descrever o ato em
texto, trabalhar com o que foi informado e sinalizar que a conferência foi feita
apenas sobre o relato, sem documento à vista.

2. REGRA DE EXISTÊNCIA DO MODELO

Um código somente é considerado cadastrado se houver, neste arquivo:

código e nome;

hipótese de uso;

texto-base ou estrutura operacional expressamente registrada.

NUNCA responder que um modelo listado no MENU não existe sem antes localizar
a seção do respectivo código neste arquivo.

Quando houver texto-base integral, tratar como MODELO TEXTUAL.

Quando o fluxo do escritório determinar o conteúdo da comunicação, mas não
reproduzir um texto integral, tratar como MODELO OPERACIONAL e jamais dizer
que se trata de transcrição literal de modelo oficial.

3. REGRAS ABSOLUTAS DE SEGURANÇA

NUNCA inventar:

número do processo;

nomes das partes;

nome do cliente;

Vara, Tribunal ou órgão julgador;

cidade/UF;

data ou horário;

prazo;

modalidade de audiência/perícia;

endereço ou link;

nome de preposto/testemunha;

nome/OAB de correspondente;

nome de perito/assistente técnico;

valor;

resultado de decisão;

pedidos deferidos/indeferidos;

viabilidade recursal;

existência de anexo;

informação de protocolo;

informação de pagamento;

dados bancários;

trânsito em julgado;

informação de acordo.

Se faltar informação opcional, remover o trecho.

Se faltar informação essencial, pedir confirmação ao usuário.

Não deixar {{CAMPOS}} no e-mail final.

4. ANEXOS

Antes de escrever “segue anexo”, “seguem anexos” ou equivalente, confirmar que:

o arquivo está anexado na conversa; ou

o usuário informou expressamente que será encaminhado.

Se não houver confirmação, omitir a frase.

5. PRAZOS

Distinguir sempre:

prazo judicial: determinado pelo Juízo/Tribunal/autoridade;

prazo interno: estabelecido pelo escritório.

Não transformar prazo interno em judicial.

Não calcular automaticamente D-3, D-6, D-7, D-10, D-15 etc. salvo se o usuário
pedir expressamente o cálculo ou fornecer a data interna já definida.

6. REGRA MÁXIMA DE FIDELIDADE AOS MODELOS

Esta Skill NÃO é uma Skill de redação livre. Ela é uma biblioteca de modelos.

Quando houver modelo cadastrado, a regra é:

COPIAR O MODELO E SUBSTITUIR APENAS OS CAMPOS VARIÁVEIS.

Campos variáveis são, exemplificativamente:

número do processo;

nome das partes;

nome da empresa;

nome do trabalhador;

Vara/Tribunal/órgão;

cidade/UF;

data;

horário;

prazo;

modalidade;

endereço;

link;

nome de preposto;

nome de testemunhas;

nome de perito/assistente;

valores;

documentos específicos quando o próprio modelo trouxer campo variável para isso.

PROIBIÇÕES

É expressamente proibido:

resumir o modelo;

reescrever o modelo com palavras diferentes;

“melhorar” o estilo do modelo;

trocar a ordem dos parágrafos;

trocar a ordem dos itens;

reduzir listas de documentos;

substituir uma lista extensa por “documentos pertinentes”;

fundir dois itens da lista em um só;

criar novos documentos que não existam no modelo;

criar novas orientações jurídicas;

acrescentar explicações legais que não façam parte do modelo;

acrescentar recomendações de antecedência, reunião, proposta de acordo ou providências que não estejam previstas no modelo;

transformar “Audiência Inicial” em “Audiência de Conciliação”, ou o inverso, se o modelo/caso exigir nomenclatura específica;

substituir texto oficial por texto “mais claro”, “mais técnico” ou “mais elegante”;

omitir itens do modelo só porque parecem desnecessários.

REGRA PARA LISTAS

Se o modelo contiver 31 documentos, o e-mail final deverá conter os mesmos 31 documentos,
na mesma ordem e com a mesma redação-base, salvo se o próprio modelo indicar expressamente
que determinado bloco é condicional.

Não é permitido entregar 7, 10 ou 20 itens “representativos”.

REGRA PARA BLOCOS CONDICIONAIS

A Skill NÃO TEM AUTONOMIA PARA EXCLUIR blocos, documentos ou itens do modelo por interpretação própria.

Se o modelo trouxer um bloco com a expressão “se houver”, “quando aplicável”, “se for o caso” ou equivalente, o comportamento padrão é:

manter o bloco no texto, inclusive o título condicional e todos os itens previstos;

não concluir pela inaplicabilidade apenas porque o documento analisado não menciona o tema;

não usar ausência de informação como fundamento para excluir conteúdo do modelo;

somente remover o bloco se o usuário determinar expressamente sua retirada.

Exemplo: se o modelo contém:

IV. SE HOUVER ACIDENTE DE TRABALHO/DOENÇA OCUPACIONAL

e os itens 21 a 31, a Skill deve reproduzir integralmente o título e os itens 21 a 31, ainda que a petição inicial não esteja anexada ou não haja informação suficiente para saber se existe pedido de acidente/doença ocupacional.

A expressão “SE HOUVER” já faz a ressalva necessária. Portanto, não cabe à Skill decidir excluir o bloco.

A mesma regra vale para listas de documentos, anexos condicionais, orientações e demais partes fixas do modelo.

REGRA DE CONFLITO

Se o documento anexado trouxer informação incompatível com o texto fixo do modelo,
NÃO reescrever livremente.

Nesse caso:

preservar o modelo;

substituir apenas o campo variável compatível; e

se houver incompatibilidade real que impeça o uso fiel, avisar ao usuário antes de alterar o texto-base.

REGRA PARA DADOS VARIÁVEIS AUSENTES

Quando um campo variável necessário ao modelo não estiver disponível no documento:

não inventar;

não substituir por informação genérica;

não criar solução alternativa;

não reescrever o modelo para contornar a ausência do dado.

Exemplo: se a notificação menciona um “código de certidão de acesso”, mas o código não consta das páginas fornecidas, a Skill não deve inserir referência genérica a site de validação.

Nessa hipótese, antes do e-mail final, informar de forma objetiva:

Ponto para conferência antes do envio: não foi localizado o código da certidão de acesso mencionado no documento.

Somente após o usuário fornecer o dado ou autorizar expressamente a retirada daquele trecho a Skill poderá finalizar o e-mail.

7. PADRÃO DE REDAÇÃO

Manter o padrão Marques Advogados:

formal;

objetivo;

profissional;

cordial;

direto;

claro;

sem floreios;

sem emojis;

sem explicações típicas de IA;

sem transformar e-mail em petição.

Assinatura padrão, salvo instrução contrária:

Marques Advogados S/S

7. EXTRAÇÃO DE DADOS

Sempre extrair, quando disponíveis:

Dados gerais

processo;

ação;

reclamante/autor;

reclamada/ré;

cliente;

Vara/órgão;

Tribunal;

cidade/UF.

Audiência

tipo;

data;

horário;

modalidade;

endereço;

link;

necessidade de preposto;

testemunhas;

reunião preparatória.

Perícia

objeto/tipo;

perito;

data;

horário;

local;

prazo para quesitos;

prazo para assistente técnico;

documentos exigidos.

Decisão

resultado;

pedidos deferidos/indeferidos;

valor da ação;

valor da condenação;

custas;

depósito;

providências.

Acordo

valor;

parcelas;

vencimentos;

multa;

dados bancários, se constantes;

obrigações;

comprovante.

8. MENU COMPLETO DE MODELOS

AUDIÊNCIAS

AUD-01 — Audiência de Instrução Telepresencial/Híbrida

AUD-02 — Audiência de Conciliação Telepresencial

AUD-03 — Audiência de Conciliação em 2º Grau

AUD-04 — Comunicado Geral de Audiência com Orientações ao Preposto

AUD-05 — Audiência UNA + Testemunhas + Documentos para Defesa

AUD-06 — Audiência de Conciliação + Documentos para Defesa

AUD-07 — Lembrete de Audiência

AUD-08 — Comunicado Detalhado de Audiência de Conciliação

AUD-09 — Agendamento de Reunião Preparatória com Preposto/Testemunhas

DEFESA / DOCUMENTOS / HABILITAÇÃO

DEF-01 — Solicitação Completa de Documentos para Defesa Trabalhista

DEF-02 — Solicitação Simplificada de Documentos

DOC-01 — Solicitação de Documentos de SESMT

DOC-02 — Solicitação de Documento Faltante/Complementar

DOC-03 — Solicitação de Relatórios de Rastreamento e Advertências

HAB-01 — Novo Processo + Audiência + Procuração + Carta de Preposição + Documentos

HAB-02 — Solicitação de Assinatura de Procuração e/ou Carta de Preposição

PERÍCIA

PER-01 — Perícia Designada sem Data Definida

PER-02 — Perícia Técnica + Quesitos + Assistente Técnico

PER-03 — Comunicado de Perícia com Data — sem Assistente de Confiança

PER-04 — Comunicado de Perícia com Data — com Assistente de Confiança

PER-05 — Laudo Pericial Desfavorável — Solicitação de Subsídios Técnicos

PER-06 — Lembrete de Perícia

ACORDOS

ACO-01 — Comunicação de Acordo Judicial Homologado

ACO-02 — Lembrete de Vencimento de Parcela de Acordo

ADVOGADO CORRESPONDENTE

COR-01 — Autorização da Empresa para Contratação

COR-02 — Consulta/Contratação de Correspondente

COR-03 — Confirmação da Contratação

COR-04 — Feedback do Correspondente

COR-05 — Solicitação de Relatório e Documentos ao Correspondente

JULGAMENTOS / DECISÕES

JUL-01 — Cumprimento de Tutela de Urgência

JUL-02 — Alerta de Condenação (com pontos para embargos)

JUL-03 — Improcedência Total

JUL-04 — Grau Recursal — Manutenção da Improcedência

JUL-05 — Grau Recursal — Exclusão da Condenação

JUL-06 — Condenação + Análise de Viabilidade Recursal

HOMOLOGAÇÃO DE TRANSAÇÃO EXTRAJUDICIAL (HTE)

HTE-01 — Protocolo do Pedido de HTE

HTE-02 — Solicitação Inicial de Documentos e Informações

HTE-03 — Solicitação de Documentos Pendentes

HTE-04 — Acordo Homologado (providências)

HTE-05 — Acordo Não Homologado (alternativas)

DECISÃO / CUSTAS / EXECUÇÃO

DEC-01 — Comunicação de Sentença ou Acórdão

CUST-01 — Envio de Custas e/ou Depósito Recursal

EXE-01 — Execução: Guia/Pagamento/Garantia

ENC-01 — Resultado Final/Encerramento

PAG-01 — Comunicação de Crédito/Pagamento ao Cliente

ADMINISTRATIVO / OUTROS

ADM-01 — Notificação Administrativa + Solicitação de Documentos

CP-01 — Carta Precatória + Solicitação de Documentos

PAR-01 — Indicação de Parceiro para Área não Atendida pelo Escritório

9. AUD-01 — AUDIÊNCIA DE INSTRUÇÃO TELEPRESENCIAL/HÍBRIDA

Status: MODELO TEXTUAL

Prezada(o), bom dia!

Informo que a Audiência de Instrução referente ao processo nº {{PROCESSO}}
(Reclamante: {{RECLAMANTE}}) foi designada para o dia {{DATA}}, às
{{HORARIO}}, em modalidade {{MODALIDADE}}.

{{BLOCO_LINK}}

{{BLOCO_TESTEMUNHAS}}

Solicito, ainda, a confirmação do preposto que representará a empresa, a fim
de que possamos agendar, com antecedência, uma reunião preparatória em conjunto
com as testemunhas para alinhamento antes da audiência.

Permaneço à disposição para quaisquer esclarecimentos.

Atenciosamente,
Marques Advogados S/S

BLOCO_LINK

Somente se houver link:

Conforme determinado no despacho, as partes, patronos e testemunhas poderão
participar por videoconferência, por meio do seguinte link:
{{LINK}}

BLOCO_TESTEMUNHAS

Somente se o documento/modelo determinar quantidade:

Saliento que será necessária a indicação de {{QUANTIDADE_TESTEMUNHAS}}
testemunhas que tenham presenciado os fatos em condições semelhantes.

10. AUD-02 — AUDIÊNCIA DE CONCILIAÇÃO TELEPRESENCIAL

Status: MODELO TEXTUAL

Prezados, bom dia!

Comunicamos que foi designada audiência de conciliação, de forma
{{MODALIDADE}}, referente ao processo nº {{PROCESSO}}, no qual a empresa
{{RECLAMADA}} consta como reclamada, tendo como parte autora
{{RECLAMANTE}}, conforme informações abaixo:

Data: {{DATA}}
Horário: {{HORARIO}}
{{BLOCO_LINK}}

Ficamos à disposição para quaisquer esclarecimentos.

Atenciosamente,
Marques Advogados S/S

11. AUD-03 — AUDIÊNCIA DE CONCILIAÇÃO EM 2º GRAU

Status: MODELO TEXTUAL

Prezados, bom dia.

Comunicamos que foi designada audiência de conciliação, em segundo grau de
jurisdição, referente ao processo nº {{PROCESSO}}, no qual a empresa
{{RECLAMADA}} figura como reclamada, tendo como parte autora
{{RECLAMANTE}}.

A audiência ocorrerá de forma {{MODALIDADE}}, conforme informações abaixo:

Data: {{DATA}}
Horário: {{HORARIO}}
{{BLOCO_LINK}}

{{BLOCO_CONTEXTO_RECURSAL}}

A audiência designada tem por objetivo buscar eventual composição entre as
partes.

Permanecemos à disposição para quaisquer esclarecimentos adicionais.

Atenciosamente,
Marques Advogados S/S

BLOCO_CONTEXTO_RECURSAL

Usar somente se confirmado no processo.

12. AUD-04 — COMUNICADO GERAL DE AUDIÊNCIA COM ORIENTAÇÕES

Status: MODELO TEXTUAL

Assunto: COMUNICADO DE AUDIÊNCIA | PROCESSO Nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}}

Prezados(as),

Em relação ao processo nº {{PROCESSO}}, trata-se de reclamação trabalhista
movida por {{RECLAMANTE}} em face de {{RECLAMADA}}.

Informamos que a audiência {{MODALIDADE}} ({{TIPO_AUDIENCIA}}) foi
designada para o dia {{DATA}}, às {{HORARIO}}, a ser realizada
{{LOCAL_OU_LINK}}.

Registre-se que o preposto deverá estar presente na audiência, sob pena de
revelia e confissão quanto à matéria de fato.

{{BLOCO_DOCUMENTOS_AUD}}

Orientações importantes:

{{BLOCO_ORIENTACOES_MODALIDADE}}

É indispensável que o preposto esteja investido de plenos poderes para prestar
informações, esclarecer fatos e firmar acordo, se necessário, conforme orientação
da empresa.

Permaneço à disposição para quaisquer esclarecimentos.

Atenciosamente,
Marques Advogados S/S

BLOCO_DOCUMENTOS_AUD

Somente listar anexos existentes:

Petição Inicial;

Contestação/Defesa;

Notificação da Audiência;

Laudo, se houver;

Carta de Preposição, se houver.

BLOCO_ORIENTACOES_MODALIDADE

Se virtual:

testar link, áudio, vídeo e conexão com antecedência;

ingressar na sala virtual com antecedência conforme orientação aplicável.

Se presencial:

informar orientação de comparecimento/endereço apenas se confirmada.

13. AUD-05 — AUDIÊNCIA UNA + TESTEMUNHAS + DOCUMENTOS PARA DEFESA

Status: MODELO TEXTUAL COMPLETO

Prezados, bom dia!

Em relação ao processo nº {{PROCESSO}}, trata-se de Reclamação Trabalhista
movida por {{RECLAMANTE}} em face de {{RECLAMADA}}.

Informamos que a Audiência UNA ({{MODALIDADE}}) foi agendada para o dia
{{DATA}}, às {{HORARIO}}.

{{BLOCO_LINK}}

{{BLOCO_TESTEMUNHAS}}

Solicito, ainda, a confirmação do preposto que representará a empresa, a fim
de que possamos agendar, com antecedência, uma reunião preparatória em conjunto
com as testemunhas para alinhamento antes da audiência.

Para estruturação da Defesa, solicitamos o envio da documentação abaixo até
{{PRAZO_INTERNO}}:

I. Relato resumido dos fatos e histórico laboral, descrevendo condições de
trabalho, local e demais informações relevantes para a defesa.

II. Padrão de organização

enviar informações nesta cadeia de e-mails;

arquivos com até 9 MB, quando possível;

ordem crescente;

divisão por ano;

documentos separados e renomeados por tipo;

mesma orientação;

legíveis;

em PDF.

III. Documentos para Defesa Trabalhista

Ficha de Registro;

Contrato de Trabalho;

ASO admissional, periódicos e demissional;

CTPS — registro e anotações;

Termo de Devolução de CTPS;

Avisos de Férias;

Recibos de Férias;

Recibos de Salário de todo o contrato, inclusive 13º;

Controles de jornada;

Acordo de prorrogação/compensação de jornada, se houver;

Fichas de EPI;

Normas/Ordens de Serviço assinadas;

Treinamentos;

Advertências/Suspensões;

Extrato FGTS sintético e analítico;

TRCT e comprovante;

Seguro-desemprego, quando aplicável;

Atestados e exames;

ACT/CCT;

outros documentos pertinentes.

IV. Se houver acidente de trabalho/doença ocupacional

REGRA: este bloco deve permanecer no e-mail. Não excluir por ausência de informação no processo.

LTCAT;

PPRA;

PGR;

PCMSO;

PGRTR, se aplicável;

decisões do INSS;

PPP;

DDS;

CAT;

BO, quando houver;

laudos/perícias e documentos relacionados.

{{BLOCO_ANEXOS_DEFESA}}

Ficamos no aguardo do envio dos documentos solicitados.

Desde já agradecemos.

Atenciosamente,
Marques Advogados S/S

14. AUD-06 — AUDIÊNCIA DE CONCILIAÇÃO + DOCUMENTOS PARA DEFESA

Status: MODELO TEXTUAL COMPLETO — FIDELIDADE LITERAL OBRIGATÓRIA

REGRA ESPECÍFICA

Ao utilizar este modelo, é proibido resumir, reduzir, reorganizar ou excluir qualquer item da relação de documentos.

A lista abaixo deverá aparecer integralmente no e-mail final, inclusive o bloco IV e os itens 21 a 31.

A expressão “SE HOUVER ACIDENTE DE TRABALHO/DOENÇA OCUPACIONAL” já funciona como ressalva condicional do próprio modelo. Portanto, a Skill não deve decidir se o bloco é aplicável nem excluí-lo por falta de acesso à petição inicial ou por ausência de menção no documento analisado.

Somente o usuário pode autorizar expressamente a retirada de qualquer bloco ou item.

TEXTO-BASE

Prezados, {{PERIODO}}.

Em relação ao processo nº {{PROCESSO}}, trata-se de Reclamação Trabalhista, movida por {{RECLAMANTE}} em face da {{RECLAMADA}}.

Informamos que, a Audiência de Conciliação ({{MODALIDADE}}) foi agendada para o dia {{DATA}} às {{HORARIO}} horas.

{{BLOCO_LINK}}

Registre-se que, o preposto deverá estar presente na audiência, sob pena de revelia.

Para estruturação da Defesa, solicitamos o envio até o dia {{PRAZO_INTERNO}}

I. Relato resumido dos fatos, e histórico laboral, descrevendo as condições de trabalho, local e todas as informações relevantes e pertinentes para a defesa;

II. Os documentos solicitados devem seguir o seguinte padrão:

Todas as informações pertinentes a este processo deverão ser enviadas neste e-mail para fins de organização.

Os documentos encaminhados devem ter no máximo 9 MB.

Devem estar em ordem crescente.

Os documentos devem estar divididos por ano.

Todos os documentos devem estar separados e renomeados conforme Relação pedida ou divididos por tipo de arquivo.

Todos organizados horizontalmente na mesma orientação.

Todos os documentos devem estar legíveis.

Todos os arquivos devem estar no formato PDF.

III. Relação de Documentos para Defesa Trabalhista:

Ficha de Registro

Contrato de Trabalho

Atestado de Saúde Ocupacional - ASO (admissional, periódico e demissional)

CTPS (Carteira de Trabalho e Previdência Social) - Cópia do registro e anotações

Termo de Devolução de CTPS;

Avisos de Férias;

Recibos de Férias;

Recibos de Pagamento de Salário - mês a mês, de todo o contrato de trabalho inclusive Recibos de Pagto. de 13º Salário;

Controle de Registro de Horário - Manual ou Eletrônico;

Acordo Individual de Prorrogação e Compensação de Jornada de Trabalho (se houver);

Ficha Entrega de EPI - Equipamentos de Proteção Individual;

Normas da Empresa ou OS – Ordens de Serviço (assinadas pela empregada)

Treinamentos (se houver).

Advertências e/ou Suspensões;

Extrato FGTS Sintético e Analítico;

TRCT (Termo de Rescisão do Contrato) com comprovante de pagamento;

Guia SD (seguro desemprego)

Atestados médicos e exames; (se houver)

Acordo ou Convenção Coletiva de Trabalho da categoria (se houver);

Outros documentos que a empresa possuir e julgar pertinentes ao contrato de trabalho do/a reclamante.

IV. SE HOUVER ACIDENTE DE TRABALHO/DOENÇA OCUPACIONAL

LTCAT;

PPRA – Programa de Prevenção de Riscos Ambientais;

PGR – A partir de 2021;

PCMSO - Programa de Controle Médico de Saúde Ocupacional;

PGRTR - PROGRAMA DE GERENCIAMENTO DE RISCOS NO TRABALHO RURAL (Se Fazenda);

Decisões do INSS;

PPP – Perfil Profissiográfico Previdenciário;

DDS – Diálogo Diário de Segurança;

CAT – Comunicação de Acidente de Trabalho;

BO – Boletim de Ocorrência (Quando for o caso);

Perícia (Quando for o caso)

{{BLOCO_ANEXOS_DEFESA}}

Ficamos no aguardo do envio dos documentos solicitados.

Desde já agradecemos.

Atenciosamente,

Marques Advogados S/S

BLOCO_LINK

Somente se houver link no documento:

Segue link/endereço da audiência: {{LINK_OU_ENDERECO}}

BLOCO_ANEXOS_DEFESA

Somente se os arquivos estiverem efetivamente anexados:

Por fim, segue em anexo cópia da inicial e ata/notificação de audiência.

15. AUD-07 — LEMBRETE DE AUDIÊNCIA

Status: MODELO TEXTUAL

Assunto: Audiência Agendada

Prezado(a) {{NOME_CLIENTE}},

Lembramos que a audiência do processo nº {{PROCESSO}}, {{PARTE_A}} x
{{PARTE_B}}, ocorrerá no dia {{DATA}}, às {{HORARIO}}, no formato
{{MODALIDADE}}.

{{BLOCO_LINK_OU_ENDERECO}}

Estamos à disposição para mais informações.

Atenciosamente,
Marques Advogados S/S

16. AUD-08 — COMUNICADO DETALHADO DE AUDIÊNCIA DE CONCILIAÇÃO

Status: MODELO TEXTUAL

Assunto: COMUNICADO DE AUDIÊNCIA | PROCESSO Nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}}

Prezados(as),

Encaminho, para conhecimento e providências, os documentos e informações
referentes à audiência de conciliação agendada no processo em referência:

Processo: {{PROCESSO}}
Vara: {{VARA}}
Reclamante: {{RECLAMANTE}}
Reclamada: {{RECLAMADA}}
Data e horário: {{DATA}}, às {{HORARIO}}
{{BLOCO_LINK_OU_ENDERECO}}

{{BLOCO_DOCUMENTOS_AUD}}

Orientações importantes:

solicitamos leitura prévia dos documentos;

em audiência virtual, testar o link com antecedência;

comunicar imediatamente eventual dificuldade técnica;

ingressar na sala virtual com antecedência;

o preposto deverá possuir poderes para firmar acordo, se necessário.

Permaneço à disposição para quaisquer esclarecimentos.

Atenciosamente,
Marques Advogados S/S

17. AUD-09 — REUNIÃO PREPARATÓRIA

Status: MODELO TEXTUAL

Prezados(as),

A reunião de alinhamento ocorrerá na seguinte data:

Data e horário: {{DATA_REUNIAO}}, às {{HORARIO_REUNIAO}}
Link/endereço: {{LINK_OU_ENDERECO_REUNIAO}}

Solicitamos que preposto e testemunhas estejam pontualmente conectados/presentes,
com a leitura prévia dos documentos enviados e preparados para discutir os pontos
relevantes do processo.

Permaneço à disposição para quaisquer esclarecimentos.

Atenciosamente,
Marques Advogados S/S

18. DEF-01 — SOLICITAÇÃO COMPLETA DE DOCUMENTOS PARA DEFESA

Status: MODELO TEXTUAL

Prezados, {{PERIODO}}.

Em relação ao processo nº {{PROCESSO}}, trata-se de Reclamação Trabalhista
movida por {{RECLAMANTE}} em face de {{RECLAMADA}}.

{{BLOCO_AUDIENCIA}}

Para estruturação da Defesa, solicitamos o envio até {{PRAZO_INTERNO}}:

I. Relato resumido dos fatos e histórico laboral, descrevendo as condições de
trabalho, local e todas as informações relevantes e pertinentes para a defesa.

II. Organização

informações nesta cadeia de e-mails;

arquivos com até 9 MB, quando possível;

ordem crescente;

divisão por ano;

documentos separados e renomeados;

mesma orientação;

legíveis;

PDF.

III. Relação de documentos
Usar integralmente a relação dos itens 1 a 20 do AUD-05.

IV. Se houver acidente/doença ocupacional
Usar integralmente a relação dos itens 21 a 31 do AUD-05.

{{BLOCO_ANEXOS_DEFESA}}

Ficamos no aguardo do envio dos documentos solicitados.

Desde já agradecemos.

Atenciosamente,
Marques Advogados S/S

REGRA CRÍTICA

Ao gerar o e-mail, NÃO escrever “usar relação do AUD-05”.
A Skill deve expandir a lista completa de documentos no e-mail final.

19. DOC-01 — DOCUMENTOS DE SESMT

Status: MODELO TEXTUAL

Prezados, {{PERIODO}}.

Solicitamos, por gentileza, o envio dos seguintes documentos referentes ao
contrato de trabalho de {{TRABALHADOR}}:

PGR;

PCMSO;

LTCAT;

PPRA, quando aplicável.

{{BLOCO_PRAZO}}

Atenciosamente,
Marques Advogados S/S

20. DOC-02 — DOCUMENTO FALTANTE/COMPLEMENTAR

Status: MODELO TEXTUAL

Prezados,

Em relação ao processo nº {{PROCESSO}}, solicito a gentileza de providenciar
{{DOCUMENTO_OU_INFORMACAO_FALTANTE}}, referente ao colaborador
{{TRABALHADOR}}, até {{PRAZO}}.

O envio dessas informações é essencial para a adequada estruturação da defesa e
cumprimento das providências processuais.

Agradecemos pela colaboração.

Atenciosamente,
Marques Advogados S/S

21. DOC-03 — RASTREAMENTO E ADVERTÊNCIAS

Status: MODELO TEXTUAL

Assunto: Rastreamento | {{RECLAMANTE}}

Prezados(as),

Em relação ao processo nº {{PROCESSO}}, solicitamos a gentileza de
providenciar os relatórios de rastreamento e as respectivas mensagens de
advertência relacionadas aos veículos conduzidos pelo motorista
{{MOTORISTA}}, até {{PRAZO}}.

Permanecemos à disposição.

Atenciosamente,
Marques Advogados S/S

22. HAB-01 — NOVO PROCESSO + HABILITAÇÃO + DOCUMENTOS

Status: MODELO TEXTUAL

Prezados, {{PERIODO}}.

Foi distribuído novo processo sob o nº {{PROCESSO}}, ajuizado por
{{RECLAMANTE}} em face de {{RECLAMADA}}.

{{BLOCO_AUDIENCIA}}

Sendo assim, seguem Procuração específica e Carta de Preposição para
assinatura, para fins de habilitação no processo acima citado.

{{BLOCO_AUTOS}}

Solicitamos os seguintes documentos:

{{LISTA_DOCUMENTOS}}

Atenciosamente,
Marques Advogados S/S

23. HAB-02 — ASSINATURA DE PROCURAÇÃO/CARTA DE PREPOSIÇÃO

Status: MODELO TEXTUAL

Assunto: Solicitação de assinatura | Procuração e/ou Carta de Preposição

Prezados(as),

Em relação ao processo nº {{PROCESSO}}, trata-se de {{TIPO_ACAO}}, movida
por {{PARTE_A}} em face de {{PARTE_B}}.

Para viabilizar nossa atuação no processo/audiência, solicitamos, por gentileza,
a assinatura dos seguintes documentos anexos:

{{LISTA_DOCUMENTOS_ASSINATURA}}

Os documentos seguem preenchidos e prontos para assinatura. Caso seja necessária
alguma alteração nos dados, favor nos informar com brevidade.

Após a assinatura, pedimos que os documentos sejam digitalizados e devolvidos
por e-mail até {{DATA_LIMITE}}, para que possamos protocolá-los com
antecedência.

Em caso de dúvidas, estamos à disposição.

Atenciosamente,
Marques Advogados S/S

24. PER-01 — PERÍCIA DESIGNADA SEM DATA

Status: MODELO TEXTUAL

Prezados,

Comunicamos que foi designada diligência pericial no processo trabalhista
movido por {{RECLAMANTE}} em face de {{RECLAMADA}}, para apuração de
{{OBJETO_PERICIA}}.

Até o presente momento, o perito judicial ainda não informou a data de realização.
Tão logo haja definição e comunicação oficial, encaminharemos as informações
pertinentes.

{{BLOCO_ANEXOS_PERICIA}}

Desde já, orientamos que a empresa providencie:

funcionário paradigma disponível e orientado;

documentação de SESMT/segurança do trabalho relativa ao período contratual,
incluindo fichas de EPI, treinamentos e laudos ambientais;

acesso ao ambiente, equipamento, veículo e/ou local objeto da perícia.

Permanecemos à disposição para esclarecimentos e alinhamento com o assistente
técnico indicado.

Atenciosamente,
Marques Advogados S/S

25. PER-02 — PERÍCIA TÉCNICA + QUESITOS + ASSISTENTE

Status: MODELO TEXTUAL

Prezados(as),

Informamos que foi designada perícia técnica no processo em referência,
nomeando o(a) perito(a) judicial {{PERITO}} e concedendo prazo de
{{PRAZO_QUESITOS}} para apresentação de quesitos e indicação de assistente
técnico.

Solicitamos o apoio do assistente técnico da empresa para estruturação dos
quesitos, considerando as alegações constantes da petição inicial.

Orientamos a empresa a:

disponibilizar funcionário paradigma;

separar documentação de SESMT relacionada ao caso, incluindo PPRA/PGR, PCMSO,
LTCAT, fichas de EPI, ASO e treinamentos;

garantir acesso ao ambiente, equipamentos e locais de trabalho em condições
normais de funcionamento.

{{BLOCO_ANEXOS_QUESITOS}}

Pedimos confirmação de recebimento e permanecemos à disposição para alinhamento.

Atenciosamente,
Marques Advogados S/S

26. PER-03 — PERÍCIA COM DATA — SEM ASSISTENTE DE CONFIANÇA

Status: MODELO TEXTUAL

Assunto: COMUNICADO DE PERÍCIA | PROCESSO Nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}}

Prezados,

Processo: {{PROCESSO}}
Autor/Reclamante: {{RECLAMANTE}}
Réu/Reclamada: {{RECLAMADA}}

Foi designada Perícia Judicial para o dia {{DATA}}, às {{HORARIO}}, no
endereço {{LOCAL}}.

{{BLOCO_DOC_PERICIA}}

A empresa deverá apresentar, conforme aplicável:

PGR;

LTCAT;

PPP;

FISPQ/FDS;

fichas de EPI;

demais documentos comprobatórios;

CRLV/NF/CSV, se o objeto envolver tanque suplementar.

Como não há perito/assistente técnico de confiança disponível na região,
solicitamos que a empresa indique profissional de sua preferência para
acompanhamento da perícia, bem como encaminhe os quesitos técnicos que deverão ser
apresentados ao Juízo.

Aguardamos confirmação e envio dos quesitos até {{PRAZO_QUESITOS}}.

Atenciosamente,
Marques Advogados S/S

27. PER-04 — PERÍCIA COM DATA — COM ASSISTENTE DE CONFIANÇA

Status: MODELO TEXTUAL

Assunto: COMUNICADO DE PERÍCIA | PROCESSO Nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}}

Prezados,

Processo: {{PROCESSO}}
Autor/Reclamante: {{RECLAMANTE}}
Réu/Reclamada: {{RECLAMADA}}

Foi designada Perícia Judicial para o dia {{DATA}}, às {{HORARIO}}, no
endereço {{LOCAL}}.

A empresa deverá apresentar, conforme aplicável:

PGR;

LTCAT;

PPP;

FISPQ/FDS;

fichas de EPI;

demais documentos comprobatórios;

CRLV/NF/CSV, se aplicável.

Como há perito/assistente técnico de confiança disponível na região, solicitamos
confirmação da disponibilidade de {{ASSISTENTE_TECNICO}} para acompanhamento
da perícia e auxílio na elaboração dos quesitos.

Aguardamos confirmação e envio dos quesitos até {{PRAZO_QUESITOS}}.

Atenciosamente,
Marques Advogados S/S

28. PER-05 — LAUDO DESFAVORÁVEL — SUBSÍDIOS

Status: MODELO TEXTUAL

Assunto: LAUDO PERICIAL — SOLICITAÇÃO DE SUBSÍDIOS | PROCESSO Nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}}

Prezado(a)s,

Processo: {{PROCESSO}}
Reclamante: {{RECLAMANTE}}
Reclamada: {{RECLAMADA}}

Encaminhamos o laudo pericial para análise e solicitamos verificar se há
fundamentação técnica para apresentação de impugnação, considerando os documentos
enviados e as conclusões do perito.

Solicitamos, se possível, o encaminhamento de argumentos/subsídios técnicos até
{{PRAZO}}, para adoção das medidas dentro do prazo processual.

{{BLOCO_ANEXOS_LAUDO}}

Permanecemos à disposição.

Atenciosamente,
Marques Advogados S/S

29. PER-06 — LEMBRETE DE PERÍCIA

Status: MODELO OPERACIONAL

Prezados(as),

Lembramos que a perícia referente ao processo nº {{PROCESSO}} ocorrerá no dia
{{DATA}}, às {{HORARIO}}, no endereço {{LOCAL}}.

Solicitamos confirmar ciência e disponibilidade para acompanhamento.

{{ORIENTACAO_ESPECIFICA}}

Atenciosamente,
Marques Advogados S/S

30. ACO-01 — ACORDO HOMOLOGADO

Status: MODELO TEXTUAL

Prezados, bom dia.

Conforme audiência realizada em {{DATA_AUDIENCIA}}, informamos que foi firmado
e homologado acordo judicial no processo nº {{PROCESSO}}, nos seguintes
termos:

Valor total do acordo: {{VALOR_TOTAL}};

Forma de pagamento: {{FORMA_PAGAMENTO}};
{{BLOCO_DADOS_BANCARIOS}}

{{BLOCO_QUITACAO}}
{{BLOCO_MULTA}}
{{BLOCO_EXTINCAO}}

Permanecemos acompanhando o cumprimento do acordo e ficamos no aguardo do envio
do comprovante de pagamento após a quitação, para fins de controle e providências
processuais.

Atenciosamente,
Marques Advogados S/S

31. ACO-02 — LEMBRETE DE PARCELA

Status: MODELO TEXTUAL

Processo nº: {{PROCESSO}}
Reclamante: {{RECLAMANTE}}
Reclamada: {{RECLAMADA}}

Prezados,

Informamos que a {{NUMERO_PARCELA}}ª parcela do acordo judicial firmado no
processo em epígrafe possui vencimento em {{VENCIMENTO}}, conforme condições
homologadas.

{{CRONOGRAMA_PARCELAS}}

Solicitamos que o comprovante de pagamento seja encaminhado por esta cadeia de
e-mails, para fins de comprovação judicial e controle interno.

Permanecemos à disposição.

Atenciosamente,
Marques Advogados S/S

32. COR-01 — AUTORIZAÇÃO PARA CONTRATAÇÃO DE CORRESPONDENTE

Status: MODELO TEXTUAL

Assunto: Processo nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}} | Advogado Correspondente

Prezados(as),

Em razão da audiência do processo nº {{PROCESSO}}, designada para
{{DATA}}, às {{HORARIO}}, na cidade de {{CIDADE_UF}}, informamos que
será necessária a contratação de advogado(a) correspondente.

Segue o profissional indicado:

Nome: {{NOME_CORRESPONDENTE}}
OAB: {{OAB}}
Valor da diligência: {{VALOR_DILIGENCIA}}
{{BLOCO_VALOR_PREPOSTO}}

Solicitamos autorização da empresa para contratação, a fim de confirmarmos a
diligência dentro do prazo.

{{BLOCO_PRAZO_AUTORIZACAO}}

Atenciosamente,
Marques Advogados S/S

33. COR-02 — CONSULTA/CONTRATAÇÃO DE CORRESPONDENTE

Status: MODELO TEXTUAL

Prezado(a) Dr(a). {{NOME}},

Em razão da audiência de {{TIPO_AUDIENCIA}} do processo nº {{PROCESSO}},
agendada para {{DATA}}, às {{HORARIO}}, no Foro de {{CIDADE_UF}},
gostaríamos de confirmar sua disponibilidade para atuar como advogado(a)
correspondente.

{{BLOCO_ANEXOS_COR}}

Caso esteja disponível, pedimos o envio de:

valor da diligência;

nome completo;

OAB;

dados bancários/Pix para registro interno.

{{BLOCO_PRAZO_COR}}

Aguardo sua confirmação.

Atenciosamente,
Marques Advogados S/S

34. COR-03 — CONFIRMAÇÃO DA CONTRATAÇÃO

Status: MODELO TEXTUAL

Prezado(a) Dr(a). {{NOME}},

Confirmamos sua atuação como advogado(a) correspondente no processo nº
{{PROCESSO}}, referente à audiência designada.

Data: {{DATA}}
Horário: {{HORARIO}}
Tipo de audiência: {{TIPO_AUDIENCIA}}
Local: {{LOCAL}}
Reclamante: {{RECLAMANTE}}
Reclamada: {{RECLAMADA}}

{{BLOCO_ANEXOS_CONFIRMACAO}}

Atenciosamente,
Marques Advogados S/S

35. COR-04 — FEEDBACK DO CORRESPONDENTE

Status: MODELO TEXTUAL CORRIGIDO

Assunto: FEEDBACK DE CONTRATAÇÃO DE ADVOGADO CORRESPONDENTE | PROCESSO Nº {{PROCESSO}}

Prezados(as),

Em relação ao processo nº {{PROCESSO}}, movido por {{PARTE_A}} em face de
{{PARTE_B}}, encaminho a seguir o resumo da diligência enviado pelo advogado
correspondente:

1. Desempenho/relatório da audiência
{{RELATORIO_AUDIENCIA}}

Quando informado, incluir:

comparecimento das partes;

propostas/tratativas de acordo;

manifestações;

determinações do Juízo;

desempenho do preposto.

2. Financeiro
Valor da diligência: {{VALOR_DILIGENCIA}}

{{BLOCO_RECIBO}}
{{BLOCO_PAGAMENTO}}
{{BLOCO_DOCUMENTOS_COMPROBATORIOS}}

Permaneço à disposição.

Atenciosamente,
Marques Advogados S/S

36. DEC-01 — SENTENÇA OU ACÓRDÃO

Status: MODELO OPERACIONAL

Prezados, {{PERIODO}}.

Em relação ao processo nº {{PROCESSO}}, movido por {{PARTE_A}} em face de
{{PARTE_B}}, informamos que foi proferido(a) {{TIPO_DECISAO}}.

Síntese do resultado:
{{RESUMO_RESULTADO}}

{{BLOCO_PEDIDOS_DEFERIDOS}}
{{BLOCO_PEDIDOS_INDEFERIDOS}}
{{BLOCO_VALORES}}
{{BLOCO_RECURSAL}}
{{BLOCO_GUIAS}}

Atenciosamente,
Marques Advogados S/S

REGRA

A Skill não decide sozinha se é viável recorrer. Só incluir conclusão de
viabilidade recursal se fornecida/validada pelo advogado responsável.

37. CUST-01 — CUSTAS / DEPÓSITO RECURSAL

Status: MODELO OPERACIONAL

Prezados, {{PERIODO}}.

Em relação ao processo nº {{PROCESSO}}, encaminhamos {{TIPO_GUIA}} para
providências quanto ao recolhimento.

Valor: {{VALOR}}
Prazo: {{PRAZO}}

{{CONSEQUENCIA_OU_ORIENTACAO}}

Solicitamos, após o pagamento, o envio do respectivo comprovante para juntada aos
autos.

Atenciosamente,
Marques Advogados S/S

Não criar teto recursal, complementação, abatimento ou CNPJ.

38. EXE-01 — EXECUÇÃO / PAGAMENTO / GARANTIA

Status: MODELO OPERACIONAL

Prezados, {{PERIODO}}.

Em relação ao processo nº {{PROCESSO}}, seguem as informações e providências
necessárias na fase de execução:

{{RESUMO_PROCESSO}}

Valor: {{VALOR}}
Providência: {{PROVIDENCIA}}
Prazo: {{PRAZO}}

{{BLOCO_GUIA}}

Solicitamos retorno/comprovante dentro do prazo informado, para adoção das
providências processuais cabíveis.

Atenciosamente,
Marques Advogados S/S

39. ENC-01 — RESULTADO FINAL / ENCERRAMENTO

Status: MODELO OPERACIONAL

Prezados, {{PERIODO}}.

Em relação ao processo nº {{PROCESSO}}, movido por {{PARTE_A}} em face de
{{PARTE_B}}, comunicamos o resultado final para ciência.

Objeto da ação: {{OBJETO_ACAO}}
Valor da causa: {{VALOR_CAUSA}}
Resultado: {{RESULTADO_FINAL}}
{{BLOCO_CONDENACAO}}
{{BLOCO_PROVEITO_ECONOMICO}}
{{INFORMACOES_RELEVANTES}}

Atenciosamente,
Marques Advogados S/S

40. PAG-01 — COMUNICAÇÃO DE CRÉDITO/PAGAMENTO AO CLIENTE

Status: MODELO TEXTUAL

Prezado(a) {{NOME_CLIENTE}},

Informamos que o pagamento/transferência referente ao processo nº
{{PROCESSO}} foi realizado.

O crédito destinado ao cliente, após os descontos expressamente informados no
caso, corresponde a {{VALOR_CREDITO}}.

{{BLOCO_COMPROVANTE}}

Em caso de dúvidas, estamos à disposição.

Atenciosamente,
Marques Advogados S/S

REGRA

Nunca calcular honorários ou valor líquido sem dados/instrução expressa.

41. ADM-01 — NOTIFICAÇÃO ADMINISTRATIVA + DOCUMENTOS

Status: MODELO OPERACIONAL BASEADO EM TEXTO DO FLUXO

Assunto: Notificação nº {{NUMERO_NOTIFICACAO}} | {{PARTE_A}} x {{PARTE_B}}

Prezados(as),

Trata-se de notificação administrativa expedida por {{ORGAO}} em face da
empresa {{EMPRESA}}.

{{RESUMO_NOTIFICACAO}}

Para análise e estruturação da defesa/recurso administrativo, solicitamos o envio
dos seguintes documentos e informações:

{{LISTA_DOCUMENTOS_ADMIN}}

Prazo: {{PRAZO}}

Orientamos que o envio seja realizado em PDF, legível e organizado.

Permanecemos à disposição para esclarecimentos.

Atenciosamente,
Marques Advogados S/S

42. CP-01 — CARTA PRECATÓRIA + DOCUMENTOS

Status: MODELO TEXTUAL

Assunto: Carta Precatória | Processo nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}}

Prezados(as),

Trata-se de Carta Precatória originada da ação {{ACAO_ORIGEM}}, ajuizada por
{{PARTE_A}} em face de {{PARTE_B}}.

A carta precatória diz respeito ao ato de {{ATO_PRECATORIO}}, que deverá ser
realizado perante o juízo local.

Para estruturação da manifestação, solicitamos os seguintes documentos:

{{LISTA_DOCUMENTOS}}

Orientamos que o envio seja realizado em formato PDF, legível e organizado,
preferencialmente com identificação dos arquivos.

Após o recebimento da documentação e eventuais esclarecimentos, daremos
prosseguimento à elaboração da manifestação.

{{BLOCO_PROCURACAO}}

Permanecemos à disposição para esclarecimentos adicionais.

Atenciosamente,
Marques Advogados S/S

43. PAR-01 — INDICAÇÃO DE PARCEIRO

Status: MODELO TEXTUAL

Olá, {{NOME_CLIENTE}}.

Agradecemos a confiança em nosso trabalho.

No momento, em razão de {{MOTIVO}}, não poderemos assumir esta demanda.

{{BLOCO_INDICACAO_PARCEIRO}}

Permanecemos à disposição e desejamos sucesso na condução do seu caso.

Atenciosamente,
Marques Advogados S/S

BLOCO_INDICACAO_PARCEIRO

Quando houver parceiro autorizado:

Para não deixá-lo(a) sem suporte, indicamos um advogado de nossa confiança,
que atua na área e poderá auxiliá-lo(a): {{CONTATO_PARCEIRO}}.

43-A. DEF-02 — SOLICITAÇÃO SIMPLIFICADA DE DOCUMENTOS

Status: MODELO TEXTUAL

Assunto: Solicitação de documentos | Processo nº {{PROCESSO}} | {{PARTE_A}} x {{PARTE_B}}

Prezados(as),

Em relação ao processo nº {{PROCESSO}}, informamos que a audiência de
{{TIPO_AUDIENCIA}}, na modalidade {{MODALIDADE}}, foi agendada para o dia
{{DATA}}, às {{HORARIO}}.

Endereço ou link da audiência: {{LOCAL_OU_LINK}}

Registre-se que o preposto deverá estar presente na audiência, sob pena de revelia.

Solicitamos o envio dos seguintes documentos:

Procuração, carta de preposição e contrato de honorários devidamente assinados,
quando aplicável;

Documento pessoal e comprovante de endereço, em se tratando de pessoa física;

Contrato social, última alteração contratual e comprovante de endereço, em se
tratando de pessoa jurídica;

{{DOCUMENTOS_TRABALHISTAS_OU_CIVEIS}};

Relato detalhado dos fatos.

Ficamos no aguardo do envio até {{PRAZO_INTERNO}}, sob pena de restar prejudicada
a elaboração da defesa, considerando o prazo fatal para protocolo.

Agradecemos, desde já, pela atenção.

Atenciosamente,
Marques Advogados S/S

43-B. COR-05 — SOLICITAÇÃO DE RELATÓRIO E DOCUMENTOS AO CORRESPONDENTE

Status: MODELO TEXTUAL

Prezado(a) Dr.(a),

Em razão da audiência realizada no processo nº {{PROCESSO}}, solicitamos o
encaminhamento, até {{PRAZO}}, dos seguintes documentos e informações:

Recibo assinado ou nota fiscal referente à diligência;

Relatório resumido da audiência, contendo:

comparecimento das partes;

propostas ou tratativas de acordo, se houver;

manifestações das partes;

determinações do Juízo;

Relato sucinto da atuação do preposto, se aplicável.

O envio é necessário para a finalização dos registros internos e continuidade do
acompanhamento processual.

Aguardamos o retorno.

Atenciosamente,
Marques Advogados S/S

43-C. JUL-01 — CUMPRIMENTO DE TUTELA DE URGÊNCIA

Status: MODELO TEXTUAL

Assunto: Cumprimento de tutela de urgência | Processo nº {{PROCESSO}}

Prezados(as),

Processo nº: {{PROCESSO}}
Valor da causa: R$ {{VALOR_CAUSA}}

Em atenção ao processo em referência, informamos que, na petição inicial, foram
formulados os seguintes pedidos: {{PRINCIPAIS_PEDIDOS}}.

A decisão que analisou o pedido de tutela de urgência deferiu a medida e
determinou o cumprimento, no prazo de {{PRAZO}}, das seguintes obrigações:

{{OBRIGACAO_1}};

{{OBRIGACAO_2}};

{{OBRIGACAO_3}}.

Assim, encaminhamos a decisão anexa para ciência e imediato cumprimento.

Solicitamos o envio dos respectivos comprovantes até {{DATA_LIMITE}}, para adoção
das providências processuais cabíveis.

Atenciosamente,
Marques Advogados S/S

43-D. JUL-02 — ALERTA DE CONDENAÇÃO

Status: MODELO TEXTUAL

Assunto: Alerta de condenação | Processo nº {{PROCESSO}}

Prezados(as),

Processo nº: {{PROCESSO}}

Na petição inicial, foram formulados os seguintes pedidos:

{{LISTA_PEDIDOS}}

A sentença condenou a empresa ao pagamento ou cumprimento das seguintes parcelas e
obrigações:

{{LISTA_CONDENACOES}}

Valor provisório da condenação: R$ {{VALOR_CONDENACAO}}

Os principais fundamentos da decisão foram:

a) {{TEMA_A}}:
{{FUNDAMENTOS_A}}

b) {{TEMA_B}}:
{{FUNDAMENTOS_B}}

c) {{TEMA_C}}:
{{FUNDAMENTOS_C}}

Identificamos, ainda, os seguintes pontos para eventual apresentação de embargos de
declaração:

{{PONTO_1}};

{{PONTO_2}};

{{PONTO_3}}.

Aguardamos a confirmação de ciência.

Atenciosamente,
Marques Advogados S/S

REGRA: os pontos para embargos e os fundamentos só devem constar se extraídos do
documento ou fornecidos/validados pelo advogado responsável. Não inventar omissão,
contradição ou erro material que não conste da decisão.

43-E. JUL-03 — IMPROCEDÊNCIA TOTAL

Status: MODELO TEXTUAL

Assunto: Sentença de improcedência total | Processo nº {{PROCESSO}}

Prezados(as),

Processo nº: {{PROCESSO}}
Valor da causa: R$ {{VALOR_CAUSA}}

Em atenção ao processo em referência, informamos que, na petição inicial, foram
formulados os seguintes pedidos: {{PRINCIPAIS_PEDIDOS}}.

A sentença proferida julgou totalmente improcedentes os pedidos formulados em face
da empresa.

Assim, não há interesse recursal por parte da empresa.

Encaminhamos a sentença para ciência e controle.

Permanecemos à disposição para quaisquer esclarecimentos adicionais que se
fizerem necessários.

Atenciosamente,
Marques Advogados S/S

43-F. JUL-04 — GRAU RECURSAL — MANUTENÇÃO DA IMPROCEDÊNCIA

Status: MODELO TEXTUAL

Assunto: Acórdão — manutenção da improcedência | Processo nº {{PROCESSO}}

Prezados(as),

Processo nº: {{PROCESSO}}
Valor da causa: R$ {{VALOR_CAUSA}}

Em atenção ao processo em referência, informamos que, na petição inicial, foram
formulados os seguintes pedidos: {{PRINCIPAIS_PEDIDOS}}.

A sentença havia julgado totalmente improcedentes os pedidos formulados em face da
empresa.

Após a interposição de recurso pela parte contrária, o acórdão manteve a
improcedência total da ação.

Assim, não há interesse na interposição de recurso pela empresa.

Encaminhamos a decisão para ciência e controle.

Permanecemos à disposição para quaisquer esclarecimentos adicionais que se
fizerem necessários.

Atenciosamente,
Marques Advogados S/S

43-G. JUL-05 — GRAU RECURSAL — EXCLUSÃO DA CONDENAÇÃO

Status: MODELO TEXTUAL

Assunto: Acórdão — exclusão da condenação | Processo nº {{PROCESSO}}

Prezados(as),

Processo nº: {{PROCESSO}}
Valor da causa: R$ {{VALOR_CAUSA}}

Em atenção ao processo em referência, informamos que a sentença havia condenado a
empresa ao pagamento de {{DESCRICAO_CONDENACAO}}.

Após a interposição do recurso cabível, o acórdão excluiu a condenação, tornando a
ação totalmente improcedente.

Assim, não há interesse na interposição de novo recurso pela empresa.

Encaminhamos a decisão para ciência e controle.

Permanecemos à disposição para quaisquer esclarecimentos adicionais que se
fizerem necessários.

Atenciosamente,
Marques Advogados S/S

43-H. JUL-06 — CONDENAÇÃO + ANÁLISE RECURSAL

Status: MODELO TEXTUAL

Assunto: Sentença condenatória e análise recursal | Processo nº {{PROCESSO}}

Prezados(as),

Processo nº: {{PROCESSO}}
Valor da causa: R$ {{VALOR_CAUSA}}

Em atenção ao processo em referência, informamos que, na petição inicial, foram
formulados os seguintes pedidos: {{PRINCIPAIS_PEDIDOS}}.

Na sentença, a empresa foi condenada ao pagamento das seguintes parcelas:

{{PARCELA_1}};

{{PARCELA_2}};

{{PARCELA_3}}.

Esclarecemos que, neste momento processual, o valor da condenação é provisório. O
valor definitivo será estabelecido após o trânsito em julgado e na fase de
liquidação.

Após análise dos autos, entendemos que {{HA_OU_NAO_HA}} fundamento para
interposição de recurso, considerando que:

{{FUNDAMENTO_1}};

{{FUNDAMENTO_2}};

{{FUNDAMENTO_3}}.

Diante desse entendimento, aguardamos orientação quanto à conveniência de
prosseguir ou não com a interposição do recurso cabível até {{DATA_LIMITE}}.

Permanecemos à disposição para quaisquer esclarecimentos adicionais que se
fizerem necessários.

Atenciosamente,
Marques Advogados S/S

REGRA: a conclusão sobre haver ou não fundamento recursal ({{HA_OU_NAO_HA}}) e os
respectivos fundamentos só podem constar se fornecidos/validados pelo advogado
responsável. A Skill não decide sozinha a viabilidade do recurso.

43-I. HTE-01 — PROTOCOLO DO PEDIDO DE HTE

Status: MODELO TEXTUAL

Assunto: Protocolo de HTE | Processo nº {{PROCESSO}}

Prezados(as),

Informamos que foi protocolado o pedido de Homologação de Transação Extrajudicial
— HTE referente ao acordo firmado com o colaborador.

Processo nº: {{PROCESSO}}
Data do protocolo: {{DATA_PROTOCOLO}}
Comprovante/ID do protocolo: {{COMPROVANTE_PROTOCOLO}}.

Orientamos que a empresa apresente essas informações ao colaborador, esclarecendo
que o pedido já foi distribuído e que, neste momento, é necessário aguardar a
análise do Juízo quanto à homologação e/ou eventual designação de audiência.

Ainda não há data de audiência definida. Assim que houver qualquer novidade no
processo, comunicaremos a empresa.

O colaborador também poderá consultar eventuais atualizações diretamente com seu
próprio advogado.

Permanecemos à disposição.

Atenciosamente,
Marques Advogados S/S

43-J. HTE-02 — SOLICITAÇÃO INICIAL DE DOCUMENTOS E INFORMAÇÕES

Status: MODELO TEXTUAL

Assunto: HTE — solicitação de documentos | Processo nº {{PROCESSO}}

Prezados(as),

Considerando o recebimento da demanda, solicitamos o envio dos documentos e
informações abaixo, no prazo de dois dias, para que possamos estruturar a
documentação, avaliar eventual possibilidade de acordo e adotar as providências
processuais cabíveis.

1. Dados do advogado do colaborador:

Nome completo;

Número da OAB;

Telefone;

Endereço;

E-mail.

2. Dados e documentos do colaborador:

Documento de identificação, RG ou CNH, frente e verso;

Comprovante de endereço atualizado;

Procuração assinada pelo empregado ao advogado particular, se houver;

Declaração de hipossuficiência assinada, se houver;

Ficha de registro do empregado;

Extrato analítico do FGTS;

CTPS.

3. Documentos da empresa:

Contrato social atualizado;

Procuração;

Cartão do CNPJ;

Carta de preposição, caso já exista modelo assinado. Caso não exista, favor
informar para que possamos providenciar o modelo.

4. Informações para eventual acordo:

Dossiê completo do caso;

Dados bancários para eventual depósito, com indicação sobre a titularidade da
conta;

Data do último dia de trabalho;

Data da baixa na CTPS;

Informação sobre eventual renúncia à estabilidade, se aplicável;

Valor pretendido para o acordo;

Descrição das parcelas que irão compor o acordo, por exemplo: FGTS, aviso-prévio,
saldo de salário, férias e 13º salário.

Solicitamos, ainda, esclarecimentos sobre os principais fatos relacionados ao
caso, especialmente quanto à existência de documentos, testemunhas, mensagens,
e-mails, atas, registros internos ou outras provas que possam auxiliar na análise.

Permanecemos à disposição.

Atenciosamente,
Marques Advogados S/S

43-K. HTE-03 — SOLICITAÇÃO DE DOCUMENTOS PENDENTES

Status: MODELO TEXTUAL

Assunto: HTE — documentos pendentes | Processo nº {{PROCESSO}}

Prezados(as),

Considerando o recebimento da demanda e a análise preliminar da documentação
encaminhada, identificamos que ainda estão pendentes documentos e informações
necessários para a adequada estruturação do pedido, avaliação de eventual
possibilidade de acordo e adoção das providências processuais cabíveis.

Solicitamos, por gentileza, o envio dos seguintes itens no prazo de dois dias:

Documentos e informações pendentes:

{{ITEM_PENDENTE_1}};

{{ITEM_PENDENTE_2}};

{{ITEM_PENDENTE_3}}.

Caso ainda não tenham sido apresentados, solicitamos esclarecimentos sobre os
principais fatos relacionados ao caso.

Também solicitamos, se aplicável, o envio das seguintes informações para eventual
acordo:

Último dia trabalhado: {{ULTIMO_DIA}};

Valor pretendido para o acordo: R$ {{VALOR_ACORDO}};

Dados bancários para eventual depósito: {{DADOS_BANCARIOS}};

Data da baixa na CTPS: {{DATA_BAIXA}};

Informação sobre eventual renúncia à estabilidade: {{RENUNCIA_ESTABILIDADE}};

Descrição das parcelas que compõem o acordo: {{DESCRICAO_PARCELAS}}.

Permanecemos à disposição.

Atenciosamente,
Marques Advogados S/S

43-L. HTE-04 — ACORDO HOMOLOGADO (PROVIDÊNCIAS)

Status: MODELO TEXTUAL

Assunto: HTE homologado — providências | Processo nº {{PROCESSO}}

Prezados(as),

Conforme sentença homologatória anexa, informamos abaixo as providências que
deverão ser adotadas pela empresa até {{DATA}}, {{DIA_SEMANA}}:

1. Pagamento da parcela acordada, no valor de R$ {{VALOR_PARCELA}}, na conta
bancária indicada no acordo;

2. Recolhimento da multa de 40% do FGTS, no valor de R$ {{VALOR_MULTA_FGTS}},
diretamente na conta vinculada do trabalhador, caso previsto no acordo;

3. Baixa da CTPS Digital, constando como data de desligamento o dia
{{DATA_DESLIGAMENTO}};

4. Cumprimento das demais obrigações previstas no acordo, tais como entrega de
guias, chave de conectividade, TRCT, comprovantes de recolhimento e demais
documentos rescisórios, conforme o caso.

Quanto aos encargos previdenciários e fiscais incidentes, deverão ser realizadas
as respectivas informações no eSocial e cumpridas as demais obrigações acessórias,
observando-se a natureza salarial ou indenizatória das parcelas estabelecida na
petição de acordo e na sentença homologatória.

Solicitamos que, após a realização dos pagamentos e o cumprimento das demais
providências, sejam encaminhados os respectivos comprovantes para juntada aos
autos dentro do prazo informado.

Atenciosamente,
Marques Advogados S/S

43-M. HTE-05 — ACORDO NÃO HOMOLOGADO (ALTERNATIVAS)

Status: MODELO TEXTUAL COMPLETO — FIDELIDADE OBRIGATÓRIA

REGRA ESPECÍFICA: este modelo traz quatro alternativas jurídicas completas. Não
resumir, não excluir alternativas e não escolher por conta própria a medida a ser
adotada. Reproduzir integralmente as quatro alternativas, salvo autorização
expressa do usuário para retirar alguma.

Assunto: HTE não homologado — alternativas | Processo nº {{PROCESSO}}

Prezados(as),

Informamos que foi proferida decisão que não homologou o acordo apresentado pelas
partes.

Diante disso, a empresa deverá avaliar, com cautela, a medida a ser adotada,
conforme as alternativas abaixo.

1. Interposição de recurso contra a decisão

Caso a empresa opte por recorrer da decisão que indeferiu a homologação,
orientamos que, enquanto o processo estiver pendente de julgamento, o colaborador
seja formalmente convocado para retornar ao trabalho.

Nessa hipótese, a empresa deverá realizar o pagamento dos dias efetivamente
trabalhados, se houver, bem como observar eventual período em que o colaborador
permaneça à disposição da empresa, conforme a situação concreta.

Caso o colaborador, mesmo convocado, não compareça ao trabalho e não apresente
justificativa legalmente válida, os dias não trabalhados poderão ser registrados
como faltas injustificadas.

Ressaltamos que não deverá ser aplicada justa causa enquanto o processo estiver
pendente de recurso, devendo a empresa aguardar o desfecho processual ou nova
orientação jurídica específica.

2. Não interposição de recurso e rescisão contratual sem HTE

Caso a empresa opte por não recorrer, deverá avaliar a forma juridicamente
adequada para o encerramento administrativo do contrato.

Havendo estabilidade provisória, deverão ser avaliadas as seguintes alternativas:

a) Homologação do pedido de demissão perante o sindicato, quando aplicável e desde
que exista manifestação válida do colaborador;

b) Rescisão sem justa causa, com indenização do período estabilitário, caso a
empresa opte pelo encerramento contratual mediante pagamento das verbas
rescisórias e da indenização correspondente;

c) Após o encerramento do período de estabilidade, caso o contrato permaneça
ativo, reavaliação da manutenção do colaborador no quadro funcional ou adoção de
outra medida rescisória cabível.

Também deverá ser observado o pagamento dos dias efetivamente trabalhados, se
houver.

Em qualquer dessas hipóteses, o Jurídico deverá ser imediatamente comunicado para
adoção das providências processuais cabíveis, inclusive quanto à eventual
desistência do HTE ou renúncia ao prazo recursal.

3. Não interposição de recurso e manutenção do contrato ativo

Caso a empresa opte por não recorrer e mantenha o contrato ativo, o colaborador
deverá ser formalmente convocado para retornar ao trabalho.

A convocação deverá ser realizada por meio que permita a comprovação do
recebimento, como carta com aviso de recebimento, e-mail, WhatsApp com confirmação
inequívoca de leitura ou resposta, ou outro meio formal utilizado pela empresa.

Se o colaborador, mesmo regularmente convocado, deixar de comparecer ao trabalho
sem apresentar justificativa válida, a empresa deverá registrar as ausências como
faltas injustificadas e manter o controle documental das tentativas de contato.

Após 30 dias consecutivos de ausência injustificada, poderá ser avaliada a
aplicação de justa causa por abandono de emprego, nos termos do artigo 482, alínea
"i", da CLT, mediante prévia análise jurídica.

Antes da adoção da medida, é indispensável verificar se o colaborador ajuizou
reclamação trabalhista com pedido de rescisão indireta ou outro pedido relacionado
ao encerramento do contrato, hipótese que poderá impedir ou tornar arriscada a
aplicação da justa causa.

4. Alternativa judicial

Como alternativa, o trabalhador poderá ajuizar reclamação trabalhista, sendo
possível a realização de acordo em juízo mediante apresentação de petição após o
protocolo da ação.

Nesse caso, o Jurídico deverá ser previamente informado de que se trata de
processo autorizado para composição judicial, a fim de conduzir as tratativas e
formalizar o acordo nos autos.

Diante disso, solicitamos que a empresa informe qual medida pretende adotar, para
que possamos prosseguir com o recurso, renunciar ao prazo recursal, desistir do
HTE ou adotar a providência processual cabível.

Atenciosamente,
Marques Advogados S/S

44. SELEÇÃO AUTOMÁTICA

Quando o usuário disser “Faça o e-mail conforme nosso modelo”:

instrução híbrida/telepresencial → AUD-01

conciliação telepresencial simples → AUD-02

conciliação 2º grau → AUD-03

comunicado geral de audiência/preposto → AUD-04

UNA + testemunhas + defesa → AUD-05

conciliação + defesa → AUD-06

lembrete de audiência → AUD-07

comunicação detalhada de conciliação → AUD-08

reunião preparatória → AUD-09

documentos completos de defesa → DEF-01

documentos simplificados de defesa → DEF-02

SESMT → DOC-01

documento faltante → DOC-02

rastreamento → DOC-03

habilitação/nova ação → HAB-01

assinatura de procuração/preposição → HAB-02

perícia sem data → PER-01

perícia + prazo quesitos → PER-02

perícia com data e sem assistente → PER-03

perícia com data e assistente → PER-04

laudo desfavorável/subsídios → PER-05

lembrete de perícia → PER-06

acordo homologado → ACO-01

parcela do acordo → ACO-02

correspondente → COR-01 a COR-04

solicitação de relatório/recibo ao correspondente após a audiência → COR-05

cumprimento de tutela de urgência (liminar deferida) → JUL-01

sentença condenatória, alerta de condenação, pontos para embargos → JUL-02

sentença de improcedência total → JUL-03

acórdão que manteve a improcedência → JUL-04

acórdão que excluiu a condenação → JUL-05

sentença condenatória com análise de viabilidade recursal → JUL-06

protocolo de HTE → HTE-01

HTE — pedido inicial de documentos → HTE-02

HTE — documentos pendentes → HTE-03

HTE homologado (providências) → HTE-04

HTE não homologado (alternativas) → HTE-05

sentença/acórdão (comunicação genérica) → DEC-01

custas/depósito → CUST-01

execução → EXE-01

encerramento → ENC-01

crédito ao cliente → PAG-01

notificação administrativa → ADM-01

carta precatória → CP-01

indicação de parceiro → PAR-01

44-A. DÚVIDA NA SELEÇÃO E CASOS SEM MODELO

Quando o documento casar claramente com um único modelo, seguir direto e indicar,
de forma breve, qual código foi usado (por exemplo, ao final: "Modelo utilizado:
JUL-02").

Quando houver dúvida real entre dois ou mais modelos, ou quando o documento não
casar claramente com nenhum, NÃO escolher no escuro. Antes de redigir, listar os
códigos candidatos com uma frase sobre a hipótese de uso de cada um e perguntar ao
usuário qual deve ser usado. É melhor uma pergunta objetiva do que um e-mail no
modelo errado.

Quando o ato for legítimo, mas não corresponder a NENHUM dos grupos cadastrados
(por exemplo, uma comunicação de assunto novo), redigir um e-mail seguindo o tom e
a estrutura geral do padrão Marques Advogados — saudação, contextualização breve,
informação principal extraída do documento, providência/prazo, fechamento e
assinatura — e avisar, ao final, que não havia modelo específico cadastrado e que,
se este tipo de comunicação for recorrente, vale a pena cadastrar um novo código.
Mesmo sem modelo, permanecem válidas todas as regras de segurança: não inventar
dados, não afirmar anexos inexistentes e sinalizar o que faltou.

45. REGRAS PARA MODELOS COM LISTAS

Se o modelo trouxer lista de documentos, a Skill deve:

reproduzir todos os itens da lista, integralmente e na mesma ordem;

não selecionar apenas os itens que considerar “aplicáveis”;

não omitir itens por ausência de informação;

não substituir a lista por referência a outro código;

não remover blocos condicionais por conta própria;

não adicionar documentos fora do modelo sem instrução do usuário.

A Skill não exerce juízo de conveniência sobre a lista de documentos do escritório.

46. REGRAS PARA MODELOS COMBINADOS

AUD-05 e AUD-06 são modelos completos por si mesmos.

É proibido responder:

“AUD-06 não possui texto-base cadastrado.”

É proibido pedir ao usuário novamente a lista de documentos prevista no próprio
modelo.

47. MODO CONFERÊNCIA

Se o usuário disser “confira”, “revise” ou “valide”:

comparar silenciosamente:

documento;

modelo;

e-mail produzido.

Conferir:

processo;

partes;

data;

horário;

modalidade;

link/endereço;

prazo;

valores;

anexos;

providência;

modelo escolhido.

Apontar apenas divergências relevantes.

48. SAÍDA PADRÃO

Há dois modos de entrega. O padrão depende do que o usuário pediu.

MODO COMPLETO (padrão quando um documento em PDF/PNG foi analisado)

Entregar, nesta ordem:

Assunto:
[assunto claro e objetivo]

E-mail ajustado:
[texto completo do e-mail, pronto para envio, no modelo selecionado]

Dados extraídos do documento:
Processo:
Partes:
Data:
Prazo:
Valor:
Providência:
Outros dados relevantes:

Observações sobre dados não identificados ou inconsistentes:
[preencher SOMENTE se houver dado ilegível, ausente ou contraditório; caso
contrário, omitir este campo por inteiro]

O bloco "Dados extraídos" serve para o advogado conferir de relance se a leitura
do documento foi correta antes de disparar o e-mail. Preencher cada campo apenas
com o que constar no documento; se um campo não se aplicar ao caso, escrever
"não se aplica"; se deveria constar mas não foi localizado, escrever "não
identificado" e repetir o ponto nas Observações.

MODO SÓ E-MAIL

Quando o usuário pedir expressamente apenas o e-mail ("só o e-mail", "manda só o
texto", "sem o resumo"), entregar somente:

Assunto: ...

e o corpo pronto para envio, sem os blocos de dados extraídos e observações.

EM QUALQUER MODO, dentro do corpo do e-mail, não exibir:

raciocínio;

checklist interno;

explicação sobre seleção de modelo;

placeholders {{CAMPOS}} não preenchidos.

VERIFICAÇÃO OBRIGATÓRIA DE FIDELIDADE

Antes de responder, comparar o e-mail final com o texto-base do modelo selecionado.

Se houver:

frase reescrita sem necessidade;

parágrafo resumido;

item da lista ausente;

ordem alterada;

orientação criada;

documento acrescentado ou removido indevidamente;

corrigir antes de exibir a resposta.

A prioridade é fidelidade ao modelo, e não concisão.

Se houver qualquer item do modelo original ausente no e-mail final sem autorização expressa do usuário, considerar a resposta incorreta e refazer antes de exibir.

49. DADOS INTERNOS E SEGURANÇA

Não reproduzir no e-mail final:

caminhos internos de servidor;

credenciais;

logins;

senhas;

listas internas de contatos;

dados de acesso a sistemas;

informações internas de gestão que não façam parte da comunicação.

50. REGRA FINAL

Quando houver modelo e dados suficientes: elaborar diretamente o e-mail.

Quando faltar dado opcional: omitir.

Quando faltar dado essencial: pedir confirmação.

Quando houver código no MENU: localizar sua seção antes de afirmar que não
existe.