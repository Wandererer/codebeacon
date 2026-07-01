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

## Nouveautés en 0.6.8

Un audit de parité graphify de l'upstream v0.8.41–v0.9.3 (issues signalées jusqu'au #1568). Chaque candidat a été reproduit sur codebeacon avant correction, puis revérifié par une passe de revue adversariale ; **7 bugs réels** confirmés, avec en tête un piège à perte de données et une fuite de confidentialité.

- **`--obsidian-dir` ne peut plus supprimer vos notes** — pointé vers un vault Obsidian existant, l'export balayait *tous* les `.md` en dessous avant de régénérer, pouvant ainsi vider un vrai vault. codebeacon refuse désormais tout répertoire qu'il ne possède pas (seul un répertoire réellement vide, ou portant son marqueur `.codebeacon-vault.json`, est adopté) et saute l'export avec un message clair au lieu de supprimer.
- **`.gitignore` n'est plus désactivé silencieusement par `.codebeaconignore`** — ajouter un `.codebeaconignore` *remplaçait* auparavant le `.gitignore` du dépôt, si bien qu'un fichier exclu uniquement par `.gitignore` (un `prod-dump.sql`, `customer-data.*` au nom neutre) pouvait être indexé dans les artefacts `.codebeacon/` commités. Les deux sont désormais fusionnés (`.codebeaconignore` l'emporte en cas de conflit) ; l'ajouter ne peut que exclure *davantage*.
- **Plus aucun chemin absolu machine dans les artefacts commités** — les valeurs `source_file` des edges/links (l'essentiel de `beacon.json`) et les lignes `Source:` des notes wiki/obsidian conservaient des chemins absolus `/Users/vous/...`, rendant l'index commité non portable et divulguant des chemins locaux. Tout est désormais relatif au projet (edges compris, ainsi que les fichiers `shares_db_entity` inter-projets).
- **Des symboles homonymes dans des répertoires différents n'écrasent plus les notes l'un de l'autre** — les noms de fichiers wiki/obsidian étaient dérivés du label sans normalisation de casse, si bien que sur macOS/Windows `UserService` et `userService` entraient en collision et une note disparaissait silencieusement. Les noms de fichiers sont désormais salés anti-collision et normalisés en casse ; les labels tout en ponctuation (`@`) retombent sur `unnamed` au lieu d'un `@.md` cassé.
- **Un `beacon.json` corrompu ne plante plus** — `codebeacon affected`, le serveur MCP et les exécutions `--wiki-only` sauvegardent désormais un graphe corrompu/tronqué et affichent un message clair « relancez scan » au lieu d'une trace brute.
- **Davantage de composants React sont capturés** — `react.scm` manquait les composants en expression de fonction (`const X = function() {…}`), les HOC importés nus (`const X = forwardRef(…)` sans préfixe `React.`) et les composants `function X()` non exportés. Les trois sont désormais extraits.
- **Les liens du wiki ne pointent plus jamais dans le vide** — un lien vers une page jamais écrite est rétrogradé en texte brut, et un lien vers un article dans un bucket voisin (un service → son entité) est réparé vers le bon chemin relatif au lieu de pointer vers un fichier manquant.

---

## Nouveautés en 0.6.7

Suite de l'audit de parité graphify de 0.6.6 : la dérive de grammaire échoue désormais bruyamment au lieu de silencieusement, et les négations du fichier d'ignore ne ralentissent plus les scans.

- **La dérive de grammaire est un échec bruyant, pas un graphe vide silencieux** — quand une requête tree-sitter ne compile pas contre une grammaire qu'elle est *censée* prendre en charge (p. ex. un nœud renommé dans une future mise à jour de grammaire), `run_query` lève désormais une exception et le fichier est enregistré comme `ExtractionFailure` au lieu de n'extraire silencieusement rien. Avec les bornes supérieures de 0.6.6 et le test « chaque requête compile contre chaque grammaire qu'elle revendique », la dérive est désormais détectée de trois façons indépendantes.
- **Une seule négation `!` dans `.codebeaconignore` ne force plus un parcours complet de l'arbre** — une règle de négation où que ce soit désactivait l'élagage des répertoires *partout*, de sorte que le scanner descendait dans chaque répertoire exclu (`node_modules`, `build`, …) même si la négation ne pouvait rien y récupérer. Un répertoire ignoré n'est désormais conservé que si une négation pourrait réellement réinclure un fichier *en dessous* ; les règles `!` non liées ne coûtent rien.
- **Les globs d'ignore sont compilés une seule fois** — le matcher de style gitignore mémorise la regex compilée par motif au lieu de la reconstruire à chaque vérification de chemin (découverte plus rapide sur les arbres profonds avec de gros fichiers d'ignore). Sémantique inchangée.

---

## Nouveautés en 0.6.6

Un audit de parité graphify de l'upstream v0.8.37–v0.8.40 (et des issues signalées jusqu'à #1362) : un balayage « vérifier puis réfuter de façon adverse » sur 32 candidats a confirmé **6 vrais bugs**. L'essentiel — trois extracteurs de framework ne produisaient silencieusement *rien*.

- **Les apps Express/Koa/Fastify en TypeScript extraient désormais des routes** — `express.scm` codait en dur le nœud de nom de classe de JavaScript, qui est un « Impossible pattern » sous la grammaire TypeScript ; toute la requête ne compilait pas et l'erreur était avalée : **les apps Express en TS extrayaient 0 route**. (Les apps JavaScript fonctionnaient, et la seule fixture de test était `.js`, donc c'est passé inaperçu.) La même cause touchait `vue.scm` (SFC Vue avec `<script>` simple → 0 composant). Les deux utilisent désormais un joker de nœud neutre vis-à-vis de la grammaire qui compile en JS et TS.
- **Les fichiers Kotlin dans les projets Spring ne provoquent plus d'erreur** — `spring_boot.scm` est une requête de grammaire Java mais était autorisée à s'exécuter contre Kotlin, émettant `Invalid node type: marker_annotation` et écartant chaque fichier `.kt`. Kotlin est désormais proprement bloqué (Kotlin Spring Boot nécessiterait sa propre requête).
- **Les grammaires tree-sitter sont épinglées avec des bornes supérieures** — `pyproject.toml` épinglait les grammaires sans limite supérieure (`>=0.23`), de sorte qu'une future version de grammaire renommant des nœuds de l'AST pouvait à nouveau casser les requêtes en silence. Chaque grammaire a désormais un plafond de plage compatible, et un nouveau test vérifie que chaque `.scm` livrée compile contre chaque grammaire qu'elle revendique.
- **Le cache d'extraction est versionné** — après une mise à jour de codebeacon, un `--update` incrémental pouvait réutiliser des résultats extraits par l'*ancienne* version pour des fichiers inchangés (un hash de contenu ne détecte pas que l'extracteur a changé). Le cache porte désormais la version de codebeacon et est rejeté en cas de divergence.
- **Les noms accentués / non-ASCII se résolvent sous macOS** — `codebeacon query` / `path` / MCP et `affected` normalisent désormais les libellés et chemins en Unicode NFC, de sorte qu'un nom copié depuis un nom de fichier macOS (stocké en NFD) correspond au libellé NFC dans le graphe (p. ex. `Auditoría`).
- De plus : un `cache.json` corrompu est sauvegardé et reconstruit au lieu d'être silencieusement réinitialisé puis écrasé.

---

## Nouveautés en 0.6.5

`codebeacon upgrade` fonctionne désormais partout — il supposait auparavant une installation pip classique et échouait silencieusement sur les machines où ce n'était pas le cas.

- **Détection du gestionnaire d'installation** — la commande upgrade détecte comment codebeacon a été installé et exécute l'outil correspondant : `pip install --upgrade` pour pip, `pipx upgrade codebeacon` pour pipx, `uv tool upgrade codebeacon` pour uv. Les venvs pipx/uv tool sont livrés *sans* module `pip`, donc l'ancien appel inconditionnel à `python -m pip` mourait avant de faire quoi que ce soit.
- **Vérification de la mise à jour** — après la mise à jour, un interpréteur neuf relit la version installée et rapporte `0.6.4 -> 0.6.5`. Si la version n'a pas changé alors que PyPI propose une release plus récente, un avertissement indique que le `codebeacon` de votre PATH appartient peut-être à un autre environnement Python — au lieu d'un faux « Upgrade complete ».
- **Échecs actionnables** — un environnement sans pip affiche les commandes exactes à lancer ; un refus PEP 668 `externally-managed-environment` explique la solution (pipx ou un virtualenv) au lieu de déverser une erreur pip brute. La commande affiche aussi d'emblée la version actuelle face à la dernière sur PyPI.

---

## Nouveautés en 0.6.4

Nettoyage du deep-dive — les sorties atterrissent là où vous les cherchez, plus deux bugs de perte silencieuse de données trouvés en le vérifiant sur un workspace de 47 projets.

- **Le deep-dive écrit exactement à deux niveaux** — chaque *racine de dépôt* (un répertoire avec son propre `.git` ou `codebeacon.yaml`) et la *racine du scan*. Les dossiers framework d'un monorepo (`mono/landing`, `mono/server`) ne reçoivent plus chacun leur propre `.codebeacon/` + CLAUDE.md ; leur graphe combiné vit dans `mono/.codebeacon/`, et la racine du scan porte le graphe complet du workspace, donc n'importe quel projet se trouve depuis un seul endroit. Lancer le deep-dive *à l'intérieur* d'un monorepo produit désormais une seule sortie racine au lieu d'une par sous-dossier.
- **Les clés de cache sont namespacées par framework** — un groupe de dépôts partage un seul cache, et un projet parent parcourant en premier les fichiers d'un projet imbriqué (`desktop/` comme sveltekit au-dessus de `desktop/src-tauri`) empoisonnait auparavant le cache avec des résultats vides que le projet imbriqué (tauri) réutilisait ensuite, perdant silencieusement toutes ses routes et entités.
- **Course au chargement des grammaires corrigée** — deux workers d'extraction parallèles touchant une grammaire tree-sitter non mise en cache construisaient chacun leur propre instance `Language` ; les fichiers du thread perdant échouaient alors à une vérification d'identité et n'extrayaient **rien** — aucun avertissement, aucun enregistrement d'échec, juste quelques fichiers auxquels il manquait aléatoirement toutes leurs routes sur les gros scans. Le premier chargement est désormais verrouillé sur une seule instance partagée (vérifié stable sur 20 scans complets consécutifs).

---

## Nouveautés en 0.6.3

Version de correction de bugs — un audit de parité avec graphify (upstream 3–10 juin) plus un audit indépendant du propre code de codebeacon : **16 correctifs**, vérifiés de bout en bout avec un scan de workspace `--deep-dive` sur 47 projets (5 226 nœuds / 8 715 arêtes).

- **Les hooks git se déclenchent désormais partout** — le hook de reconstruction post-commit épingle dans le script l'interpréteur Python ayant servi à l'installation et se détache via `subprocess` plutôt que `nohup`, donc il fonctionne dans les clients git graphiques (Sublime Merge, GitKraken), les runners CI et sous Windows — des environnements où le lanceur `codebeacon` n'est pas sur le `PATH` et où l'ancien hook ne faisait silencieusement rien. Relancez `codebeacon hook install` pour récupérer le correctif ; le merge driver est épinglé de la même manière.
- **Les imports JS/TS commentés ne créent plus d'arêtes** — les passes regex des re-exports barrel et de `require()` retirent désormais d'abord les commentaires `//` et `/* */` (en tenant compte des littéraux de chaîne). Un `export * from './legacy'` commenté produisait auparavant une arête fantôme et de faux cycles d'import.
- **`from pkg import name` lie la vraie cible (Python)** — l'extracteur d'imports capture désormais les noms importés, donc `from auth.services import UserService` pointe vers le nœud `UserService` et `from src.services import enricher` vers le sous-module. Auparavant, seul le dernier segment du chemin de module était essayé, laissant les fichiers de test déconnectés. Les alias (`import x as y`) se résolvent vers le vrai nom de symbole.
- **« High-Impact Files » est vraiment à fort impact** — le classement des hubs (CLAUDE.md, `analyze`) comptait le *fan-out* d'imports via le `source_file` de l'arête (toujours l'importateur), donc les points d'entrée devançaient les vrais modules partagés avec des décomptes gonflés par nœud (« imported by 392 files » dans un dépôt de 60 fichiers). Les deux copies comptent désormais les fichiers importateurs distincts par fichier importé.
- **Les arêtes `injects` de DI portent de vrais chemins de fichiers** — les arêtes d'injection de dépendances résolues estampillaient l'ID du nœud de graphe (`proj::Name`) dans `source_file` ; elles portent désormais le vrai fichier du nœud source.
- **Les préfixes de routes Ktor imbriquées se concatènent** — `route("/api") { route("/v1") { get("/users") } }` extrait `/api/v1/users` au lieu d'abandonner chaque préfixe extérieur.
- **Les routes au même chemin correspondent toutes les deux** — quand deux services exposent la même URL (gateway + upstream), l'enrichissement `calls_api` ne conserve plus silencieusement uniquement la dernière.
- **La configuration tolère le YAML clairsemé** — `output:` / `wave:` / `semantic:` laissés vides ne plantent plus avec `AttributeError` ; un `-` nu égaré sous `projects:` lève une erreur de configuration propre au lieu d'un `TypeError`.
- **La détection de langage saute les répertoires vendorés** — le vote de langage de repli élague `node_modules` / `.git` / `dist`, donc un dépôt Python avec du JS vendoré n'est plus détecté comme *javascript* (et la découverte ne parcourt plus des dizaines de milliers de fichiers vendorés).
- **Les liens du wiki correspondent à leurs fichiers** — les cibles de liens utilisent désormais exactement la même transformation de nom de fichier que celle avec laquelle le générateur écrit, donc les libellés contenant des espaces, `#`, des parenthèses ou des génériques ne produisent plus de liens morts.
- Et aussi : ordre déterministe des arêtes d'enrichissement, un garde de build contre les libellés `None`, un cache d'extraction thread-safe, les références fantômes `Depends()` de FastAPI supprimées, et les noms de dossiers de services Obsidian plafonnés en octets.

---

## Nouveautés en 0.6.2

- **IDs de communauté déterministes** — les communautés de taille égale étaient numérotées selon l'ordre d'énumération du partitionneur, brassant 77–88 % de `beacon.json` lors d'un re-scan sans changement ; des regroupements identiques reçoivent désormais toujours des IDs identiques.
- **Noms de fichiers de notes plafonnés en octets** — un nom de classe CJK de plus de 85 caractères dépassait la limite de 255 octets du système de fichiers et faisait planter tout l'export wiki/Obsidian avec `ENAMETOOLONG` ; plafonné à 200 octets UTF-8 avec un suffixe de hachage anti-collision.
- **Arêtes de DI restaurées pour FastAPI / Laravel / ASP.NET** — les références résolues `Depends()` / `bind()` / `AddScoped<>` étaient indexées par chemin de fichier alors que les nœuds sont indexés par projet, donc les arêtes étaient silencieusement abandonnées ; elles sont désormais remappées sur les IDs finaux des nœuds.
- **DI interface → implémentation ressuscitée** — les métadonnées `implements`/`extends` n'étaient renseignées par aucun extracteur, donc l'injection typée par interface ne se résolvait jamais ; Spring, ASP.NET, NestJS et Angular les câblent désormais de bout en bout.

---

## Nouveautés en 0.6.1

Version corrective — exactitude de l'extraction et sortie reproductible.

- **Six extracteurs de frameworks restaurés** — les requêtes tree-sitter de `laravel`, `angular`, `aspnet`, `actix`, `ktor` et `vapor` s'étaient désynchronisées des versions actuelles des grammaires et n'extrayaient **rien** : la requête ne compilait pas et l'erreur était avalée sous forme d'avertissement. Les six compilent et extraient désormais avec les grammaires fournies (champs `scope:`/`name:` de Laravel, décorateurs `export class` d'Angular, champs `invocation_expression` d'ASP.NET, attributs ancrés aux frères d'Actix, renommages de nœuds de Kotlin 1.x, jeu de nœuds de Swift 0.0.1), chacun avec un test de régression pour ne plus se casser en silence.
- **`beacon.json` reproductible** — les chemins `source_file` des nœuds sont réécrits relativement à la racine de chaque projet avant la sérialisation, de sorte que scanner le même commit sur deux machines produit un graphe identique octet par octet au lieu de brasser des chemins absolus dans les diffs.
- **`affected` ne sur-rapporte plus** — la correspondance des fichiers modifiés est alignée par segments de chemin, donc `src/user.py` n'entraîne plus de nœuds étrangers comme `foosrc/user.py`.
- **Correction de plantage de `semantic-apply`** — un `confidence_score: null` dans une arête JSONL archivée/migrée n'interrompt plus l'exécution avec `TypeError` ; il est normalisé vers la valeur sûre par défaut comme le reste du pipeline.
- **Compatibilité ascendante NetworkX 3.6** — `beacon.json` est écrit avec la clé explicite `edges="links"` pour qu'un changement de valeur par défaut en amont ne modifie pas silencieusement le format sur disque ; le serveur MCP charge via la même couche de compatibilité.
- **Hygiène du vault Obsidian** — le nettoyage des notes obsolètes balaie tout le vault (racine + imbriqué), et le filtre d'imports inter-langages se base sur le vrai langage source de la note au lieu d'un suffixe de nom de fichier qui ne correspondait jamais.
- **Sémantique gitignore** — les motifs ancrés comme `build/*.js` ne laissent plus `*` franchir `/`, donc les fichiers imbriqués ne sont plus ignorés à tort.
- **App Router Next.js** — les routes `page.js` / `page.jsx` basées sur JS sont désormais découvertes (auparavant seulement `.ts` / `.tsx`).
- **Corrections d'attribution de DI** — `Depends()` de FastAPI et l'injection par constructeur d'Angular sont attribués à la fonction/classe englobante par plage d'octets plutôt qu'à la première/dernière du fichier ; `@using` de Razor n'émet plus d'arêtes en double.

---

## Nouveautés en 0.6.0

- **`codebeacon affected`** — prend une liste de fichiers modifiés (ou via `--base <ref>` un git diff) et imprime tous les nœuds du graphe en aval. Pensé pour le scoring de risque en CI et la revue de PR.
- **Fichiers projet `.NET`** — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml` sont désormais analysés : les balises `<ProjectReference>` / `<PackageReference>` deviennent des arêtes du graphe, et les directives Razor `@inherits` / `@inject` / `@using` relient les pages Blazor à leurs types sous-jacents.
- **Re-exports barrel JS/TS** — `export { X } from './mod'` et `export * from './mod'` produisent maintenant des arêtes explicites `re_exports`, pour que les barrels Next.js / monorepo ne s'affichent plus avec 0 import.
- **Drapeau `--exclude PATTERN`** pour `scan` / `sync`, plus repli automatique sur `.gitignore` lorsque `.codebeaconignore` est absent.
- **`codebeacon install --project [PATH]`** — installe le skill `/codebeacon` dans `<PATH>/.claude/` plutôt que `~/.claude/`, pour permettre aux équipes de figer la version du SKILL.md par dépôt.
- **Le wiki s'auto-répare** — les exécutions `--update` suppriment maintenant les fichiers `wiki/<project>/{controllers,services,entities,components}/*.md` dont le nœud de graphe n'existe plus.
- **Garde anti-rétrécissement relâchée pour les suppressions explicites** — en mode `--update`, l'écriture d'un `beacon.json` plus petit n'est plus refusée si le cache a déjà tenu compte des fichiers supprimés ; la garde s'applique toujours en cas de corruption silencieuse.
- **Fusion union des déclarations multi-fichiers** — les `extension Foo` Swift, les `partial class` C# et les classes Ruby réouvertes voient leurs `fields` / `methods` fusionnés dans un unique nœud canonique au lieu d'être écrasés.
- **Recherche renforcée** — `BeaconIndex` utilise `casefold()`, ainsi l'allemand `ß`, le turc `i/İ`, le grec `σ/ς` et les libellés CJK matchent correctement.
- **Contexte sémantique enrichi** — chaque chunk de tâche transporte désormais les appelants / appelés du graphe via `neighbors`, ce qui garde le LLM ancré sur de vrais libellés. `SKILL.md` ajoute **Step 0 — Constrained query expansion** pour que les flux `/codebeacon query` n'inventent pas de tokens fantômes.
- **Garde « zéro rendement » de `semantic-apply`** — si tous les chunks ont archivé 0 arête, la CLI termine avec exit 1 pour que la CI détecte les échecs silencieux du LLM.
- **ArkTS (`.ets`) et sécurité worktree** — `.ets` est collecté ; les dossiers `worktrees/` imbriqués sont ignorés pour éviter l'indexation en double des worktrees liées.

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
