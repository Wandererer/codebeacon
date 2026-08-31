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
  Analyse AST du code source et génération de contexte IA — knowledge graph multi-framework unifié
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## Nouveautés en 0.7.1

La plus grosse release d'audit à ce jour : un double balayage de parité amont (graphify v0.9.13–v0.9.53 / issues #1777–#3235, plus codesight #50–#55) vérifié face à codebeacon avec reproduction obligatoire — **~70 défauts confirmés corrigés** par dix correcteurs en parallèle, chaque correctif testé par mutation, puis relu de manière adverse par le lead avec des exécutions d'intégration en CLI réelle. Suite : 885 → 1 481 tests.

- **Le graphe JS/TS a pratiquement doublé** — les fonctions fléchées en minuscule exportées, les `const` et les membres de littéraux d'objet (`export const useAuthStore = …`, `authUtils.clear`) deviennent enfin des nœuds : sur une vraie application Next.js de 865 fichiers, les nœuds de composants sont passés de **960 → 2 237** et les fichiers ne contribuant rien sont tombés de 406 à 108. Les imports sont désormais résolus d'abord par **chemin** (spécificateurs relatifs, alias `tsconfig`/`jsconfig` avec chaînes `extends` et `${configDir}`, suffixes de package) avant de retomber sur les labels — ainsi `from codebeacon.graph.build import …` ne peut plus se lier à un symbole `build` sans rapport, et la liste « High-Impact Files » dans CLAUDE.md reflète la réalité. L'héritage `class X extends Y` en JS pur et les arêtes d'`await import()` dynamiques sont également capturés.
- **Les préfixes de routes se composent comme dans les vrais frameworks** — vérifié face à des serveurs FastAPI/Express/Flask en cours d'exécution : `include_router(prefix=)` se compose avec le préfixe propre du routeur, les includes sous forme d'attribut (`app.include_router(pkg.router, …)`, `@pkg.router.get`) ne disparaissent plus, les montages en cascade dans un même fichier se démultiplient, un routeur monté deux fois produit les deux routes, et le `register_blueprint(url_prefix=)` de Flask *écrase* correctement. Limite connue : une chaîne de montage qui traverse des **fichiers** n'est toujours pas composée.
- **La résolution DI interface→implémentation fonctionne vraiment maintenant** — une frontière de sérialisation dans le pipeline d'extraction abandonnait silencieusement `implements`/`extends` depuis la 0.6.x, si bien que la fonctionnalité entière était morte de bout en bout alors que le wiki semblait correct. Corrigé, cache invalidé, et testé à la frontière à travers le vrai pipeline. La liaison DI est désormais conditionnée par des preuves : plus de fabrications inter-langages ou inter-projets (un service Spring ne peut plus « injecter » un composant React), les cas ambigus à implémentations multiples ne se lient que via la convention de nommage `*Impl` avec une confiance `AMBIGUOUS` explicite, et une arête en double enregistre sa seconde relation sous un nouvel attribut `also` au lieu de l'écraser.
- **L'identité des nœuds est déterministe et tient compte de l'extension** — `Button.tsx` et `Button.jsx` sont deux nœuds (auparavant l'un absorbait silencieusement l'autre — 6,3 % des déclarations sur le dépôt de codebeacon lui-même) ; les identifiants de nœuds ne dépendent plus de l'ordre d'achèvement des threads ni du répertoire de checkout, si bien que les noms de fichiers wiki/obsidian cessent de fluctuer d'une exécution à l'autre. Les labels qui entrent en collision reçoivent le plus court suffixe de chemin qui les distingue. (Les identifiants des nœuds auparavant fusionnés changeront une fois lors de la mise à niveau.)
- **La couche d'ignore colle beaucoup plus près de git** — les fichiers `.gitignore` imbriqués s'appliquent à leur propre sous-arbre (l'`app/.gitignore` d'un monorepo n'est plus ignoré, ce qui tirait auparavant des dizaines de milliers de fichiers de build dans le scan), `.git/info/exclude` est respecté, les worktrees liés sont détectés structurellement au lieu de doubler le corpus, et les fichiers d'ignore encodés avec BOM / en UTF-16 / en NFD sont décodés au lieu de perdre silencieusement leurs règles. Les noms de répertoires ambigus (`env/`, `build/`, `public/`, `coverage/`, …) ne sont élagués qu'avec des preuves corroborantes — un banc de test UVM `env/` ou un package Python nommé `coverage/` reste dans le graphe. La correspondance est ~19× plus rapide, et un nouveau diagnostic `ignored.json` consigne *pourquoi* chaque sous-arbre a été sauté.
- **Le garde-fou anti-rétrécissement protège enfin les chemins qui comptent** — il était auparavant désarmé par la simple présence de `--update`, c'est-à-dire précisément sur les chemins sans surveillance (watch, hooks git, CI) ; une erreur de permission pouvait réduire de moitié votre graphe commité, en silence. Il attribue désormais chaque nœud supprimé à son fichier source (supprimé / nouvellement ignoré / **inexpliqué** — seul le dernier cas refuse, avec un vrai drapeau `--force`), reste armé partout, traite un sous-arbre illisible comme « inconnu, pas de dispense », et avertit quand les arêtes s'effondrent alors même que les nœuds sont restés stables.
- **`scan → knowledge → scan` ne se bloque plus** — le flux documenté de la 0.7.0 se terminait soit par un code de sortie 1 (« refusing to shrink »), soit en abandonnant silencieusement votre surcouche de notes. Le garde-fou tient désormais compte des niveaux et la surcouche knowledge est **réappliquée automatiquement après chaque scan** ; supprimer une note élague exactement cette note. Les `[[wikilinks]]` que vous écrivez créent enfin des arêtes (ils étaient analysés puis jetés — 100 % de perte), les notes portent `node_kind`/frontmatter, et les fichiers générés (CLAUDE.md, KNOWLEDGE.md) ne sont plus réingérés comme des notes.
- **Un index commité reste propre** — un rescan sans changement réécrit désormais **zéro** fichier commité (avant : tous, un brassage de ~31k fichiers en amont) : `built_at_ts` dérive du commit, les exports ne s'écrivent qu'en cas de changement de contenu, et le cache AST local à la machine s'auto-git-ignore. Les exports HTML (`beacon.html`, `callflow.html`) embarquent leur JS **hors ligne par défaut** (d3 + mermaid vendorisés sous `_assets/`) — conformément à la posture air-gapped ; mettez `output.html_assets: cdn` pour conserver l'ancien comportement. Les chemins absolus de la machine de build ne fuitent plus dans aucun artefact.
- **Des réponses MCP auxquelles un programme peut se fier** — les échecs d'outil renvoient `isError: true` avec le message actionnable (au lieu d'une prose d'erreur en forme de succès, ou d'une erreur de protocole que le client avale) ; la résolution de noms privilégie une correspondance exacte avant les sous-chaînes, si bien que `blast_radius("User")` ne répond plus au sujet de `UserServiceImpl` ; chaque outil respecte un `token_budget` (2 000 tokens par défaut) et annonce la troncature par rapport au total réel.
- **Balayage de robustesse et de sécurité** — le XML `.csproj` est analysé avec un filtre DOCTYPE/ENTITY ; le texte destiné aux modèles (sortie MCP, CLAUDE.md) neutralise les tokens de contrôle de gabarit de chat par leur forme (`<|…|>`, `[INST]`) ; `hook install` fonctionne dans les worktrees git et ne laisse jamais un dépôt à moitié configuré ; `install`/`upgrade` sauvegardent un SKILL.md modifié à la main au lieu de l'écraser, et un marqueur non terminé ne peut plus supprimer le contenu utilisateur situé en dessous ; un CLAUDE.md en cp949/latin-1 ne fait plus planter le scan ; `codebeacon … | head` se termine proprement ; le mode watch ne se redéclenche plus lui-même sur les événements inotify de Linux ; le clustering de Leiden est initialisé avec une graine, si bien que les communautés cessent de dériver de 12 % à chaque rescan.

Notes de mise à niveau : les identifiants de nœuds des déclarations auparavant fusionnées changent une fois ; les `task_id` sémantiques sont invalidés une fois (les tâches hachent désormais le fichier entier, ce qui corrige « les modifications au-delà du caractère 4 000 ne sont jamais réanalysées ») ; le cache AST est invalidé une fois (empreinte de schéma) ; nouvel attribut d'arête `also`, nouvelle valeur de confiance `AMBIGUOUS`, nouveau marqueur `verification` sur les externes forgés par le sémantique. Si votre dépôt a déjà commité `.codebeacon/cache/`, exécutez une fois `git rm --cached -r .codebeacon/cache` — le nouveau `.gitignore` auto-ignorant ne peut pas retirer du suivi les fichiers qui le sont déjà.

Historique complet des versions : voir [CHANGELOG.md](CHANGELOG.md) (en anglais).

---

## Pourquoi codebeacon ?

À chaque nouvelle session de développement assisté par IA, l'assistant repart de zéro. Il ne connaît ni vos routes, ni votre couche de services, ni votre modèle d'entités, ni les relations entre vos microservices. Vous passez le début de chaque session à coller des fichiers, expliquer la structure et rétablir le contexte.

Les outils existants ne résolvent ce problème qu'en partie. Les analyseurs de routes cartographient vos contrôleurs mais omettent les dépendances de services. Les outils de knowledge graph capturent les relations mais ignorent la surface API. Vous finissez par exécuter les deux, assembler manuellement les résultats, et recommencer à chaque changement dans le code.

**codebeacon unifie ces deux approches dans un seul CLI.** Une commande suffit pour analyser l'ensemble du code avec tree-sitter, résoudre l'injection de dépendances entre fichiers, détecter les clusters communautaires dans l'architecture, et écrire une carte de contexte prête à l'emploi dans `CLAUDE.md`, `.cursorrules` et `AGENTS.md`.

---

## Fonctionnalités principales

- **Pipeline unifié** — analyse routes/contrôleurs + knowledge graph en un seul outil
- **27 frameworks, 9 langages** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor
- **Basé sur tree-sitter** — analyse AST structurelle, pas de regex ; grammaires de langage incluses par défaut
- **Résolution DI en 2 passes** — Pass 1 extrait les nœuds AST locaux ; Pass 2 construit une table de symboles globale et résout les mappings Interface → Implementation
- **Architecture Wave merge** — fichiers traités en chunks parallèles puis fusionnés globalement ; gère les grands monorepos sans problème mémoire
- **Formats de sortie multiples** — knowledge graph JSON, wiki Markdown, Obsidian Vault, cartes de contexte IA, serveur MCP, HTML interactif
- **Exploration visuelle** — `beacon.html` (arbre repliable D3) et `callflow.html` (diagrammes d'architecture Mermaid par communauté) régénérés à chaque scan
- **Détection de communautés** — clustering Leiden/Louvain révèle les vraies frontières architecturales
- **Cache incrémental** — SHA-256 + chemin rapide mtime/size ; les modifications de mtime sans changement de contenu (Obsidian/iCloud/Nextcloud) ne déclenchent jamais une ré-extraction inutile
- **Promotion de confiance** — les arêtes `calls` inter-fichiers passent de INFERRED à EXTRACTED automatiquement quand un import explicite prouve le binding
- **Écritures sûres** — beacon.json a un shrink guard (une exécution partielle ne peut jamais écraser un graphe complet) et estampille `built_at_commit` afin que REPORT.md signale les sorties stale par rapport au HEAD courant
- **Multi-développeur** — `codebeacon hook install` enregistre un git merge driver pour `beacon.json` et un hook post-commit de rebuild incrémental, de sorte que deux devs scannant la même branche ne produisent jamais de conflits de merge sur le graphe
- **Sortie durcie** — les frontmatter YAML et les labels MCP sont sanitisés : U+2028/U+2029, contrôles C0 et marques bidi sont supprimés avant d'atteindre Obsidian, Cursor ou l'agent
- **`.codebeaconignore` style gitignore** — last-match-wins avec négation `!`, patterns de répertoire (`build/`), patterns ancrés (`/secrets.txt`), règles sur espaces de fin
- **Zéro configuration** — détecte automatiquement les frameworks et langages ; génère `codebeacon.yaml` pour les exécutions suivantes
- **Mode Deep Dive** — `--deep-dive` génère un `.codebeacon/` + `CLAUDE.md` propre à chaque sous-projet ; une commande de mise à jour depuis **n'importe quel** sous-projet synchronise automatiquement tous les projets du workspace
- **Redécouverte automatique du workspace** — à chaque `scan`/`sync`, codebeacon réanalyse le workspace et ajoute automatiquement les nouveaux projets au `codebeacon.yaml` avant l'extraction, de sorte que les sous-projets fraîchement ajoutés ne soient jamais oubliés en silence ; utilisez `--no-rediscover` pour conserver une configuration yaml gérée manuellement
- **Enrichissement sémantique façon Graphify** — après l'extraction AST, le skill dispatche un sous-agent parallèle par chunk pour émettre des fragments complets de knowledge graph `{nodes, edges, hyperedges}` avec 8 types de relations (`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`) et confiance EXTRACTED/INFERRED/AMBIGUOUS ; sur Claude Code, le sous-agent s'exécute un cran sous le modèle hôte (Opus→Sonnet, Sonnet→Haiku) pour garder le coût proportionnel à la taille du corpus. L'AST possède les nœuds de code ; le LLM ne peut contribuer que des nœuds `concept`/`document`/`paper`. Les archives 0.3.x existantes sont rejouées sous le nouveau schéma sans modification
- **Mode connaissance (`codebeacon knowledge`)** — scanne les notes markdown (ADRs, comptes-rendus, rétros, specs, research) et produit un unique `KNOWLEDGE.md` à côté de `.codebeacon/`. Classification automatique par motifs de nom de fichier et de titres, parsing du frontmatter YAML Obsidian et des `[[backlinks]]`, et un résumé « Key Decisions » + « Open Questions » en tête pour que l'agent comprenne *pourquoi* la base de code a cette forme. Pure heuristique — sans appel LLM
- **Raccourci chemin** — `codebeacon ./src` équivaut désormais à `codebeacon scan ./src` ; quand le premier argument n'est pas une sous-commande enregistrée, `scan` est injecté automatiquement, ce qui préserve la mémoire musculaire de `graphify <path>` / `codesight <path>`
- **Pipeline sémantique durci** — `semantic-apply` protège contre les lignes JSONL mal formées de l'agent (null/listes/code-fences/champs manquants), coerce les valeurs cassées de `confidence_score` (None/NaN/string/hors-plage) vers un défaut sûr, snapshote `beacon.json` → `beacon.json.bak` avant le merge pour que la baseline AST reste toujours récupérable, et régénère `beacon.html` + `callflow.html` pour que les exports visuels reflètent les nouvelles arêtes inférées
- **Garde-fous fichiers/dossiers sensibles** — les répertoires `secrets/`, `credentials/`, `.ssh/`, `.aws/`, `.gnupg/` sont toujours ignorés ; les noms de fichiers correspondant à des motifs de credentials (`api_token`, `oauth_token`, `private_key`, `client_secret` ; variantes avec underscore *et* tiret) sont exclus du collecteur avant d'atteindre les extracteurs

---

## Démarrage rapide

```bash
pip install codebeacon

codebeacon scan .
```

codebeacon détecte les types de projet, extrait routes/services/entités/composants, construit le knowledge graph et écrit tout dans `.codebeacon/`.

Pour un workspace multi-projet :

```bash
codebeacon scan /chemin/workspace   # détecte tous les projets, génère codebeacon.yaml
codebeacon sync                     # exécutions suivantes via la configuration
```

---

## Frameworks supportés

| Langage | Frameworks |
|---------|-----------|
| Java / Kotlin | Spring Boot, Ktor |
| Python | Django, FastAPI, Flask |
| JavaScript / TypeScript | Express, Fastify, Koa, NestJS, React, Next.js, Vue, Nuxt, Angular, SvelteKit |
| Go | Gin, Echo, Fiber |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web, Axum, Tauri, Rocket, Warp |
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`) ; `.sln` / `.csproj` / `.fsproj` / `.vbproj` analysés pour `ProjectReference` + `PackageReference` |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) collecté — les extracteurs sont framework-agnostiques |

---

## Architecture

codebeacon exécute un pipeline d'extraction en 2 passes :

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         AST local          Table de     Filtrage    HTTP API
                         par chunk          symboles     artefacts   DB partagée
                         (Pass 1)           (Pass 2)
```

**Pass 1 — Extraction Wave :** Les fichiers sont traités en chunks parallèles. Chaque fichier passe par cinq extracteurs : routes, services, entités, composants et dépendances.

**Pass 2 — Construction du graphe :** Fusion de tous les résultats Wave. Une table de symboles globale résout les références d'injection de dépendances non résolues — les mappings Interface→Implementation que les outils mono-passe manquent.

---

## Structure de sortie

Après le scan, les fichiers de carte de contexte sont mis à jour à la racine du projet (le contenu utilisateur existant est préservé) et le knowledge graph dans `.codebeacon/` :

```
project-root/
  CLAUDE.md              ← carte de contexte IA (bloc codebeacon fusionné ; contenu utilisateur conservé)
  .cursorrules           ← contexte Cursor IDE (même stratégie de fusion)
  AGENTS.md              ← contexte OpenAI Agents / Codex (même stratégie de fusion)
  .codebeacon/
    beacon.json          ← knowledge graph complet ; embarque `meta.built_at_commit`
    beacon.html          ← visualiseur d'arbre repliable D3 (ouvrir dans un navigateur)
    callflow.html        ← diagrammes Mermaid de call-flow groupés par communauté
    REPORT.md            ← nœuds dieu, connexions surprenantes, fichiers hub, fraîcheur
    wiki/
      index.md
      overview.md
      routes.md
      <project>/
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian Vault (une note par nœud du graphe)
```

### Mode Deep Dive

Avec `--deep-dive`, chaque sous-projet reçoit son propre `.codebeacon/` + `CLAUDE.md`. Claude Code charge les fichiers `CLAUDE.md` de manière hiérarchique — une session dans `api-server/` charge à la fois la vue d'ensemble du workspace et les détails spécifiques au projet.

Le point clé : une commande de mise à jour depuis **n'importe quel sous-projet** synchronise automatiquement tout le workspace :

```bash
# Premier scan deep dive
codebeacon scan /workspace --deep-dive

# Plus tard, depuis n'importe quel sous-projet — trouve la config parente et met à jour TOUS les projets
cd /workspace/api-server
codebeacon scan . --update
```

Structure de sortie :
```
workspace/
  CLAUDE.md                   ← combiné (tous les projets)
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← graphe combiné
  api-server/
    CLAUDE.md                 ← api-server uniquement
    .codebeacon/
  frontend/
    CLAUDE.md                 ← frontend uniquement
    .codebeacon/
```

## Exploration visuelle

Chaque scan écrit deux fichiers HTML autonomes à côté de `beacon.json` :

```
.codebeacon/beacon.html      # arbre repliable D3 v7 — ouvrir dans n'importe quel navigateur
.codebeacon/callflow.html    # diagrammes d'architecture Mermaid, un par communauté
```

Pas de build, pas de serveur statique, pas de copier-coller. Ouvre le fichier, clique pour déplier projets → types → nœuds ; survole pour voir le chemin source et le degré. `callflow.html` groupe le graphe par communauté et rend chacune en flowchart Mermaid, avec les arêtes sortantes inter-communautés dans un tableau pliable.

---

## Workflow multi-développeur

Deux devs exécutant `codebeacon scan` sur la même branche produisent des `beacon.json` légèrement différents — point chaud historique de conflits de merge. `codebeacon hook install` règle ça :

```bash
codebeacon hook install            # à la racine du repo
```

Cela enregistre :

- un **git merge driver** qui union-merge deux `beacon.json` en un seul (nœuds dédupliqués par ID, arêtes par `(source, target, relation)`),
- une entrée `.gitattributes` pointant `*beacon.json` vers le driver,
- un **hook post-commit** qui lance `codebeacon scan . --update` en arrière-plan pour que le graphe ne soit jamais en retard sur les commits. Sortie dans `~/.cache/codebeacon-rebuild.log`.

Le merge driver sort toujours en 0 — la régénération du graphe ne bloque jamais un vrai merge.

---

## Garanties de sécurité

Quelques invariants que le writer applique à chaque scan réussi :

| Guard | Ce qu'il empêche |
|---|---|
| **Shrink guard** | Une extraction partielle ratée ou une exécution interrompue ne peut jamais écraser un `beacon.json` complet plus grand. Bypass via `force=True` depuis l'API. |
| **Écriture atomique** | `beacon.json` est écrit via `os.replace`, donc le fichier est soit complet soit intact — jamais à moitié écrit. |
| **Estampille `built_at_commit`** | `beacon.json` embarque `meta.built_at_commit` (SHA complet) et `REPORT.md` affiche le SHA court. Si HEAD a avancé, le rapport marque le graphe comme `⚠ stale` avec un hint d'une ligne. |
| **Durcissement frontmatter / labels** | Les valeurs YAML sont en single-quoted et échappent U+2028, U+2029, tabulation et contrôles C0 ; la sortie MCP passe chaque label par le même sanitizer. Un identifiant malveillant dans le code source ne peut pas casser le parser YAML d'Obsidian ni injecter de séquences de contrôle dans le contexte d'un agent LLM. |

---

## Configuration

Exécutez `codebeacon init` pour générer `codebeacon.yaml`, ou créez-le manuellement :

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # optionnel : détecté automatiquement

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
  chunk_size: 300              # fichiers par chunk
  max_parallel: 5              # threads parallèles

semantic:
  enabled: false               # uniquement l'extraction de commentaires structurés ;
                               # activée par --semantic. L'AI-sémantique N'EST PAS ici :
                               # elle est déclenchée par le skill /codebeacon
                               # (= l'agent en cours d'exécution).

deep_dive: false               # mettre à true pour une sortie par projet
```

### .codebeaconignore

Placez un fichier `.codebeaconignore` à la racine du projet pour exclure des répertoires ou fichiers du scan. Sémantique conforme à `.gitignore` — last-match-wins avec négation `!`, motifs ancrés (`/foo`), motifs uniquement répertoire (`build/`), commentaires :

```
# .codebeaconignore

# répertoires
build/
generated/
fixtures/

# ancré à la racine uniquement
/scripts/local-only.ts

# motifs glob
*.gen.ts
**/snapshots/**

# ré-inclure un fichier même si build/ est ignoré
!build/manifest.ts
```

`!pattern` ré-inclut un chemin précédemment ignoré ; les règles ultérieures écrasent les précédentes. Le walker élague les répertoires dont le nom matche, mais reporte l'élagage quand une règle de négation pourrait ré-inclure un fichier imbriqué.

---

## Intégration IA

### Skill Claude Code (`/codebeacon`)

Installez codebeacon comme commande slash dans Claude Code :

```bash
pip install codebeacon
codebeacon install
```

Cette commande copie `SKILL.md` dans `~/.claude/skills/codebeacon/` et enregistre le déclencheur `/codebeacon` dans `~/.claude/CLAUDE.md`. Redémarrez votre session Claude Code puis tapez `/codebeacon` pour analyser le répertoire courant.

```
/codebeacon                  # analyser le répertoire courant
/codebeacon /path/to/project # analyser un chemin spécifique
/codebeacon sync             # re-analyser depuis codebeacon.yaml
```

### Serveur MCP

Exécutez codebeacon comme serveur MCP persistant pour permettre à tout client compatible MCP d'interroger directement le graphe de connaissances.

**Étape 1 — analyser le projet :**
```bash
codebeacon scan .
```

**Étape 2 — ajouter à la configuration du client MCP :**

**Claude Code** (`.claude.json` à la racine du projet ou `~/.claude.json` global) :
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

**Cursor** (`~/.cursor/mcp.json`) :
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

**Outils MCP disponibles après connexion :**

| Outil | Description |
|-------|-------------|
| `beacon_wiki_index` | Vue d'ensemble globale (routes, services, entités) |
| `beacon_wiki_article` | Lire un article wiki par son chemin |
| `beacon_query` | Rechercher des nœuds par sous-chaîne d'étiquette |
| `beacon_path` | Chemin de dépendance le plus court entre deux nœuds |
| `beacon_blast_radius` | Appelants en amont et nœuds affectés en aval |
| `beacon_routes` | Liste de toutes les routes HTTP (filtrable par projet) |
| `beacon_services` | Liste de tous les services/classes (filtrable par projet) |

---

## Options d'installation

```bash
pip install codebeacon              # grammaires de langage incluses
pip install codebeacon[cluster]     # + détection de communautés Leiden (graspologic)
pip install --upgrade codebeacon    # mettre à jour vers la dernière version avec toutes les dépendances
```

Les parsers Java, Kotlin, Python, JavaScript, TypeScript, Go, Ruby, PHP, C#, Rust, Swift, HTML et Svelte sont inclus par défaut.

---

## Référence CLI

```bash
codebeacon scan .                         # répertoire courant
codebeacon scan . --update                # incrémental : fichiers modifiés seulement
codebeacon scan . --wiki-only             # ignorer la ré-extraction, régénérer wiki/obsidian/contexte depuis beacon.json existant
codebeacon scan . --semantic              # extraction des références dans commentaires structurés (Javadoc/JSDoc/docstring)
codebeacon scan . --list-only             # détecter les frameworks uniquement
codebeacon scan /workspace --deep-dive    # sortie par projet + workspace combiné
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # motifs gitignore répétables
                                          # fusionnés avec .codebeaconignore / .gitignore

codebeacon init [chemin]                  # générer codebeacon.yaml
codebeacon sync                           # exécuter depuis codebeacon.yaml (ajoute automatiquement les nouveaux projets du workspace)
codebeacon sync --no-rediscover           # ne pas ajouter automatiquement les nouveaux projets (mode yaml géré manuellement)
codebeacon sync --exclude PATTERN         # même drapeau, même sémantique

# PR / CI : qu'est-ce que ce diff casse vraiment ?
codebeacon affected --base main           # remonter les appelants des fichiers modifiés
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # chemins explicites — pas besoin de git

codebeacon query <terme> [--dir .codebeacon] [--limit N]   # rechercher des nœuds par sous-chaîne de label
codebeacon path <source> <cible> [--dir .codebeacon]       # chemin de dépendances le plus court

# Support multi-développeur (git plumbing)
codebeacon hook install [path]            # installer merge driver + hook post-commit incrémental
codebeacon merge-driver <base> <cur> <other>  # invoqué par git après `hook install` ; union-merge de beacon.json

# Enrichissement AI-sémantique (le LLM est exécuté par l'agent, codebeacon tient la comptabilité)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # réhydrate .codebeacon/semantic/original/*.jsonl sur le
                                          # nouveau beacon.json + élague les entrées pointant vers
                                          # des nœuds disparus, puis écrit les nouvelles tâches
                                          # dans .codebeacon/semantic/pending/chunk_NNN.jsonl
                                          # (--chunk-size par chunk, défaut 10). task_id inclut un
                                          # hash de contenu : un fichier modifié est ré-émis.
codebeacon semantic-apply   [--dir .codebeacon]
                                          # pour chaque .codebeacon/semantic/results/chunk_NNN.jsonl
                                          # écrit par l'agent, fusionne les arêtes INFERRED references
                                          # dans beacon.json et DÉPLACE le chunk pending vers
                                          # .codebeacon/semantic/original/chunk_NNN.jsonl (archive
                                          # durable). Supprime les résultats, régénère tout.

codebeacon serve [--dir .codebeacon]      # serveur MCP (stdio)
codebeacon install                        # installer le skill Claude Code (portée utilisateur : ~/.claude/)
codebeacon install --project [PATH]       # installer dans <PATH>/.claude/ (partagé en équipe, épinglé au dépôt)
codebeacon upgrade                        # pip upgrade + rafraîchir ~/.claude/skills/codebeacon/SKILL.md
                                          # (`--force` si installé en mode éditable)
```

---

## Enrichissement AI-sémantique (via le skill `/codebeacon`)

L'analyse tree-sitter trouve ce qui est dans l'AST. **AI-sémantique** trouve ce qui ne vit que dans les *commentaires* — le `@see UserService` dans une Javadoc, le `:class:`OrderRepository`` dans une docstring Python, les références contractuelles documentées à côté d'un handler de route. codebeacon propose deux couches pour cela :

| Couche | Flag | Coût | Ce qu'elle capture |
|---|---|---|---|
| Analyse de commentaires structurés | `--semantic` | gratuit, local, sans LLM | Javadoc `@see` / `{@link}`, JSDoc `@see` / types `@param`, Python `:class:` / `:func:` / `See Also` |
| **AI-sémantique** | auto dans le skill `/codebeacon` | utilise le modèle courant de l'agent — **aucune clé API supplémentaire** | références de classe/type/service que la regex ne peut pas attraper (prose libre, mentions indirectes, hints de type uniquement) |

Le CLI lui-même **n'appelle jamais un LLM**. La couche AI-sémantique est intentionnellement **propriété de l'agent en cours d'exécution** à l'intérieur du skill Claude Code `/codebeacon` — ainsi le modèle choisi par l'utilisateur (Opus / Sonnet / Haiku / autre) est respecté et codebeacon n'a jamais besoin de `ANTHROPIC_API_KEY` ni d'aucune configuration cloud.

### Comment ça tourne

Quand vous invoquez `/codebeacon` dans Claude Code :

1. `scan` / `sync` construit `beacon.json` à partir de l'AST (aucun appel LLM).
2. `codebeacon semantic-prepare` réhydrate l'archive sous `.codebeacon/semantic/original/*.jsonl` sur le graphe frais et **élague** les entrées dont le nœud source a disparu. Il écrit ensuite les nouvelles tâches dans `.codebeacon/semantic/pending/chunk_NNN.jsonl` (≤ `--chunk-size` par fichier, défaut 10). La numérotation des chunks reprend là où l'archive durable s'est arrêtée — pas de collision possible.
3. Le skill itère les chunks pending **un par un**. Pour chaque `pending/chunk_NNN.jsonl`, l'agent (avec le modèle de sa session courante) lit l'`excerpt` de chaque tâche et écrit un `semantic/results/chunk_NNN.jsonl` du même nom.
4. `codebeacon semantic-apply` fusionne les résultats en arêtes `INFERRED references` dans `beacon.json` et **déplace** chaque `pending/chunk_NNN.jsonl` terminé vers **`semantic/original/chunk_NNN.jsonl`** (les arêtes appliquées y sont incluses pour auditabilité). Les fichiers de résultats sont supprimés ; wiki + obsidian + carte de contexte sont régénérés.
5. Au prochain scan : `semantic-prepare` lit chaque chunk sous `original/`, applique ses arêtes au graphe fraîchement construit (les inférences historiques sont conservées) et saute toute tâche dont le `task_id` est déjà archivé. `task_id` = `SHA1(file_path | node_id | excerpt_hash[:8])` — si le contenu sémantique d'un fichier change, il obtient un nouvel id et est ré-analysé.

Enrichissement incrémental et idempotent : l'agent ne ré-analyse jamais deux fois la même combinaison (fichier, contenu), le signal AI accumulé survit à chaque re-scan et les chunks gardent l'ensemble de travail de l'agent petit.

### Utilisation directe du CLI

Si vous n'utilisez pas le skill (par ex. en CI), vous pouvez piloter les deux mêmes commandes manuellement et fournir vos propres `results/chunk_NNN.jsonl` :

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# .codebeacon/semantic/pending/chunk_001.jsonl ... existent.
# Pour chaque chunk pending, écrivez un results/chunk_NNN.jsonl du même nom.
# Chaque ligne :
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### Désactivation

Passez `--no-semantic` (ou `--wiki-only`, ou `--list-only`) lors de l'invocation du skill pour sauter complètement l'étape AI. La couche de commentaires structurés fonctionne toujours quand vous passez `--semantic` à `scan` / `sync`.

---

## Comparaison

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| Analyse routes / contrôleurs | ✅ | ❌ | ✅ |
| Graphe services / DI | partiel | ✅ | ✅ |
| Résolution Interface → Impl | ❌ | ❌ | ✅ |
| Extraction entités / ORM | ✅ | ❌ | ✅ |
| Analyse composants frontend | ✅ | ❌ | ✅ |
| Détection de communautés | ❌ | ✅ | ✅ |
| Export Obsidian Vault | ❌ | ✅ | ✅ |
| Serveur MCP | ✅ | ❌ | ✅ |
| Carte de contexte (CLAUDE.md) | ✅ | ✅ | ✅ |
| Workspace multi-projet | partiel | ❌ | ✅ |
| Basé sur Python | ❌ | ✅ | ✅ |

---

## Benchmarks

| Base de code | Stack | Fichiers | Nœuds | Arêtes | Communautés | Temps de scan |
|-------------|-------|----------|-------|--------|-------------|---------------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3 projets) | 444 | 382 | 553 | 175 | ~12s |

---

## Confidentialité et sécurité

Tout le traitement AST est local. Lorsque vous lancez codebeacon directement, le code source ne quitte jamais votre machine. Aucune télémétrie ni appel réseau pendant le fonctionnement normal.

- Le CLI lui-même **n'appelle jamais un fournisseur LLM** — le paquet codebeacon ne contient aucun client API, ni gestion de clé, ni nom de modèle.
- `--semantic` n'active que **l'analyse des commentaires structurés** (Javadoc `@see` / `{@link}`, JSDoc `@see` / types `@param`, Python `:class:` / `:func:` / `See Also`). 100 % local.
- **AI-sémantique** (la couche LLM plus profonde) est déclenchée par le skill `/codebeacon` de Claude Code. L'agent lit `semantic-tasks.jsonl`, exécute l'analyse avec **le modèle de sa session courante** et écrit `semantic-results.jsonl`. Le CLI Python prépare uniquement le lot de tâches et fusionne les résultats — il ne sait même pas quel modèle a été utilisé. Passez `--no-semantic` au skill pour ignorer entièrement l'étape LLM.

---

## Contribuer

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

Le point d'entrée le plus simple pour ajouter le support d'un nouveau framework est d'écrire un fichier de requête tree-sitter dans `codebeacon/extract/queries/`. Consultez [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md).

---

## Licence

MIT — voir [LICENSE](LICENSE).

---

## Remerciements

Construit sur [tree-sitter](https://tree-sitter.github.io/tree-sitter/), [NetworkX](https://networkx.org/) et [graspologic](https://microsoft.github.io/graspologic/). Inspiré par les approches complémentaires de [codesight](https://github.com/Houseofmvps/codesight) et [graphify](https://github.com/safishamsi/graphify).
