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
- **다양한 출력 형식** — JSON 지식 그래프, 마크다운 위키, Obsidian 볼트, AI 컨텍스트 맵, MCP 서버
- **커뮤니티 감지** — Leiden/Louvain 클러스터링으로 실제 아키텍처 경계 도출
- **증분 캐시** — SHA-256 기반; 마지막 스캔 이후 변경된 파일만 재추출
- **제로 설정** — 프레임워크와 언어 자동 감지; 반복 실행을 위한 `codebeacon.yaml` 자동 생성
- **딥다이브 모드** — `--deep-dive`는 각 서브 프로젝트에 개별 `.codebeacon/` + `CLAUDE.md`를 생성; 어느 서브 프로젝트 폴더에서든 `codebeacon scan . --update`를 실행하면 워크스페이스의 모든 프로젝트가 자동으로 업데이트됨

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
    beacon.json          ← 전체 지식 그래프 (노드-링크 JSON, 쿼리 가능)
    REPORT.md            ← 갓 노드, 놀라운 연결, 허브 파일
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
/codebeacon                  # 현재 디렉토리 스캔
/codebeacon /path/to/project # 특정 경로 스캔
/codebeacon sync             # codebeacon.yaml 기반 재스캔
```

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
codebeacon scan . --update                # 증분: 변경된 파일만 재추출
codebeacon scan . --wiki-only             # 재추출 건너뛰고 기존 beacon.json에서 위키/obsidian/컨텍스트 맵 재생성
codebeacon scan . --obsidian-dir <path>   # Obsidian 볼트를 커스텀 위치에 저장
codebeacon scan . --semantic              # LLM 시맨틱 추출 활성화
codebeacon scan . --list-only             # 프레임워크 감지만, 추출 제외
codebeacon scan /workspace --deep-dive    # 프로젝트별 + 통합 워크스페이스 출력

# 설정 기반 모드
codebeacon init [path]                    # codebeacon.yaml 자동 생성
codebeacon sync                           # codebeacon.yaml 기반 실행
codebeacon sync --config <file>           # 특정 설정 파일 사용

# 지식 그래프 쿼리 (예정)
codebeacon query <term>                   # 노드와 엣지 검색
codebeacon path <source> <target>         # 두 노드 간 최단 경로

# 통합
codebeacon serve [--dir .codebeacon]      # MCP 서버 시작 (stdio)
codebeacon install                        # Claude Code 스킬 설치
```

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
  enabled: false               # --semantic 플래그로 오버라이드

deep_dive: false               # true로 설정하면 프로젝트별 출력 생성
```

### .codebeaconignore

프로젝트 루트에 `.codebeaconignore` 파일을 두면 스캔에서 특정 디렉토리나 파일을 제외할 수 있습니다. `.gitignore`와 동일한 문법 — 한 줄에 패턴 하나, `#`은 주석.

```
# .codebeaconignore
generated/
build/
*.generated.ts
fixtures/
```

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

모든 처리는 로컬에서 이루어집니다. 소스코드는 외부로 전송되지 않습니다.

- tree-sitter AST 파싱은 프로세스 내에서만 실행
- 텔레메트리, 분석, 일반 동작 중 네트워크 호출 없음
- `--semantic` 플래그(기본 비활성화)는 두 가지 추출 모드를 활성화합니다:
  1. **구조화된 주석 파싱** (LLM 불필요) — Javadoc(`@see`, `{@link}`), Python 독스트링(`:class:`, `:func:`), JSDoc(`@see`, `@param` 타입)에서 크로스 레퍼런스 추론
  2. **LLM 추론** (선택 사항) — `ANTHROPIC_API_KEY` 설정 시 Claude API로 코드 발췌문을 전송하여 심층 관계 추론; 명시적으로 활성화할 때만 사용됩니다

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
