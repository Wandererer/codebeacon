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

## Novidades na 0.6.7

Acompanhamento da auditoria de paridade com graphify da 0.6.6: a deriva de gramática agora falha de forma ruidosa em vez de silenciosa, e as negações no arquivo de ignore não deixam mais os scans lentos.

- **A deriva de gramática é uma falha ruidosa, não um grafo vazio silencioso** — quando uma query do tree-sitter não compila contra uma gramática que *deveria* suportar (p. ex. um nó renomeado em uma futura atualização de gramática), `run_query` agora lança uma exceção e o arquivo é registrado como `ExtractionFailure` em vez de extrair silenciosamente nada. Junto com os limites superiores da 0.6.6 e o teste "cada query compila contra cada gramática que declara suportar", a deriva agora é detectada de três formas independentes.
- **Uma única negação `!` no `.codebeaconignore` não força mais um percurso completo da árvore** — uma regra de negação em qualquer lugar desativava o pruning de diretórios *em todo lugar*, então o scanner descia em cada diretório excluído (`node_modules`, `build`, …) mesmo quando a negação não podia resgatar nada ali. Agora um diretório ignorado só é mantido se uma negação realmente puder reincluir um arquivo *abaixo dele*; regras `!` não relacionadas não custam nada.
- **Globs de ignore são compilados uma única vez** — o matcher no estilo gitignore memoiza a regex compilada por padrão em vez de reconstruí-la a cada verificação de caminho (descoberta mais rápida em árvores profundas com arquivos de ignore grandes). Semântica inalterada.

---

## Novidades na 0.6.6

Uma auditoria de paridade com graphify do upstream v0.8.37–v0.8.40 (e issues reportadas até #1362): uma varredura de "verificar e então refutar de forma adversária" sobre 32 candidatos confirmou **6 bugs reais**. O destaque — três extratores de framework produziam silenciosamente *nada*.

- **Apps Express/Koa/Fastify em TypeScript agora extraem rotas** — `express.scm` fixava o nó de nome de classe do JavaScript, que é um "Impossible pattern" sob a gramática do TypeScript, então a query inteira não compilava e o erro era engolido: **apps Express em TS extraíam 0 rotas**. (Apps JavaScript funcionavam, e a única fixture de teste era `.js`, então passou despercebido.) A mesma causa atingia `vue.scm` (SFCs Vue com `<script>` simples → 0 componentes). Ambos agora usam um coringa de nó neutro de gramática que compila em JS e TS.
- **Arquivos Kotlin em projetos Spring não dão mais erro** — `spring_boot.scm` é uma query de gramática Java mas tinha permissão de rodar contra Kotlin, emitindo `Invalid node type: marker_annotation` e descartando cada arquivo `.kt`. Kotlin agora é bloqueado de forma limpa (Kotlin Spring Boot precisaria de sua própria query).
- **Gramáticas do tree-sitter têm limites superiores fixados** — `pyproject.toml` fixava as gramáticas sem limite superior (`>=0.23`), então um futuro release de gramática que renomeasse nós da AST poderia quebrar as queries silenciosamente de novo. Cada gramática agora tem um teto de faixa compatível, e um novo teste verifica que cada `.scm` distribuída compila contra cada gramática que declara suportar.
- **O cache de extração é versionado** — após atualizar o codebeacon, um `--update` incremental podia reutilizar resultados extraídos pela versão *antiga* para arquivos inalterados (um hash de conteúdo não detecta que o extrator mudou). O cache agora carrega a versão do codebeacon e é descartado em caso de divergência.
- **Nomes acentuados / não ASCII resolvem no macOS** — `codebeacon query` / `path` / MCP e `affected` agora normalizam rótulos e caminhos para Unicode NFC, de modo que um nome copiado de um nome de arquivo do macOS (armazenado como NFD) corresponde ao rótulo NFC no grafo (p. ex. `Auditoría`).
- Além disso: um `cache.json` corrompido é salvo em backup e reconstruído em vez de ser silenciosamente resetado e sobrescrito.

---

## Novidades na 0.6.5

`codebeacon upgrade` agora funciona em qualquer ambiente — antes ele presumia uma instalação pip comum e falhava silenciosamente em máquinas onde não era o caso.

- **Detecção do gerenciador de instalação** — o comando upgrade detecta como o codebeacon foi instalado e executa a ferramenta correspondente: `pip install --upgrade` para instalações pip, `pipx upgrade codebeacon` para pipx, `uv tool upgrade codebeacon` para uv. Os venvs do pipx/uv tool vêm *sem* o módulo `pip`, então a antiga chamada incondicional a `python -m pip` morria antes de fazer qualquer coisa.
- **Verificação do upgrade** — após o upgrade, um interpretador novo relê a versão instalada e reporta `0.6.4 -> 0.6.5`. Se a versão não mudou mas o PyPI tem uma release mais nova, você recebe um aviso de que o `codebeacon` no seu PATH pode pertencer a outro ambiente Python — em vez de um falso "Upgrade complete".
- **Falhas acionáveis** — um ambiente sem pip imprime os comandos exatos a executar; uma recusa PEP 668 `externally-managed-environment` explica a solução (pipx ou um virtualenv) em vez de despejar um erro pip cru. O comando também mostra logo de início a versão atual e a mais recente no PyPI.

---

## Novidades na 0.6.4

Limpeza do deep-dive — as saídas caem onde você procura por elas, mais dois bugs de perda silenciosa de dados encontrados ao verificá-lo num workspace de 47 projetos.

- **O deep-dive escreve em exatamente dois níveis** — cada *raiz de repo* (um diretório com seu próprio `.git` ou `codebeacon.yaml`) e a *raiz do escaneamento*. As pastas de framework de um monorepo (`mono/landing`, `mono/server`) não ganham mais cada uma seu próprio `.codebeacon/` + CLAUDE.md; o grafo combinado delas vive em `mono/.codebeacon/`, e a raiz do escaneamento carrega o grafo completo do workspace, então qualquer projeto pode ser encontrado a partir de um só lugar. Rodar o deep-dive *dentro* de um monorepo agora produz uma única saída raiz em vez de uma por subpasta.
- **Chaves de cache têm namespace por framework** — um grupo de repos compartilha um cache, e um projeto pai que percorria primeiro os arquivos de um projeto aninhado (`desktop/` como sveltekit sobre `desktop/src-tauri`) envenenava o cache com resultados vazios que o projeto aninhado (tauri) depois reutilizava, descartando silenciosamente todas as suas rotas e entidades.
- **Corrida no carregamento de gramáticas corrigida** — dois workers de extração em paralelo encontrando uma gramática tree-sitter sem cache construíam cada um sua própria instância de `Language`; os arquivos da thread perdedora então falhavam numa checagem de identidade e extraíam **nada** — sem aviso, sem registro de falha, só alguns arquivos aleatoriamente sem todas as suas rotas em escaneamentos grandes. O primeiro carregamento agora está travado numa única instância compartilhada (verificado estável ao longo de 20 escaneamentos completos consecutivos).

---

## Novidades na 0.6.3

Versão de correção de bugs — uma auditoria de paridade com o graphify (upstream 3–10 de junho) mais uma auditoria independente do próprio código do codebeacon: **16 correções**, verificadas de ponta a ponta com um escaneamento de workspace `--deep-dive` de 47 projetos (5.226 nós / 8.715 arestas).

- **Hooks de git agora disparam em todo lugar** — o hook de reconstrução pós-commit fixa o interpretador Python usado na instalação dentro do script e se desacopla via `subprocess` em vez de `nohup`, então funciona em clientes git com GUI (Sublime Merge, GitKraken), runners de CI e no Windows — ambientes onde o lançador `codebeacon` não está no `PATH` e o hook antigo silenciosamente não fazia nada. Rode `codebeacon hook install` de novo para pegar a correção; o merge driver é fixado da mesma forma.
- **Imports JS/TS comentados não criam mais arestas** — as passadas de regex de re-exports barrel e `require()` agora removem primeiro os comentários `//` e `/* */` (cientes de literais de string). Um `export * from './legacy'` comentado produzia uma aresta fantasma e falsos ciclos de import.
- **`from pkg import name` vincula o alvo real (Python)** — o extrator de imports agora captura os nomes importados, então `from auth.services import UserService` liga ao nó `UserService` e `from src.services import enricher` liga ao submódulo. Antes só o último segmento do caminho do módulo era tentado, deixando arquivos de teste desconectados. Aliases (`import x as y`) resolvem para o nome real do símbolo.
- **"High-Impact Files" é de alto impacto de verdade** — o ranking de hubs (CLAUDE.md, `analyze`) contava o *fan-out* de imports via o `source_file` da aresta (sempre o importador), então pontos de entrada superavam módulos compartilhados reais com contagens infladas por nó ("imported by 392 files" num repo de 60 arquivos). Ambas as cópias agora contam arquivos importadores distintos por arquivo importado.
- **Arestas `injects` de DI carregam caminhos de arquivo reais** — arestas de injeção de dependência resolvidas carimbavam o ID do nó do grafo (`proj::Name`) em `source_file`; agora carregam o arquivo real do nó de origem.
- **Prefixos de rotas aninhadas do Ktor são concatenados** — `route("/api") { route("/v1") { get("/users") } }` extrai `/api/v1/users` em vez de descartar todos os prefixos externos.
- **Rotas com o mesmo caminho casam ambas** — quando dois serviços expõem a mesma URL (gateway + upstream), o enriquecimento `calls_api` não mantém mais silenciosamente só a última.
- **A configuração tolera YAML esparso** — `output:` / `wave:` / `semantic:` deixados vazios não quebram mais com `AttributeError`; um `-` solto sob `projects:` levanta um erro de configuração limpo em vez de um `TypeError`.
- **A detecção de linguagem pula diretórios vendorizados** — o voto de linguagem de fallback poda `node_modules` / `.git` / `dist`, então um repo Python com JS vendorizado não é mais detectado como *javascript* (e a descoberta não rastreia mais dezenas de milhares de arquivos vendorizados).
- **Links do wiki casam com seus arquivos** — os alvos dos links agora usam exatamente a mesma transformação de nome de arquivo com que o gerador escreve, então rótulos com espaços, `#`, parênteses ou genéricos não produzem mais links mortos.
- Além disso: ordem determinista das arestas de enriquecimento, uma trava de build contra rótulos `None`, um cache de extração thread-safe, referências fantasmas de `Depends()` do FastAPI removidas, e nomes de pastas de serviços do Obsidian limitados em bytes.

---

## Novidades na 0.6.2

- **IDs de comunidade deterministas** — comunidades de tamanho igual eram numeradas pela ordem de enumeração do particionador, remexendo 77–88% de `beacon.json` num re-escaneamento sem mudanças; agrupamentos idênticos agora sempre recebem IDs idênticos.
- **Nomes de arquivo de notas limitados em bytes** — um nome de classe CJK com mais de 85 caracteres estourava o limite de 255 bytes do sistema de arquivos e derrubava toda a exportação wiki/Obsidian com `ENAMETOOLONG`; agora limitado a 200 bytes UTF-8 com um sufixo de hash à prova de colisão.
- **Arestas de DI restauradas para FastAPI / Laravel / ASP.NET** — referências resolvidas de `Depends()` / `bind()` / `AddScoped<>` eram indexadas por caminho de arquivo enquanto os nós são indexados por projeto, então as arestas eram descartadas silenciosamente; agora são remapeadas para os IDs finais dos nós.
- **DI interface → implementação revivida** — os metadados `implements`/`extends` nunca eram preenchidos por nenhum extrator, então a injeção tipada por interface nunca se resolvia; Spring, ASP.NET, NestJS e Angular agora a conectam de ponta a ponta.

---

## Novidades na 0.6.1

Versão de correção — exatidão de extração e saída reproduzível.

- **Seis extratores de frameworks restaurados** — as queries tree-sitter de `laravel`, `angular`, `aspnet`, `actix`, `ktor` e `vapor` haviam se desencontrado das versões atuais das gramáticas e não extraíam **nada**: a query não compilava e o erro era engolido como aviso. As seis agora compilam e extraem contra as gramáticas incluídas (campos `scope:`/`name:` do Laravel, decoradores `export class` do Angular, campos `invocation_expression` do ASP.NET, atributos ancorados a irmãos do Actix, renomeações de nós do Kotlin 1.x, conjunto de nós do Swift 0.0.1), cada uma com um teste de regressão para não quebrarem silenciosamente de novo.
- **`beacon.json` reproduzível** — os caminhos `source_file` dos nós são reescritos relativos à raiz de cada projeto antes da serialização, então escanear o mesmo commit em duas máquinas produz um grafo idêntico byte a byte em vez de remexer caminhos absolutos nos diffs.
- **`affected` não super-reporta mais** — a correspondência de arquivos alterados é alinhada por segmentos de caminho, então `src/user.py` não arrasta mais nós alheios como `foosrc/user.py`.
- **Correção de crash no `semantic-apply`** — um `confidence_score: null` em uma aresta JSONL arquivada/migrada não aborta mais a execução com `TypeError`; é normalizado para o padrão seguro como o resto do pipeline.
- **Compatibilidade futura com NetworkX 3.6** — `beacon.json` é gravado com a chave explícita `edges="links"` para que uma mudança de padrão upstream não altere silenciosamente o formato em disco; o servidor MCP carrega pela mesma camada de compatibilidade.
- **Higiene do vault do Obsidian** — a limpeza de notas obsoletas varre o vault inteiro (raiz + aninhado), e o filtro de imports entre linguagens se baseia na linguagem-fonte real da nota em vez de um sufixo de nome de arquivo que nunca casava.
- **Semântica do gitignore** — padrões ancorados como `build/*.js` não deixam mais `*` cruzar `/`, então arquivos aninhados não são ignorados por engano.
- **App Router do Next.js** — rotas `page.js` / `page.jsx` baseadas em JS agora são descobertas (antes só `.ts` / `.tsx`).
- **Correções de atribuição de DI** — `Depends()` do FastAPI e a injeção por construtor do Angular são atribuídos à função/classe contêiner por faixa de bytes em vez da primeira/última do arquivo; `@using` do Razor não emite mais arestas duplicadas.

---

## Novidades na 0.6.0

- **`codebeacon affected`** — recebe uma lista de arquivos alterados (ou via `--base <ref>` um git diff) e imprime todos os nós do grafo a jusante. Pensado para pontuação de risco em CI e revisão de PR.
- **Arquivos de projeto `.NET`** — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml` agora são analisados: `<ProjectReference>` / `<PackageReference>` viram arestas do grafo, e as diretivas Razor `@inherits` / `@inject` / `@using` ligam páginas Blazor aos seus tipos de back-end.
- **Re-exports barrel JS/TS** — `export { X } from './mod'` e `export * from './mod'` agora produzem arestas explícitas `re_exports`, para que barrels Next.js / monorepo deixem de aparecer com 0 imports.
- **Flag `--exclude PATTERN`** para `scan` / `sync`, mais fallback automático para `.gitignore` quando `.codebeaconignore` está ausente.
- **`codebeacon install --project [PATH]`** — instala o skill `/codebeacon` em `<PATH>/.claude/` em vez de `~/.claude/`, para que equipes fixem uma versão do SKILL.md por repositório.
- **Wiki se auto-corrige** — execuções `--update` agora removem os arquivos `wiki/<project>/{controllers,services,entities,components}/*.md` cujos nós do grafo deixaram de existir.
- **Trava anti-encolhimento flexibilizada para remoções explícitas** — no modo `--update`, escrever um `beacon.json` menor não é mais recusado quando o cache já considerou os arquivos removidos; a trava continua agindo contra corrupção silenciosa.
- **União de declarações entre arquivos** — `extension Foo` do Swift, `partial class` do C# e classes Ruby reabertas unem seus `fields` / `methods` em um único nó canônico em vez de o último a escrever vencer.
- **Busca reforçada** — `BeaconIndex` usa `casefold()`, então o `ß` alemão, o `i/İ` turco, o `σ/ς` grego e rótulos CJK fazem match corretamente.
- **Contexto semântico mais rico** — cada chunk de tarefa agora carrega os chamadores e chamados do grafo em `neighbors`, mantendo o LLM ancorado em rótulos reais. `SKILL.md` adiciona **Step 0 — Constrained query expansion** para que fluxos `/codebeacon query` não inventem tokens fantasma.
- **Trava "rendimento zero" do `semantic-apply`** — se todos os chunks arquivaram 0 arestas, a CLI termina com exit 1, permitindo que a CI capture falhas silenciosas do LLM.
- **ArkTS (`.ets`) e segurança de worktree** — `.ets` é coletado; diretórios `worktrees/` aninhados são ignorados para evitar indexação duplicada de worktrees vinculadas.

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
- **Modo de conhecimento (`codebeacon knowledge`)** — escaneia notas markdown (ADRs, atas de reunião, retros, specs, research) e gera um único `KNOWLEDGE.md` ao lado de `.codebeacon/`. Classificação automática por padrões de nome de arquivo e cabeçalhos, parsing de frontmatter YAML do Obsidian e `[[backlinks]]`, e um resumo de "Key Decisions" + "Open Questions" no topo para que o agente entenda *por que* o código tem a forma que tem. Heurística pura — sem chamadas a LLM
- **Atalho de caminho** — `codebeacon ./src` agora equivale a `codebeacon scan ./src`; quando o primeiro argumento não é um subcomando registrado, `scan` é auto-injetado, mantendo a memória muscular de `graphify <path>` / `codesight <path>`
- **Pipeline semântico endurecido** — `semantic-apply` protege contra JSONL do agente malformado (linhas null/lista/code-fence, campos faltando), coerce valores quebrados de `confidence_score` (None/NaN/string/fora do range) para um default seguro, faz snapshot `beacon.json` → `beacon.json.bak` antes do merge para manter a baseline AST sempre recuperável, e regenera `beacon.html` + `callflow.html` para que os exports visuais reflitam as novas arestas inferidas
- **Guards de arquivos/diretórios sensíveis** — os diretórios `secrets/`, `credentials/`, `.ssh/`, `.aws/`, `.gnupg/` são sempre ignorados; nomes de arquivo que combinem com padrões de credenciais (`api_token`, `oauth_token`, `private_key`, `client_secret`; variantes com underscore *e* hífen) são excluídos do coletor antes de chegarem aos extractors

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
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`); `.sln` / `.csproj` / `.fsproj` / `.vbproj` analisados para `ProjectReference` + `PackageReference` |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) coletado — os extratores são agnósticos ao framework |

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
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # padrões estilo gitignore repetíveis
                                          # mesclados com .codebeaconignore / .gitignore

codebeacon init [caminho]                 # gerar codebeacon.yaml
codebeacon sync                           # executar a partir do codebeacon.yaml (adiciona novos projetos do workspace automaticamente)
codebeacon sync --no-rediscover           # não adicionar novos projetos automaticamente (modo yaml curado à mão)
codebeacon sync --exclude PATTERN         # mesma flag, mesma semântica

# PR / CI: o que esse diff realmente quebra?
codebeacon affected --base main           # percorrer a montante os chamadores de cada arquivo alterado
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # caminhos explícitos — sem precisar de git

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
codebeacon install                        # instalar skill do Claude Code (escopo de usuário: ~/.claude/)
codebeacon install --project [PATH]       # instalar em <PATH>/.claude/ (compartilhado pelo time, fixado ao repo)
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
