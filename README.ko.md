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
  소스코드 AST 분석 및 AI 컨텍스트 생성 — 통합 멀티 프레임워크 지식 그래프
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## 왜 codebeacon인가?

AI 코딩 세션을 새로 열 때마다 어시스턴트는 백지 상태에서 시작합니다. 라우트 구조도, 서비스 레이어도, 엔티티 모델도, 마이크로서비스 간 호출 관계도 모릅니다. 결국 세션마다 파일을 붙여넣고, 구조를 설명하고, 컨텍스트를 다시 세팅하는 데 상당한 시간을 씁니다.

기존 도구들은 이 문제를 부분적으로만 해결합니다. 라우트 분석기는 컨트롤러를 파악하지만 서비스 의존성을 놓칩니다. 지식 그래프 도구는 관계를 포착하지만 API 표면은 무시합니다. 결국 두 도구를 동시에 실행하고, 출력을 수동으로 이어 붙이고, 코드베이스가 바뀔 때마다 반복해야 합니다.

**codebeacon은 이 두 접근 방식을 하나의 CLI로 통합합니다.** 명령 하나로 전체 코드베이스를 tree-sitter AST로 분석하고, 파일 간 의존성 주입을 해결하고, 아키텍처 클러스터를 감지한 뒤, `CLAUDE.md`, `.cursorrules`, `AGENTS.md`에 바로 쓸 수 있는 컨텍스트 맵을 생성합니다. AI 어시스턴트가 세션 시작부터 코드베이스를 이미 알고 있는 상태가 됩니다.

---

## 주요 기능

- **통합 파이프라인** — 라우트/컨트롤러 분석 + 지식 그래프를 하나의 도구로, 수동 연결 불필요
- **27개 프레임워크, 9개 언어** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor
- **tree-sitter 기반** — 정규식이 아닌 구조적 AST 파싱; 언어 그래머 기본 포함
- **2-패스 DI 해결** — Pass 1에서 로컬 AST 노드 추출, Pass 2에서 전역 심볼 테이블로 Interface → Implementation 매핑 해결
- **Wave 병합 아키텍처** — 파일을 병렬 청크로 처리 후 전역 병합; 대형 모노레포도 메모리 폭발 없이 처리
- **다양한 출력 형식** — JSON 지식 그래프, 마크다운 위키, Obsidian 볼트, AI 컨텍스트 맵, MCP 서버, 인터랙티브 HTML
- **시각적 탐색** — `beacon.html`(D3 접이식 트리)과 `callflow.html`(커뮤니티별 Mermaid 아키텍처 다이어그램)이 모든 스캔에서 자동 재생성됨
- **커뮤니티 감지** — Leiden/Louvain 클러스터링으로 실제 아키텍처 경계 도출
- **증분 캐시** — SHA-256 + mtime/size 빠른 경로; Obsidian/iCloud/Nextcloud처럼 mtime만 튀는 경우는 재추출 트리거하지 않음
- **신뢰도 승격** — 명시적 import가 바인딩을 증명하면 파일 간 `calls` 엣지가 INFERRED에서 EXTRACTED로 자동 승격
- **안전한 쓰기** — beacon.json에는 shrink guard(부분 실행이 완전한 그래프를 덮어쓰지 못함)와 `built_at_commit` 스탬프가 있어 REPORT.md가 현재 HEAD 대비 stale 상태를 표시
- **멀티 개발자 친화적** — `codebeacon hook install`은 `beacon.json`용 git merge driver와 post-commit 증분 재빌드 훅을 등록해, 같은 브랜치에서 두 개발자가 동시에 스캔해도 머지 충돌이 발생하지 않음
- **하드닝된 출력** — YAML frontmatter와 MCP 레이블은 U+2028/U+2029, C0 컨트롤, bidi 마크를 모두 제거; 소스 코드의 악의적 식별자가 Obsidian YAML 파서를 깨뜨리거나 LLM 에이전트 컨텍스트에 컨트롤 시퀀스를 주입할 수 없음
- **gitignore 호환 `.codebeaconignore`** — last-match-wins, `!` 부정, 디렉토리 패턴(`build/`), 앵커 패턴(`/secrets.txt`), 트레일링 공백 처리
- **제로 설정** — 프레임워크와 언어 자동 감지; 반복 실행을 위한 `codebeacon.yaml` 자동 생성
- **딥다이브 모드** — `--deep-dive`는 각 서브 프로젝트에 개별 `.codebeacon/` + `CLAUDE.md`를 생성; 어느 서브 프로젝트 폴더에서든 `codebeacon scan . --update`를 실행하면 워크스페이스의 모든 프로젝트가 자동으로 업데이트됨
- **워크스페이스 자동 재발견** — `scan`/`sync` 실행마다 워크스페이스를 다시 훑어 `codebeacon.yaml`에 없는 신규 프로젝트를 자동으로 yaml에 추가한 뒤 추출 시작 — 새로 추가된 서브 프로젝트가 조용히 누락되지 않음; 수동으로 yaml을 큐레이션 중이라면 `--no-rediscover`로 옵트아웃

---

## 빠른 시작

```bash
pip install codebeacon

codebeacon scan .
```

끝입니다. codebeacon이 프로젝트 유형을 감지하고, 라우트/서비스/엔티티/컴포넌트를 추출하고, 지식 그래프를 구축한 뒤 모든 결과를 `.codebeacon/`에 씁니다.

멀티 프로젝트 워크스페이스:

```bash
codebeacon scan /path/to/workspace   # 모든 프로젝트 자동 감지, codebeacon.yaml 생성
codebeacon sync                      # 이후 실행은 설정 파일 기반
```

---

## 지원 프레임워크

| 언어 | 프레임워크 |
|------|-----------|
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

## 아키텍처

codebeacon은 2-패스 추출 파이프라인으로 동작합니다:

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         로컬 AST            심볼 테이블   교차 언어   HTTP API
                         청크 단위           매핑 해결     아티팩트    공유 DB
                         (Pass 1)            (Pass 2)     필터링     엔티티 엣지
```

**Pass 1 — Wave 추출:** `ThreadPoolExecutor`로 파일을 병렬 청크 처리. 각 파일에서 라우트, 서비스, 엔티티, 컴포넌트, 의존성 등 5개 추출기를 실행합니다. 증분 재스캔을 위해 SHA-256으로 결과를 캐시합니다.

**Pass 2 — 그래프 구축:** 모든 Wave 결과를 병합합니다. 전역 심볼 테이블이 미해결 의존성 주입 참조를 해결합니다 — Spring의 암묵적 Bean 연결이나 TypeScript 주입 토큰 같은 단일 패스 도구가 놓치는 Interface→Implementation 매핑을 처리합니다. 빌드 아티팩트, 교차 언어 허위 임포트, 잘못된 교차 서비스 엣지를 필터링합니다.

**후처리:** HTTP API 엣지가 프론트엔드 URL 호출과 매칭되는 백엔드 라우트를 연결합니다. 커뮤니티 감지(Leiden → Louvain → 연결 컴포넌트 폴백)가 그래프를 아키텍처 클러스터로 분할합니다. 구조 보고서에서 갓 노드, 놀라운 교차 클러스터 연결, 허브 파일을 식별합니다.

---

## 출력 구조

스캔 후 컨텍스트 맵 파일은 프로젝트 루트에서 업데이트되고(기존 사용자 내용 보존), 지식 그래프는 `.codebeacon/`에 생성됩니다:

```
project-root/
  CLAUDE.md              ← AI 컨텍스트 맵 (codebeacon 블록 병합; 사용자 내용 유지)
  .cursorrules           ← Cursor IDE 컨텍스트 (동일 병합 방식)
  AGENTS.md              ← OpenAI Agents / Codex 컨텍스트 (동일 병합 방식)
  .codebeacon/
    beacon.json          ← 전체 지식 그래프; `meta.built_at_commit` 임베드
    beacon.html          ← D3 접이식 트리 뷰어 (브라우저에서 열기)
    callflow.html        ← 커뮤니티별 Mermaid 콜플로우 다이어그램
    REPORT.md            ← 갓 노드, 놀라운 연결, 허브 파일, 신선도
    wiki/
      index.md           ← 전역 인덱스 (~200 토큰)
      overview.md        ← 플랫폼 통계 + 교차 프로젝트 연결
      routes.md          ← 전체 라우트 테이블
      cross-project/
        connections.md   ← 교차 서비스 엣지
      <project>/
        index.md
        routes.md
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian 볼트 (그래프 노드당 노트 1개)
    semantic/
      original.jsonl     ← 적용된 모든 AI-시맨틱 결과의 영구 아카이브
                           (재스캔 시 스킵됨, 다시 task 로 발행되지 않음)
    semantic-tasks.jsonl     ← pending AI-시맨틱 배치
                               (`semantic-prepare` 와 `semantic-apply` 사이에만 존재)
    semantic-results.jsonl   ← 에이전트가 작성한 결과 (동일 라이프사이클)
```

### 딥다이브 모드

`--deep-dive`를 사용하면 각 서브 프로젝트에도 자체 `.codebeacon/` 디렉토리와 `CLAUDE.md`가 생성되어, 서브 프로젝트 내에서 열린 AI 세션이 프로젝트별 전체 컨텍스트를 갖게 됩니다:

```
workspace/
  CLAUDE.md                   ← 통합 (모든 프로젝트)
  .cursorrules
  AGENTS.md
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← 통합 지식 그래프
    beacon.json
    wiki/
    obsidian/
  api-server/
    CLAUDE.md                 ← api-server 전용
    .codebeacon/              ← api-server 그래프
      beacon.json
      wiki/
      obsidian/
  frontend/
    CLAUDE.md                 ← frontend 전용
    .codebeacon/              ← frontend 그래프
      beacon.json
      wiki/
      obsidian/
```

Claude Code는 `CLAUDE.md`를 계층적으로 로드하므로, `api-server/`에서 세션을 열면 상위 워크스페이스 개요와 프로젝트별 세부 정보가 모두 로드됩니다.

초기 스캔 이후 어느 서브 프로젝트에서든 업데이트:

```bash
# 초기 딥다이브 스캔
codebeacon scan /workspace --deep-dive

# 이후 어느 서브 프로젝트에서든 — 부모 설정을 찾아 모든 프로젝트 업데이트
cd /workspace/api-server
codebeacon scan . --update
```

---

## AI 통합

### Claude Code 스킬 (`/codebeacon`)

codebeacon을 Claude Code 슬래시 명령어로 설치합니다:

```bash
pip install codebeacon
codebeacon install
```

`SKILL.md`를 `~/.claude/skills/codebeacon/`에 복사하고 `/codebeacon` 트리거를 `~/.claude/CLAUDE.md`에 등록합니다. Claude Code 세션을 재시작한 후 `/codebeacon`을 입력하면 현재 디렉토리를 스캔합니다.

```
/codebeacon                       # 현재 디렉토리 스캔 + AI-시맨틱 자동
/codebeacon /path/to/project      # 특정 경로 스캔  + AI-시맨틱 자동
/codebeacon sync                  # codebeacon.yaml 기반 재스캔 + AI-시맨틱 자동
/codebeacon <path> --no-semantic  # 스캔만, AI-시맨틱 단계 스킵
/codebeacon <path> --wiki-only    # 기존 beacon.json 에서 wiki 만 재생성
/codebeacon semantic-prepare      # 새 tasks 파일만 발행
/codebeacon semantic-apply        # 에이전트가 이미 작성한 결과 파일 머지
/codebeacon serve <path>          # .codebeacon/ 을 가리키는 MCP 서버 시작
/codebeacon query <term>          # 그래프 검색
/codebeacon path <src> <tgt>      # 최단 경로
```

기본적으로 `scan` 과 `sync` 호출은 마지막에 **AI-시맨틱** 파이프라인을 자동 실행합니다 ([AI-시맨틱 보강](#ai-시맨틱-보강-codebeacon-스킬에서-자동) 섹션 참고). 에이전트는 Claude Code 세션이 **현재 실행 중인 모델**을 그대로 사용 — Opus, Sonnet, Haiku — codebeacon 은 절대 모델을 하드코딩하지 않고 API 키도 필요 없습니다.

### MCP 서버

codebeacon을 MCP 서버로 실행하면 MCP 호환 클라이언트에서 지식 그래프를 직접 조회할 수 있습니다.

**1단계 — 프로젝트 스캔:**
```bash
codebeacon scan .
```

**2단계 — MCP 클라이언트 설정에 추가:**

**Claude Code** (프로젝트 루트의 `.claude.json` 또는 전역 `~/.claude.json`):
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

**연결 후 사용 가능한 MCP 도구:**

| 도구 | 설명 |
|------|------|
| `beacon_wiki_index` | 전체 프로젝트 개요 (라우트, 서비스, 엔티티 수) |
| `beacon_wiki_article` | 경로로 특정 위키 문서 읽기 |
| `beacon_query` | 레이블 부분 문자열로 노드 검색 |
| `beacon_path` | 두 노드 간 최단 의존성 경로 |
| `beacon_blast_radius` | 업스트림 호출자 + 다운스트림 영향 노드 |
| `beacon_routes` | 전체 HTTP 라우트 목록 (프로젝트 필터 가능) |
| `beacon_services` | 전체 서비스/클래스 목록 (프로젝트 필터 가능) |

---

## 설치 옵션

```bash
pip install codebeacon              # 언어 그래머 기본 포함
pip install codebeacon[cluster]     # + Leiden 커뮤니티 감지 (graspologic)
pip install --upgrade codebeacon    # 최신 버전 + 의존성 함께 업데이트
```

Java, Kotlin, Python, JavaScript, TypeScript, Go, Ruby, PHP, C#, Rust, Swift, HTML, Svelte 파서가 기본 설치됩니다 — 별도 플래그 불필요.

---

## CLI 레퍼런스

```bash
# 프로젝트 또는 워크스페이스 스캔
codebeacon scan <path> [옵션]
codebeacon scan .                         # 현재 디렉토리
codebeacon scan /workspace                # 워크스페이스 루트 (멀티 프로젝트)
codebeacon scan . --update                # 증분: mtime/size 빠른 경로 + 콘텐츠 해시 폴백
codebeacon scan . --wiki-only             # 재추출 건너뛰고 기존 beacon.json에서 위키/obsidian/컨텍스트 맵 재생성
codebeacon scan . --obsidian-dir <path>   # Obsidian 볼트를 커스텀 위치에 저장
codebeacon scan . --semantic              # 구조화 주석 시맨틱 추출 활성화 (Javadoc/JSDoc/docstring 참조)
codebeacon scan . --list-only             # 프레임워크 감지만, 추출 제외
codebeacon scan /workspace --deep-dive    # 프로젝트별 + 통합 워크스페이스 출력

# 설정 기반 모드
codebeacon init [path]                    # codebeacon.yaml 자동 생성
codebeacon sync                           # codebeacon.yaml 기반 실행 (신규 워크스페이스 프로젝트 자동 추가)
codebeacon sync --config <file>           # 특정 설정 파일 사용
codebeacon sync --no-rediscover           # 신규 프로젝트 자동 추가 비활성화 (수동 큐레이션 모드)

# AI-시맨틱 보강 (LLM 작업은 에이전트가, 부기는 codebeacon이 담당)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N]
                                          # 시맨틱 아카이브를 fresh beacon.json에 재적용 후,
                                          # 아카이브에 없는 NEW 후보(god-node 폴더 + unresolved 타겟)
                                          # 만 골라 .codebeacon/semantic-tasks.jsonl 작성
codebeacon semantic-apply   [--dir .codebeacon]
                                          # .codebeacon/semantic-results.jsonl 을 읽어
                                          # INFERRED references 엣지로 beacon.json 에 머지,
                                          # .codebeacon/semantic/original.jsonl 아카이브에 적재,
                                          # pending 파일 정리, wiki/obsidian/컨텍스트 맵 재생성

# 지식 그래프 쿼리
codebeacon query <term> [--dir .codebeacon] [--limit N]   # 라벨 부분 문자열로 노드 검색
codebeacon path <source> <target> [--dir .codebeacon]     # 최단 의존성 경로

# 멀티 개발자 지원 (git plumbing)
codebeacon hook install [path]            # merge driver + post-commit 증분 재빌드 설치
codebeacon merge-driver <base> <cur> <other>  # `hook install` 후 git이 자동 호출; beacon.json union 머지

# 통합
codebeacon serve [--dir .codebeacon]      # MCP 서버 시작 (stdio)
codebeacon install                        # Claude Code 스킬 설치
```

---

## AI-시맨틱 보강 (`/codebeacon` 스킬에서 자동)

tree-sitter 파싱은 AST에 있는 것을 찾습니다. **AI-시맨틱**은 **주석에만** 있는 것을 찾습니다 — Javadoc 의 `@see UserService`, Python 독스트링의 `:class:`OrderRepository``, 라우트 핸들러 옆에 문서화된 계약상 참조들. codebeacon 은 이를 두 계층으로 다룹니다:

| 계층 | 플래그 | 비용 | 잡아내는 것 |
|---|---|---|---|
| 구조화 주석 파싱 | `--semantic` | 무료, 로컬, LLM 불필요 | Javadoc `@see` / `{@link}`, JSDoc `@see` / `@param` 타입, Python `:class:` / `:func:` / `See Also` |
| **AI-시맨틱** | `/codebeacon` 스킬에서 자동 | 에이전트의 **현재 모델** 사용 — **별도 API 키 불필요** | 정규식이 못 잡는 클래스/타입/서비스 참조 (자연어 산문, 간접 언급, 타입 힌트 전용 등) |

CLI 자체는 LLM API 호출을 **하지 않습니다**. AI-시맨틱 계층은 의도적으로 `/codebeacon` Claude Code 스킬 안에서 **실행 중인 에이전트가 소유**합니다 — 그래야 사용자가 고른 모델 (Opus / Sonnet / Haiku / 무엇이든) 이 그대로 사용되고, codebeacon 자체는 `ANTHROPIC_API_KEY` 도 클라우드 설정도 필요하지 않습니다.

### 실행 흐름

Claude Code 에서 `/codebeacon` 호출 시:

1. `scan` / `sync` 가 AST 로부터 `beacon.json` 빌드 (LLM 호출 없음).
2. `codebeacon semantic-prepare` 가 이전 아카이브를 새 그래프에 재적용한 뒤, **신규 후보만** 담긴 `.codebeacon/semantic-tasks.jsonl` 작성 — 점수가 높은 파일 (unresolved 타겟 엣지 + god-node 폴더) 중 한 번도 처리된 적 없는 것.
3. 스킬이 tasks 파일을 순회합니다. 각 라인마다 에이전트(현재 세션의 모델)가 `excerpt` 필드를 읽고 추론된 references 를 인라인으로 반환. 결과는 `.codebeacon/semantic-results.jsonl` 에 기록.
4. `codebeacon semantic-apply` 가 결과를 `INFERRED references` 엣지로 `beacon.json` 에 머지하고, **`.codebeacon/semantic/original.jsonl`** (영구 아카이브) 에 append, pending 파일 정리, wiki + obsidian + 컨텍스트 맵 재생성.
5. 다음 스캔: `semantic-prepare` 가 아카이브를 새 그래프에 재적용 (재스캔으로 인해 과거 추론이 사라지지 않도록) 한 뒤, 마지막 아카이브 이후 **새로 발견된 후보만** tasks 파일에 담음. 이미 처리된 파일은 `task_id` (SHA1(`file_path|node_id`)) 로 스킵.

→ 증분 + 멱등 보강. 같은 파일을 두 번 분석하지 않고, 누적된 AI 시그널은 매 재스캔을 살아남습니다.

### 직접 CLI 사용

스킬 없이 (예: CI) 같은 두 명령으로 직접 운영하고 `semantic-results.jsonl` 을 본인이 채울 수 있습니다:

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50

# 이제 .codebeacon/semantic-results.jsonl 을 직접 작성; 각 라인:
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### 비활성화

스킬 호출 시 `--no-semantic` (또는 `--wiki-only`, `--list-only`) 을 넘기면 AI 단계가 완전히 건너뜁니다. `--semantic` 플래그를 `scan` / `sync` 에 넘기면 구조화 주석 계층은 그대로 동작합니다.

---

## 시각적 탐색

모든 스캔은 `beacon.json` 옆에 self-contained HTML 파일 2개를 함께 작성합니다:

```
.codebeacon/beacon.html      # D3 v7 접이식 트리 — 브라우저에서 바로 열기
.codebeacon/callflow.html    # 커뮤니티별 Mermaid 아키텍처 다이어그램
```

빌드도, 정적 서버도, 복사-붙여넣기도 불필요. 파일을 열고 프로젝트 → 타입 → 노드 순서로 클릭해서 펼치고, 호버하면 소스 경로와 차수가 표시됩니다. `callflow.html`은 그래프를 커뮤니티별로 그룹화하고 각각을 Mermaid 플로우차트로 렌더링하며, 커뮤니티 외부 출력 엣지는 접힌 테이블에 나열됩니다.

---

## 멀티 개발자 워크플로

두 개발자가 같은 브랜치에서 `codebeacon scan`을 실행하면 약간 다른 `beacon.json` 파일이 나옵니다 — 전통적인 머지 충돌 원인. `codebeacon hook install`이 해결합니다:

```bash
codebeacon hook install            # 저장소 루트에서
```

이 명령은 다음을 등록합니다:

- 두 개의 `beacon.json` 파일을 하나로 union 머지하는 **git merge driver** (노드는 ID로, 엣지는 `(source, target, relation)`로 중복 제거)
- `*beacon.json`을 드라이버에 연결하는 `.gitattributes` 항목
- 그래프가 커밋과 멀어지지 않도록 백그라운드에서 `codebeacon scan . --update`를 실행하는 **post-commit 훅**. 출력은 `~/.cache/codebeacon-rebuild.log`로 향함

머지 드라이버는 항상 0으로 종료 — 그래프 재생성은 실제 머지를 절대 막지 않습니다.

---

## 안전성 보장

매 성공적인 스캔에서 라이터가 강제하는 불변식들:

| 가드 | 방지하는 상황 |
|---|---|
| **Shrink guard** | 부분 추출 실패나 중단된 실행이 더 큰 완전한 `beacon.json`을 덮어쓸 수 없음. API에서 `force=True`로 우회 가능 |
| **원자적 쓰기** | `beacon.json`은 `os.replace`로 작성되어, 파일은 완전하거나 손대지 않은 상태 둘 중 하나 — 반쯤 작성된 그래프 없음 |
| **`built_at_commit` 스탬프** | `beacon.json`은 `meta.built_at_commit` (풀 SHA)를 임베드하고 `REPORT.md`는 short SHA를 표시. HEAD가 그 시점보다 앞서 있으면 한 줄짜리 해결 힌트와 함께 `⚠ stale`로 표시 |
| **Frontmatter / 라벨 하드닝** | YAML frontmatter 값은 single-quoted + U+2028, U+2029, 탭, C0 컨트롤 이스케이프; MCP 도구 출력은 모든 라벨을 동일한 sanitizer로 통과시킴. 소스 코드의 악의적 식별자가 Obsidian YAML 파서를 깨거나 LLM 에이전트 컨텍스트에 컨트롤 시퀀스를 주입할 수 없음 |

---

## 설정

`codebeacon init`으로 `codebeacon.yaml`을 생성하거나 직접 작성합니다:

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # 선택 사항: 생략 시 자동 감지

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
  chunk_size: 300              # 청크당 파일 수
  max_parallel: 5              # 병렬 스레드 수

semantic:
  enabled: false               # 구조화 주석 추출; --semantic 플래그로 오버라이드.
                               # AI-시맨틱은 이 키에 없습니다 — 위의 "AI-시맨틱 보강" 참고
                               # (codebeacon 자체가 아니라 /codebeacon 스킬이 트리거).

deep_dive: false               # true로 설정하면 프로젝트별 출력 생성
```

### .codebeaconignore

프로젝트 루트에 `.codebeaconignore` 파일을 두면 스캔에서 특정 디렉토리나 파일을 제외할 수 있습니다. `.gitignore`와 동일한 시멘틱 — last-match-wins, `!` 부정, 앵커 패턴(`/foo`), 디렉토리 전용 패턴(`build/`), 주석:

```
# .codebeaconignore

# 디렉토리
build/
generated/
fixtures/

# 루트에만 앵커
/scripts/local-only.ts

# 글로브 패턴
*.gen.ts
**/snapshots/**

# build/이 무시되더라도 특정 파일은 다시 포함
!build/manifest.ts
```

`!pattern`은 이전에 무시된 경로를 다시 포함시킵니다; 뒤의 규칙이 앞의 규칙을 덮어씁니다. 워커는 룰셋에 매칭되는 디렉토리는 가지치기하지만, `!` 부정 규칙이 있을 때는 가지치기를 보류하고 각 파일별로 검사합니다.

---

## 비교

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| 라우트 / 컨트롤러 분석 | ✅ | ❌ | ✅ |
| 서비스 / DI 그래프 | 부분적 | ✅ | ✅ |
| Interface → Impl 해결 | ❌ | ❌ | ✅ |
| 엔티티 / ORM 모델 추출 | ✅ | ❌ | ✅ |
| 프론트엔드 컴포넌트 분석 | ✅ | ❌ | ✅ |
| 커뮤니티 감지 | ❌ | ✅ | ✅ |
| Obsidian 볼트 내보내기 | ❌ | ✅ | ✅ |
| MCP 서버 | ✅ | ❌ | ✅ |
| AI 컨텍스트 맵 (CLAUDE.md) | ✅ | ✅ | ✅ |
| 멀티 프로젝트 워크스페이스 | 부분적 | ❌ | ✅ |
| Python 기반 | ❌ | ✅ | ✅ |

codebeacon은 두 도구의 대체재가 아니라 통합입니다 — 공유 추출 및 그래프 레이어 위에서 두 도구가 각각 하는 일의 합집합을 구현합니다.

---

## 벤치마크

| 코드베이스 | 스택 | 파일 수 | 노드 | 엣지 | 커뮤니티 | 스캔 시간 |
|-----------|------|--------|------|------|---------|---------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3개 프로젝트) | 444 | 382 | 553 | 175 | ~12s |

---

## 프라이버시 & 보안

모든 AST 처리는 로컬에서 이루어집니다. codebeacon 을 직접 실행할 때 소스코드는 기기 밖으로 나가지 않습니다.

- tree-sitter AST 파싱은 프로세스 내에서만 실행
- 텔레메트리, 분석, 일반 동작 중 네트워크 호출 없음
- CLI 자체는 **LLM 제공자를 절대 호출하지 않습니다** — codebeacon 패키지에는 API 클라이언트도, 키 처리도, 모델 이름도 없습니다
- `--semantic` 은 **구조화된 주석 파싱만** 활성화합니다 (Javadoc `@see` / `{@link}`, JSDoc `@see` / `@param` 타입, Python `:class:` / `:func:` / `See Also`). 100% 로컬.
- **AI-시맨틱** (LLM 기반 심층 계층) 은 `/codebeacon` Claude Code 스킬이 트리거합니다. 에이전트가 `semantic-tasks.jsonl` 을 읽고 **현재 세션의 모델**로 분석을 수행한 뒤 `semantic-results.jsonl` 을 씁니다. Python CLI 는 태스크 배치 준비와 결과 머지만 담당하며, 어떤 모델이 쓰였는지조차 모릅니다. 스킬에 `--no-semantic` 을 넘기면 LLM 단계가 완전히 건너뜁니다.

---

## 기여하기

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

새 프레임워크 지원을 추가하는 가장 쉬운 진입점은 `codebeacon/extract/queries/`에 tree-sitter 쿼리 파일을 작성하는 것입니다. 전체 가이드는 [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md)를 참고하세요 — 문법 설정, `.scm` 쿼리 문법, 캡처 명명 규칙, 새 추출기 연결 방법을 안내합니다.

기여 환영합니다: 새 프레임워크 쿼리, 언어 파서, 출력 형식, 벤치마크 데이터셋.

---

## 라이선스

MIT — [LICENSE](LICENSE) 파일 참고.

---

## 감사의 말

구조적 AST 파싱을 위한 [tree-sitter](https://tree-sitter.github.io/tree-sitter/), 그래프 연산을 위한 [NetworkX](https://networkx.org/), Leiden 커뮤니티 감지를 위한 [graspologic](https://microsoft.github.io/graspologic/)을 기반으로 구축되었습니다.

[codesight](https://github.com/Houseofmvps/codesight)와 [graphify](https://github.com/safishamsi/graphify)의 상호 보완적 접근 방식에서 영감을 받았습니다.
