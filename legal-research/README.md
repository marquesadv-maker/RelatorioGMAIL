# Legal Research Local

Ferramenta de busca textual sobre processos trabalhistas, inspirada no *Legal Research* (Data Lawyer Insights), para uso interno do escritório. Roda em `localhost`, sem serviços externos obrigatórios.

## O que faz

| Recurso | Como funciona aqui |
|---|---|
| Busca textual com trechos destacados | SQLite FTS5 (sem acentuação), página a página, com `<mark>` nos termos |
| Termos avançados | todas as palavras, frase exata, ao menos uma, nenhuma, nº/ano da lei |
| Tipos de trecho | entidades extraídas por regras: pessoas, organizações, juízes, varas, tribunais, fundamentos, funções |
| Filtros | documento (tipo, data, fase), localização/órgãos, partes/profissionais, marcadores, processo, valores, situações |
| Jurimetria (N) | agregações sobre o conjunto filtrado (tribunal, fase, status, desfecho, ano, valores médios, duração, taxa de acordo) |
| Favoritos, download, imprimir, compartilhar | menu "⋯" de cada resultado |
| Salvar filtro / Limpar | filtros persistidos no banco |
| Modo I.A. (local) | expansão de sinônimos jurídicos, sem envio de dados a terceiros |

## Fontes de dados reais

0. **DJEN / Comunica PJe (CNJ)**, público e gratuito, sem chave. Publicações oficiais (intimações, despachos, sentenças, editais) com **nomes das partes, advogados e texto integral**. É a fonte da busca por nome na tela principal: ao pesquisar um nome sem resultado local, o sistema consulta o DJEN, importa as publicações e exibe os trechos.
   - Portal: https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/
   - Swagger: https://comunicaapi.pje.jus.br/swagger/index.html
   - Limites: controle por IP (HTTP 429 → o conector aguarda 1 minuto), até 10.000 resultados por pesquisa.
1. **DataJud (CNJ)** — API Pública, gratuita. Traz classe, assuntos, órgão julgador, grau e movimentações de qualquer processo trabalhista (TRT-1 a TRT-24 e TST). Não traz partes, advogados, valores nem inteiro teor, e omite processos sigilosos.
   - Documentação: https://datajud-wiki.cnj.jus.br/api-publica/
   - Chave pública (rotativa): https://datajud-wiki.cnj.jus.br/api-publica/acesso/ → copie para `DATAJUD_API_KEY` no `.env`.
   - Códigos de classe/assunto (TPU): https://www.cnj.jus.br/sgt/consulta_publica_classes.php
2. **Documentos do escritório** — PDFs/DOCX/TXT das pastas dos processos (inteiro teor pesquisável). Coloque um subdiretório por processo em `data/documentos/` (o número CNJ pode estar no nome da pasta, do arquivo ou no texto). Um `processo.json` opcional por pasta informa partes, advogados, valores e situações (ver `docs/processo.exemplo.json`).
3. **Provedores privados (opcionais)** — Judit ou Escavador, para busca por nome, CPF, CNPJ e OAB. Exigem contrato e chave no `.env`. Os caminhos dos endpoints estão em `app/fontes/privadas.py` e devem ser conferidos na documentação vigente de cada provedor antes do uso em produção.

## Desempenho e dinamismo

- **Índice FTS5 com prefixos** (`prefix='2 3 4'`), `PRAGMA` de cache/mmap e otimização do índice após gravações.
- **Cache de consultas** em memória (invalidado automaticamente a cada gravação no índice).
- **Facetas e jurimetria** usam uma única passagem pelo FTS por requisição (tabela temporária de acertos).
- **Extração de PDF/DOCX em paralelo** (processos), gravação em lote e commits parciais.
- **DataJud**: consultas por número em paralelo; varredura paginada gravada em lotes conforme chega.
- **Tarefas em segundo plano** (`/api/tarefas`) com barra de progresso na interface; o índice atualiza sozinho ao concluir.
- **Interface**: busca enquanto digita (com cancelamento de requisições), filtros aplicados ao mudar, rolagem infinita, atalhos (`/` foca a busca, `Esc` fecha, `↑ ↓ Enter` navegam), tempo de resposta exibido.

Referência medida localmente com 3.000 processos importados: busca ~9 ms no servidor (0,2 ms em cache), facetas ~30 ms, jurimetria ~40 ms.

## Instalação e execução (localhost)

```bash
cd legal-research
python -m venv .venv && .venv\Scripts\activate        # Windows
# source .venv/bin/activate                             # Linux/macOS
pip install -r requirements.txt
copy .env.exemplo .env                                  # preencha DATAJUD_API_KEY
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Abra **http://localhost:8765**. No Windows, `run.bat` faz tudo isso.

## API (compatível em espírito com a ferramenta de referência)

| Método | Rota | Função |
|---|---|---|
| POST | `/api/documento?limite=30&deslocamento=0` | resultados paginados |
| POST | `/api/documento/obterMenuLateral` | facetas |
| POST | `/api/documento/obterQuantidadeDeProcessos` | contagens |
| POST | `/api/jurimetria` | agregações do conjunto filtrado |
| GET | `/api/autocomplete/Trabalhista/{parte,advogado,magistrado,orgaoJulgador,processo,...}` | sugestões |
| GET | `/api/documento/{id}` · `/api/documento/{id}/arquivo` · `/api/processo/{id}` | detalhe, arquivo original, capa |
| POST | `/api/fontes/datajud/numero` · `/api/fontes/datajud/filtro` | importar do DataJud |
| POST | `/api/fontes/djen` · `/api/busca-online` | importar publicações do DJEN (segundo plano / síncrono) |
| POST | `/api/fontes/pessoa` | importar de provedor privado |
| POST | `/api/indexar` · `/api/upload` | indexar pasta / enviar arquivos (tarefa em segundo plano) |
| GET | `/api/tarefas` · `/api/tarefas/{id}` | progresso das tarefas |
| POST | `/api/home/{total,ativosPorUf,valorMedioCausas,duracaoMedia,porFase,porTribunal}` | painel |

Corpo das buscas: `{"filtroGeral": {"conteudo": {...}}, "filtroPesquisaTextual": {"conteudo": {"trecho": "...", "tiposEntidades": [...], "buscaDocumentosAvancada": {...}, "tipoOrdenacao": "relevancia", "periodoDataDocumento": {...}}}}`.

## Identidade visual

Interface com a identidade da Marques Advogados: azul-marinho `#0C0E34`, dourado `#8C5818`, areia `#D9C6A3`, creme `#F2E5BD`, fundo nude `#F8F3ED`, fonte Quicksand (equivalente legível à Galano Grotesque do manual) e símbolo "M" no cabeçalho. Tokens em `app/static/style.css`.

## LGPD e sigilo

- CPFs são mascarados no índice e nos metadados; o arquivo original permanece apenas na pasta do escritório.
- A busca por pessoa em provedores privados envolve dados pessoais: defina a finalidade (defesa em processo, diligência) e evite reproduzir nomes de terceiros em relatórios sem necessidade.
- O banco local (`data/legal_research.db`), o `.env` e os documentos não são versionados.

## Testes

```bash
python -m pytest -q tests
```
