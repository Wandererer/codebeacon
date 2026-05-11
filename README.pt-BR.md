<!-- translation-of: README.md | based-on-commit: initial -->

<p align="center">
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.md"><img src="https://img.shields.io/badge/lang-English-blue" alt="English"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.ko.md"><img src="https://img.shields.io/badge/lang-한국어-red" alt="Korean"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.ja.md"><img src="https://img.shields.io/badge/lang-日本語-green" alt="Japanese"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.zh-CN.md"><img src="https://img.shields.io/badge/lang-简体中文-orange" alt="Chinese"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.es.md"><img src="https://img.shields.io/badge/lang-Español-yellow" alt="Spanish"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.fr.md"><img src="https://img.shields.io/badge/lang-Français-blueviolet" alt="French"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.de.md"><img src="https://img.shields.io/badge/lang-Deutsch-lightgrey" alt="German"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.pt-BR.md"><img src="https://img.shields.io/badge/lang-Português_(BR)-brightgreen" alt="Portuguese (Brazil)"></a>
</p>

<h1 align="center">codebeacon</h1>

<p align="center">
  Análise AST de código-fonte e geração de contexto para IA — knowledge graph multi-framework unificado
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## Por que codebeacon?

Toda vez que você abre uma nova sessão de codificação com IA, o assistente começa do zero. Ele não conhece suas rotas, sua camada de serviços, seu modelo de entidades nem como seus microsserviços se comunicam. Você gasta o início de cada sessão colando arquivos, explicando a estrutura e reconstruindo o contexto.

As ferramentas existentes resolvem isso apenas parcialmente. Analisadores de rotas mapeiam seus controladores, mas ignoram dependências de serviços. Ferramentas de knowledge graph capturam relacionamentos, mas ignoram a superfície da API. O resultado: executar as duas ferramentas, unir as saídas manualmente e repetir tudo a cada mudança no código.

**codebeacon unifica as duas abordagens em um único CLI.** Um comando escaneia toda a base de código com análise AST do tree-sitter, resolve injeção de dependências entre arquivos, detecta clusters de comunidade na arquitetura e escreve um mapa de contexto pronto para uso diretamente em `CLAUDE.md`, `.cursorrules` e `AGENTS.md`.

---

## Principais funcionalidades

- **Pipeline unificado** — análise de rotas/controladores + knowledge graph em uma só ferramenta, sem junção manual
- **27 frameworks, 9 linguagens** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor
- **Baseado em tree-sitter** — análise AST estrutural, não regex; gramáticas de linguagem incluídas por padrão
- **Resolução DI em 2 passos** — Pass 1 extrai nós AST locais; Pass 2 constrói uma tabela de símbolos global e resolve mapeamentos Interface → Implementation
- **Arquitetura Wave merge** — arquivos processados em chunks paralelos e mesclados globalmente; lida com grandes monorepos sem problemas de memória
- **Múltiplos formatos de saída** — knowledge graph JSON, wiki Markdown, Obsidian Vault, mapas de contexto para IA, servidor MCP, HTML interativo
- **Exploração visual** — `beacon.html` (árvore colapsável D3) e `callflow.html` (diagramas Mermaid de arquitetura agrupados por comunidade) regerados a cada scan
- **Detecção de comunidades** — clustering Leiden/Louvain revela as fronteiras arquiteturais reais
- **Cache incremental** — SHA-256 + fast path por mtime/size; mudanças apenas de mtime causadas por ferramentas de sync (Obsidian/iCloud/Nextcloud) nunca disparam re-extração desnecessária
- **Promoção de confiança** — arestas `calls` entre arquivos sobem de INFERRED para EXTRACTED automaticamente quando um import explícito prova o binding
- **Gravações seguras** — beacon.json tem shrink guard (uma execução parcial nunca sobrescreve um grafo completo) e estampa `built_at_commit`, então REPORT.md sinaliza saídas stale contra o HEAD atual
- **Amigável a múltiplos desenvolvedores** — `codebeacon hook install` registra um git merge driver para `beacon.json` e um hook post-commit de rebuild incremental, assim dois devs escaneando o mesmo branch nunca produzem conflitos de merge no grafo
- **Saída endurecida** — frontmatter YAML e labels MCP são sanitizados: U+2028/U+2029, controles C0 e marcas bidi são removidos antes de chegar ao Obsidian, Cursor ou ao agente
- **`.codebeaconignore` estilo gitignore** — last-match-wins com negação `!`, padrões de diretório (`build/`), padrões ancorados (`/secrets.txt`), regras de espaço final
- **Zero configuração** — detecta frameworks e linguagens automaticamente; gera `codebeacon.yaml` para execuções futuras
- **Modo Deep Dive** — `--deep-dive` gera `.codebeacon/` + `CLAUDE.md` próprios para cada sub-projeto; executar o comando de atualização de **qualquer** sub-projeto sincroniza automaticamente todos os projetos do workspace
- **Auto-redescoberta do workspace** — a cada `scan`/`sync`, o codebeacon re-escaneia o workspace e adiciona automaticamente os novos projetos ao `codebeacon.yaml` antes da extração, evitando que sub-projetos recém-criados sejam silenciosamente ignorados; use `--no-rediscover` para manter uma configuração yaml curada manualmente
- **Enriquecimento semântico estilo Graphify** — após a extração AST, o skill despacha um subagente paralelo por chunk para emitir fragmentos completos de knowledge graph `{nodes, edges, hyperedges}` com 8 tipos de relação (`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`) e confiança EXTRACTED/INFERRED/AMBIGUOUS; no Claude Code o subagente roda um nível abaixo do modelo host (Opus→Sonnet, Sonnet→Haiku) para manter o custo proporcional ao tamanho do corpus. O AST é dono dos nós de código; o LLM só pode contribuir nós `concept`/`document`/`paper`. Os arquivos 0.3.x existentes são replayados sob o novo esquema sem alteração

---

## Início rápido

```bash
pip install codebeacon

codebeacon scan .
```

O codebeacon detecta os tipos de projeto, extrai rotas/serviços/entidades/componentes, constrói o knowledge graph e escreve tudo em `.codebeacon/`.

Para um workspace multi-projeto:

```bash
codebeacon scan /caminho/workspace   # detecta todos os projetos, gera codebeacon.yaml
codebeacon sync                      # execuções seguintes via configuração
```

---

## Frameworks suportados

| Linguagem | Frameworks |
|-----------|-----------|
| Java / Kotlin | Spring Boot, Ktor |
| Python | Django, FastAPI, Flask |
| JavaScript / TypeScript | Express, Fastify, Koa, NestJS, React, Next.js, Vue, Nuxt, Angular, SvelteKit |
| Go | Gin, Echo, Fiber |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web, Axum, Tauri, Rocket, Warp |
| C# | ASP.NET Core |
| Swift | Vapor |

---

## Arquitetura

O codebeacon executa um pipeline de extração em 2 passos:

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         AST local          Tabela de    Filtro      HTTP API
                         por chunk          símbolos     artefatos   DB compartilhada
                         (Pass 1)           (Pass 2)
```

**Pass 1 — Extração Wave:** Arquivos processados em chunks paralelos via `ThreadPoolExecutor`. Cada arquivo passa por cinco extratores: rotas, serviços, entidades, componentes e dependências.

**Pass 2 — Construção do grafo:** Fusão de todos os resultados Wave. Uma tabela de símbolos global resolve referências de injeção de dependência não resolvidas — mapeamentos Interface→Implementation que ferramentas de passo único perdem.

---

## Estrutura de saída

Após o scan, os arquivos de mapa de contexto são atualizados na raiz do projeto (conteúdo do usuário é preservado) e o knowledge graph em `.codebeacon/`:

```
project-root/
  CLAUDE.md              ← mapa de contexto IA (bloco codebeacon mesclado; conteúdo do usuário mantido)
  .cursorrules           ← contexto do Cursor IDE (mesma estratégia de mesclagem)
  AGENTS.md              ← contexto OpenAI Agents / Codex (mesma estratégia de mesclagem)
  .codebeacon/
    beacon.json          ← knowledge graph completo; embute `meta.built_at_commit`
    beacon.html          ← visualizador de árvore colapsável D3 (abrir em qualquer navegador)
    callflow.html        ← diagramas Mermaid de call-flow agrupados por comunidade
    REPORT.md            ← nós deus, conexões surpreendentes, arquivos hub, frescor
    wiki/
      index.md
      overview.md
      routes.md
      <project>/
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian Vault (uma nota por nó do grafo)
```

### Modo Deep Dive

Com `--deep-dive`, cada sub-projeto recebe seu próprio `.codebeacon/` + `CLAUDE.md`. O Claude Code carrega os arquivos `CLAUDE.md` de forma hierárquica — uma sessão em `api-server/` carrega tanto a visão geral do workspace quanto os detalhes específicos do projeto.

O ponto-chave: um comando de atualização de **qualquer sub-projeto** sincroniza todo o workspace automaticamente:

```bash
# Primeiro scan deep dive
codebeacon scan /workspace --deep-dive

# Depois, de qualquer sub-projeto — encontra a config pai e atualiza TODOS os projetos
cd /workspace/api-server
codebeacon scan . --update
```

Estrutura de saída:
```
workspace/
  CLAUDE.md                   ← combinado (todos os projetos)
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← grafo combinado
  api-server/
    CLAUDE.md                 ← apenas api-server
    .codebeacon/
  frontend/
    CLAUDE.md                 ← apenas frontend
    .codebeacon/
```

## Exploração visual

Cada scan escreve dois arquivos HTML autocontidos ao lado de `beacon.json`:

```
.codebeacon/beacon.html      # árvore colapsável D3 v7 — abra em qualquer navegador
.codebeacon/callflow.html    # diagramas Mermaid de arquitetura, um por comunidade
```

Sem build, sem servidor estático, sem copy-paste. Abra o arquivo, clique para expandir projetos → tipos → nós; passe o mouse para ver paths e degree. `callflow.html` agrupa o grafo por comunidade e renderiza cada uma como flowchart Mermaid, com as arestas saindo entre comunidades em uma tabela dobrada.

---

## Fluxo multi-desenvolvedor

Dois devs rodando `codebeacon scan` no mesmo branch produzem `beacon.json` ligeiramente diferentes — historicamente um hotspot de conflitos de merge. `codebeacon hook install` resolve:

```bash
codebeacon hook install            # na raiz do repo
```

Registra:

- um **git merge driver** que une dois `beacon.json` em um só (nós deduplicados por ID, arestas deduplicadas por `(source, target, relation)`),
- uma entrada `.gitattributes` apontando `*beacon.json` para o driver,
- um **hook post-commit** que roda `codebeacon scan . --update` em background, para que o grafo nunca fique atrás dos commits. Saída em `~/.cache/codebeacon-rebuild.log`.

O merge driver sempre sai com 0 — uma regeneração de grafo nunca bloqueia um merge real.

---

## Garantias de segurança

Invariantes que o writer impõe a cada scan bem-sucedido:

| Guard | O que previne |
|---|---|
| **Shrink guard** | Uma extração parcial falha ou uma execução interrompida nunca pode sobrescrever um `beacon.json` completo e maior. Bypass via `force=True` na API. |
| **Gravação atômica** | `beacon.json` é gravado via `os.replace`, então o arquivo está completo ou intocado — nunca pela metade. |
| **Estampa `built_at_commit`** | `beacon.json` embute `meta.built_at_commit` (SHA completo) e `REPORT.md` mostra o SHA curto. Se HEAD avançou, o relatório marca o grafo como `⚠ stale` com uma dica de uma linha. |
| **Hardening de frontmatter / labels** | Valores YAML em single-quoted escapam U+2028, U+2029, tab e controles C0; saída MCP passa todos os labels pelo mesmo sanitizer. Um identificador malicioso no código-fonte não consegue quebrar o parser YAML do Obsidian nem injetar sequências de controle no contexto de um agente LLM. |

---

## Configuração

Execute `codebeacon init` para gerar `codebeacon.yaml`, ou crie manualmente:

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # opcional: detectado automaticamente

  - name: frontend
    path: ./frontend
    type: react

output:
  dir: .codebeacon
  wiki: true
  obsidian: true
  context_map:
    targets: [CLAUDE.md, .cursorrules, AGENTS.md]

wave:
  auto: true
  chunk_size: 300              # arquivos por chunk
  max_parallel: 5              # threads paralelas

semantic:
  enabled: false               # apenas extração de comentários estruturados;
                               # sobrescrever com --semantic. O AI-semântico NÃO mora aqui:
                               # é acionado pelo skill /codebeacon (= o agente em execução).

deep_dive: false               # definir true para saída por projeto
```

### .codebeaconignore

Coloque um arquivo `.codebeaconignore` na raiz do projeto para excluir diretórios ou arquivos do scan. Semântica idêntica ao `.gitignore` — last-match-wins com negação `!`, padrões ancorados (`/foo`), padrões somente-diretório (`build/`), comentários:

```
# .codebeaconignore

# diretórios
build/
generated/
fixtures/

# ancorado apenas à raiz
/scripts/local-only.ts

# padrões glob
*.gen.ts
**/snapshots/**

# re-incluir um arquivo mesmo com build/ ignorado
!build/manifest.ts
```

`!pattern` re-inclui um caminho previamente ignorado; regras posteriores sobrescrevem as anteriores. O walker poda diretórios cujo nome bate com o conjunto de regras, mas adia a poda quando alguma regra de negação puder re-incluir um arquivo aninhado.

---

## Integração com IA

### Skill do Claude Code (`/codebeacon`)

Instale o codebeacon como um comando slash do Claude Code:

```bash
pip install codebeacon
codebeacon install
```

Isso copia o `SKILL.md` para `~/.claude/skills/codebeacon/` e registra o trigger `/codebeacon` em `~/.claude/CLAUDE.md`. Reinicie sua sessão do Claude Code e digite `/codebeacon` para escanear o diretório atual.

```
/codebeacon                  # escanear diretório atual
/codebeacon /path/to/project # escanear um caminho específico
/codebeacon sync             # re-escanear a partir do codebeacon.yaml
```

### Servidor MCP

Execute o codebeacon como um servidor MCP persistente para que qualquer cliente compatível com MCP possa consultar o grafo de conhecimento diretamente.

**Passo 1 — escanear o projeto:**
```bash
codebeacon scan .
```

**Passo 2 — adicionar à configuração do cliente MCP:**

**Claude Code** (`.claude.json` na raiz do projeto ou `~/.claude.json` globalmente):
```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "codebeacon",
      "args": ["serve"]
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "codebeacon",
      "args": ["serve", "--dir", "/path/to/.codebeacon"]
    }
  }
}
```

**Ferramentas MCP disponíveis após a conexão:**

| Ferramenta | Descrição |
|------------|-----------|
| `beacon_wiki_index` | Visão geral global do projeto (rotas, serviços, entidades) |
| `beacon_wiki_article` | Ler um artigo do wiki por caminho |
| `beacon_query` | Buscar nós por substring de rótulo |
| `beacon_path` | Caminho de dependência mais curto entre dois nós |
| `beacon_blast_radius` | Chamadores upstream e nós afetados downstream |
| `beacon_routes` | Listar todas as rotas HTTP (filtrável por projeto) |
| `beacon_services` | Listar todos os serviços/classes (filtrável por projeto) |

---

## Opções de instalação

```bash
pip install codebeacon              # gramáticas de linguagem incluídas
pip install codebeacon[cluster]     # + detecção de comunidades Leiden (graspologic)
pip install --upgrade codebeacon    # atualizar para a versão mais recente com todas as dependências
```

Os parsers de Java, Kotlin, Python, JavaScript, TypeScript, Go, Ruby, PHP, C#, Rust, Swift, HTML e Svelte são incluídos por padrão.

---

## Referência CLI

```bash
codebeacon scan .                         # diretório atual
codebeacon scan . --update                # incremental: apenas arquivos alterados
codebeacon scan . --wiki-only             # pular re-extração, regenerar wiki/obsidian/contexto a partir do beacon.json existente
codebeacon scan . --semantic              # extração de referências em comentários estruturados (Javadoc/JSDoc/docstring)
codebeacon scan . --list-only             # apenas detectar frameworks
codebeacon scan /workspace --deep-dive    # saída por projeto + workspace combinado

codebeacon init [caminho]                 # gerar codebeacon.yaml
codebeacon sync                           # executar a partir do codebeacon.yaml (adiciona novos projetos do workspace automaticamente)
codebeacon sync --no-rediscover           # não adicionar novos projetos automaticamente (modo yaml curado à mão)

codebeacon query <termo> [--dir .codebeacon] [--limit N]   # buscar nós por substring do label
codebeacon path <origem> <destino> [--dir .codebeacon]     # caminho de dependências mais curto

# Suporte multi-desenvolvedor (git plumbing)
codebeacon hook install [path]            # instala merge driver + hook post-commit incremental
codebeacon merge-driver <base> <cur> <other>  # chamado pelo git após `hook install`; union-merge de beacon.json

# Enriquecimento AI-semântico (LLM executado pelo agente, codebeacon faz a contabilidade)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # reaplica .codebeacon/semantic/original/*.jsonl no
                                          # beacon.json novo + remove entradas apontando para nós
                                          # que sumiram, então escreve tarefas em
                                          # .codebeacon/semantic/pending/chunk_NNN.jsonl
                                          # (--chunk-size por chunk, padrão 10). O task_id inclui
                                          # hash de conteúdo: se o arquivo muda, é reemitido.
codebeacon semantic-apply   [--dir .codebeacon]
                                          # para cada .codebeacon/semantic/results/chunk_NNN.jsonl
                                          # escrito pelo agente, mescla as arestas INFERRED
                                          # references no beacon.json e MOVE o chunk pendente para
                                          # .codebeacon/semantic/original/chunk_NNN.jsonl (arquivo
                                          # durável). Apaga os results e regenera tudo.

codebeacon serve [--dir .codebeacon]      # servidor MCP (stdio)
codebeacon install                        # instalar skill do Claude Code
codebeacon upgrade                        # pip upgrade + atualizar ~/.claude/skills/codebeacon/SKILL.md
                                          # (use `--force` se instalado em modo editable)
```

---

## Enriquecimento AI-semântico (via skill `/codebeacon`)

A análise tree-sitter encontra o que está na AST. **AI-semântico** encontra o que só vive nos *comentários* — o `@see UserService` em uma Javadoc, o `:class:`OrderRepository`` em uma docstring Python, as referências contratuais documentadas ao lado de um handler de rota. O codebeacon entrega duas camadas para isso:

| Camada | Flag | Custo | O que captura |
|---|---|---|---|
| Análise de comentários estruturados | `--semantic` | grátis, local, sem LLM | Javadoc `@see` / `{@link}`, JSDoc `@see` / tipos de `@param`, Python `:class:` / `:func:` / `See Also` |
| **AI-semântico** | automático no skill `/codebeacon` | usa o modelo atual do agente — **sem chave de API extra** | referências de classe/tipo/serviço que a regex não pega (texto livre, menções indiretas, hints só de tipo) |

O CLI em si **nunca chama um LLM**. A camada AI-semântica pertence intencionalmente ao **agente em execução** dentro do skill `/codebeacon` do Claude Code — assim a escolha de modelo do usuário (Opus / Sonnet / Haiku / qualquer um) é respeitada e o codebeacon nunca precisa de `ANTHROPIC_API_KEY` nem de qualquer configuração de nuvem.

### Como roda

Quando você invoca `/codebeacon` no Claude Code:

1. `scan` / `sync` constrói `beacon.json` a partir da AST (sem chamada LLM).
2. `codebeacon semantic-prepare` reidrata o arquivo em `.codebeacon/semantic/original/*.jsonl` no grafo novo e **remove** as entradas cujo nó de origem não existe mais. Em seguida grava as novas tarefas em `.codebeacon/semantic/pending/chunk_NNN.jsonl` (≤ `--chunk-size` por arquivo, padrão 10). A numeração de chunks continua de onde o arquivo durável parou — nunca colide.
3. O skill processa os chunks pendentes **um por vez**. Para cada `pending/chunk_NNN.jsonl`, o agente (com o modelo da sessão atual) lê o `excerpt` de cada tarefa e escreve um `semantic/results/chunk_NNN.jsonl` de mesmo nome.
4. `codebeacon semantic-apply` mescla os resultados como arestas `INFERRED references` em `beacon.json` e **move** cada `pending/chunk_NNN.jsonl` finalizado para **`semantic/original/chunk_NNN.jsonl`** (com as arestas aplicadas para auditoria). Os arquivos de results são removidos; wiki + obsidian + mapa de contexto são regenerados.
5. Na próxima execução: `semantic-prepare` lê cada chunk em `original/`, aplica suas arestas no grafo recém-construído (as inferências históricas são preservadas) e pula qualquer tarefa cujo `task_id` já esteja arquivado. `task_id` = `SHA1(file_path | node_id | excerpt_hash[:8])` — se o conteúdo semântico de um arquivo mudar, ele recebe um id novo e é reanalisado.

Enriquecimento incremental e idempotente: o agente nunca reanalisa a mesma combinação (arquivo, conteúdo) duas vezes, o sinal AI acumulado sobrevive a cada nova varredura e os chunks mantêm pequeno o conjunto de trabalho do agente.

### Uso direto do CLI

Se você não passa pelo skill (ex.: CI), pode rodar os mesmos dois comandos manualmente e fornecer seus próprios `results/chunk_NNN.jsonl`:

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# Já existem .codebeacon/semantic/pending/chunk_001.jsonl ...
# Para cada chunk pending, escreva um results/chunk_NNN.jsonl de mesmo nome.
# Cada linha:
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### Desligar

Passe `--no-semantic` (ou `--wiki-only`, ou `--list-only`) ao invocar o skill para pular completamente a etapa do AI. A camada de comentários estruturados continua rodando quando você passa `--semantic` a `scan` / `sync`.

---

## Comparativo

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| Análise rotas / controladores | ✅ | ❌ | ✅ |
| Grafo serviços / DI | parcial | ✅ | ✅ |
| Resolução Interface → Impl | ❌ | ❌ | ✅ |
| Extração entidades / ORM | ✅ | ❌ | ✅ |
| Análise componentes frontend | ✅ | ❌ | ✅ |
| Detecção de comunidades | ❌ | ✅ | ✅ |
| Exportação Obsidian Vault | ❌ | ✅ | ✅ |
| Servidor MCP | ✅ | ❌ | ✅ |
| Mapa de contexto (CLAUDE.md) | ✅ | ✅ | ✅ |
| Workspace multi-projeto | parcial | ❌ | ✅ |
| Baseado em Python | ❌ | ✅ | ✅ |

---

## Benchmarks

| Base de código | Stack | Arquivos | Nós | Arestas | Comunidades | Tempo de scan |
|---------------|-------|----------|-----|---------|-------------|---------------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3 projetos) | 444 | 382 | 553 | 175 | ~12s |

---

## Privacidade e segurança

Todo o processamento AST é local. Ao executar o codebeacon diretamente, seu código-fonte nunca sai da máquina. Sem telemetria nem chamadas de rede durante o uso normal.

- O CLI em si **nunca chama um provedor de LLM** — o pacote codebeacon não traz cliente de API, nem gerenciamento de chave, nem nome de modelo.
- `--semantic` ativa **apenas a análise de comentários estruturados** (Javadoc `@see` / `{@link}`, JSDoc `@see` / tipos de `@param`, Python `:class:` / `:func:` / `See Also`). 100% local.
- **AI-semântico** (a camada LLM mais profunda) é acionado pelo skill `/codebeacon` do Claude Code. O agente lê `semantic-tasks.jsonl`, executa a análise usando **o modelo da sessão atual** e grava `semantic-results.jsonl`. O CLI Python apenas prepara o lote de tarefas e mescla os resultados — ele nem sabe qual modelo foi usado. Passe `--no-semantic` ao skill para pular completamente o passo do LLM.

---

## Contribuindo

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

O ponto de entrada mais simples para adicionar suporte a novos frameworks é escrever um arquivo de query tree-sitter em `codebeacon/extract/queries/`. Consulte [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md).

---

## Licença

MIT — veja [LICENSE](LICENSE).

---

## Agradecimentos

Construído sobre [tree-sitter](https://tree-sitter.github.io/tree-sitter/), [NetworkX](https://networkx.org/) e [graspologic](https://microsoft.github.io/graspologic/). Inspirado nas abordagens complementares de [codesight](https://github.com/Houseofmvps/codesight) e [graphify](https://github.com/safishamsi/graphify).
