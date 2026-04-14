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
- **24 frameworks, 9 linguagens** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, ASP.NET Core, Vapor, Ktor
- **Baseado em tree-sitter** — análise AST estrutural, não regex; gramáticas de linguagem incluídas por padrão
- **Resolução DI em 2 passos** — Pass 1 extrai nós AST locais; Pass 2 constrói uma tabela de símbolos global e resolve mapeamentos Interface → Implementation
- **Arquitetura Wave merge** — arquivos processados em chunks paralelos e mesclados globalmente; lida com grandes monorepos sem problemas de memória
- **Múltiplos formatos de saída** — knowledge graph JSON, wiki Markdown, Obsidian Vault, mapas de contexto para IA, servidor MCP
- **Detecção de comunidades** — clustering Leiden/Louvain revela as fronteiras arquiteturais reais
- **Cache incremental** — baseado em SHA-256; extrai novamente apenas arquivos alterados desde o último scan
- **Zero configuração** — detecta frameworks e linguagens automaticamente; gera `codebeacon.yaml` para execuções futuras

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
| Rust | Actix-Web, Axum |
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
    beacon.json          ← knowledge graph completo (JSON node-link, consultável)
    REPORT.md            ← nós deus, conexões surpreendentes, arquivos hub
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

### .codebeaconignore

Coloque um arquivo `.codebeaconignore` na raiz do projeto para excluir diretórios ou arquivos do scan. Mesma sintaxe do `.gitignore` — um padrão por linha, `#` para comentários.

```
# .codebeaconignore
generated/
build/
*.generated.ts
fixtures/
```

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
codebeacon scan . --semantic              # extração semântica com LLM
codebeacon scan . --list-only             # apenas detectar frameworks

codebeacon init [caminho]                 # gerar codebeacon.yaml
codebeacon sync                           # executar a partir do codebeacon.yaml

codebeacon query <termo>                  # buscar no grafo (em breve)
codebeacon path <origem> <destino>        # caminho mais curto entre dois nós

codebeacon serve [--dir .codebeacon]      # servidor MCP (stdio)
codebeacon install                        # instalar skill do Claude Code
```

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

Todo o processamento é local. O código-fonte nunca sai da sua máquina. Sem telemetria nem chamadas de rede durante o uso normal.

- A flag `--semantic` (desabilitada por padrão) ativa dois modos de extração:
  1. **Análise de comentários estruturados** (sem LLM) — infere referências cruzadas de Javadoc (`@see`, `{@link}`), docstrings Python (`:class:`, `:func:`) e JSDoc (`@see`, tipos de `@param`)
  2. **Inferência LLM** (opcional) — com `ANTHROPIC_API_KEY` configurado, envia trechos de código para a API Claude para inferência de relações mais profunda; use apenas se habilitado explicitamente

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
