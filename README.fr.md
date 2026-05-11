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
| C# | ASP.NET Core |
| Swift | Vapor |

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

codebeacon init [chemin]                  # générer codebeacon.yaml
codebeacon sync                           # exécuter depuis codebeacon.yaml (ajoute automatiquement les nouveaux projets du workspace)
codebeacon sync --no-rediscover           # ne pas ajouter automatiquement les nouveaux projets (mode yaml géré manuellement)

codebeacon query <terme> [--dir .codebeacon] [--limit N]   # rechercher des nœuds par sous-chaîne de label
codebeacon path <source> <cible> [--dir .codebeacon]       # chemin de dépendances le plus court

# Support multi-développeur (git plumbing)
codebeacon hook install [path]            # installer merge driver + hook post-commit incrémental
codebeacon merge-driver <base> <cur> <other>  # invoqué par git après `hook install` ; union-merge de beacon.json

# Enrichissement AI-sémantique (le LLM est exécuté par l'agent, codebeacon tient la comptabilité)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N]
                                          # réapplique l'archive existante au beacon.json frais
                                          # puis n'émet de tâches que pour les candidats NEUFS
                                          # (dossiers god-node + cibles non résolues)
codebeacon semantic-apply   [--dir .codebeacon]
                                          # fusionne .codebeacon/semantic-results.jsonl comme
                                          # arêtes INFERRED references dans beacon.json,
                                          # ajoute à l'archive .codebeacon/semantic/original.jsonl,
                                          # nettoie les fichiers en attente et régénère
                                          # wiki/obsidian/carte de contexte

codebeacon serve [--dir .codebeacon]      # serveur MCP (stdio)
codebeacon install                        # installer le skill Claude Code
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
2. `codebeacon semantic-prepare` réapplique l'archive précédente au graphe frais puis écrit `.codebeacon/semantic-tasks.jsonl` contenant **uniquement les nouveaux candidats** — fichiers à score élevé (arêtes vers cibles non résolues + dossiers god-node) qui n'ont jamais été traités.
3. Le skill itère sur le fichier de tâches. Pour chaque ligne, l'agent (en utilisant le modèle de sa session courante) lit le champ `excerpt` et renvoie inline les références inférées. Les résultats sont écrits dans `.codebeacon/semantic-results.jsonl`.
4. `codebeacon semantic-apply` fusionne les résultats en arêtes `INFERRED references` dans `beacon.json`, **les ajoute à `.codebeacon/semantic/original.jsonl`** (l'archive durable), nettoie les fichiers en attente et régénère wiki + obsidian + carte de contexte.
5. Au prochain scan : `semantic-prepare` réhydrate l'archive sur le graphe fraîchement construit (pour que les inférences historiques ne disparaissent pas lors d'un re-scan) et n'émet dans le fichier de tâches que **les candidats nouvellement découverts** depuis la dernière mise à jour de l'archive. Les fichiers déjà traités sont sautés via `task_id` (SHA1 de `file_path|node_id`).

Vous obtenez ainsi un enrichissement incrémental et idempotent : l'agent ne réanalyse jamais deux fois le même fichier et le signal AI accumulé survit à chaque re-scan.

### Utilisation directe du CLI

Si vous n'utilisez pas le skill (par ex. en CI), vous pouvez piloter les deux mêmes commandes manuellement et fournir votre propre `semantic-results.jsonl` :

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50

# écrivez vous-même .codebeacon/semantic-results.jsonl ; chaque ligne :
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
