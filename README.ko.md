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

## 0.6.8 새 소식

업스트림 v0.8.41–v0.9.3(보고된 이슈 #1568까지)에 대한 graphify-패리티 감사입니다. 모든 후보를 수정 전에 codebeacon에서 실제로 재현하고 적대적 리뷰 패스로 재검증했으며, **7개의 실제 버그**를 확인했습니다 — 데이터 손실 함정과 프라이버시 유출이 핵심입니다.

- **`--obsidian-dir`가 더 이상 사용자 노트를 삭제하지 않음** — 기존 Obsidian 볼트를 가리키면 재생성 전에 그 아래 *모든* `.md`를 지워서 실제 볼트를 통째로 날릴 수 있었습니다. 이제 codebeacon이 소유하지 않은 디렉터리는 거부하고(완전히 비어 있거나 `.codebeacon-vault.json` 마커를 가진 디렉터리만 채택), 삭제 대신 명확한 메시지와 함께 내보내기를 건너뜁니다.
- **`.codebeaconignore`가 `.gitignore`를 조용히 무력화하지 않음** — `.codebeaconignore`를 추가하면 저장소의 `.gitignore`를 *대체*해서, `.gitignore`로만 제외된 파일(중립적 이름의 `prod-dump.sql`, `customer-data.*`)이 커밋되는 `.codebeacon/` 산출물에 인덱싱될 수 있었습니다. 이제 둘을 병합하며(충돌 시 `.codebeaconignore` 우선), 추가해도 *더 많이* 제외할 수만 있습니다.
- **커밋되는 산출물에 머신 절대 경로 없음** — 엣지/링크의 `source_file`(`beacon.json`의 대부분)과 wiki/obsidian 노트의 `Source:` 줄이 절대 경로 `/Users/you/...`를 유지해서 인덱스가 이식성이 없고 로컬 경로가 유출됐습니다. 이제 모두 프로젝트 상대 경로입니다(엣지 포함, 교차 프로젝트 `shares_db_entity` 파일도).
- **다른 디렉터리의 동일 이름 심볼이 서로의 노트를 덮어쓰지 않음** — wiki/obsidian 파일명이 대소문자 구분 없이 라벨에서 생성돼, macOS/Windows에서 `UserService`와 `userService`가 충돌해 한쪽 노트가 조용히 사라졌습니다. 이제 파일명이 충돌-솔팅 + 대소문자 폴딩되며, 구두점만 있는 라벨(`@`)은 깨진 `@.md` 대신 `unnamed`로 대체됩니다.
- **손상된 `beacon.json`이 더 이상 크래시를 내지 않음** — `codebeacon affected`, MCP 서버, `--wiki-only` 실행이 이제 손상/절단된 그래프를 백업하고 원시 트레이스백 대신 명확한 "scan 재실행" 메시지를 보여줍니다.
- **더 많은 React 컴포넌트 캡처** — `react.scm`이 함수식 컴포넌트(`const X = function() {…}`), bare-import HOC(`React.` 접두 없는 `const X = forwardRef(…)`), 비-export `function X()` 컴포넌트를 놓쳤습니다. 이제 셋 다 추출됩니다.
- **wiki 링크가 깨지지 않음** — 작성되지 않은 페이지로의 링크는 일반 텍스트로 강등되고, 형제 버킷의 문서로 가는 링크(서비스 → 엔티티)는 없는 파일을 가리키는 대신 올바른 상대 경로로 복구됩니다.

---

## 0.6.7 새 소식

0.6.6 graphify-패리티 감사의 후속 작업: grammar 드리프트가 이제 조용히 묻히지 않고 명시적으로 실패하며, ignore 파일의 부정 규칙이 더 이상 스캔을 느리게 하지 않습니다.

- **Grammar 드리프트가 "조용한 빈 그래프"가 아니라 명시적 실패로** — tree-sitter 쿼리가 지원해야 할 grammar에 대해 컴파일에 실패하면(향후 grammar 버전업의 노드 타입 개명 등), `run_query`가 이제 예외를 던져 해당 파일이 조용히 0개 추출되는 대신 `ExtractionFailure`로 기록됩니다. 0.6.6의 상한 핀 + "모든 쿼리가 자신이 지원한다고 선언한 모든 grammar에 대해 컴파일된다" 테스트와 함께, 드리프트가 세 가지 독립적인 방법으로 잡힙니다.
- **`.codebeaconignore`의 단일 `!` 부정 규칙이 더 이상 전체 트리 순회를 강제하지 않음** — 부정 규칙 하나가 어디에 있든 디렉터리 가지치기를 *전역적으로* 비활성화해서, 그 부정 규칙이 안에서 아무것도 되살릴 수 없는 경우에도 스캐너가 모든 제외 디렉터리(`node_modules`, `build` 등)로 내려갔습니다. 이제 각 무시된 디렉터리는 부정 규칙이 실제로 *그 아래* 파일을 되살릴 수 있을 때만 순회되며, 무관한 `!` 규칙은 비용이 들지 않습니다.
- **Ignore 글롭을 한 번만 컴파일** — gitignore 스타일 매처가 경로를 검사할 때마다 정규식을 다시 만드는 대신 패턴별 컴파일된 정규식을 메모이즈합니다(큰 ignore 파일을 가진 깊은 트리에서 탐색 속도 향상). 동작 의미는 동일합니다.

---

## 0.6.6 새 소식

업스트림 v0.8.37–v0.8.40(및 #1362까지 리포트된 이슈)에 대한 graphify-패리티 감사: 32개 후보를 "검증 후 적대적 반박" 방식으로 훑어 **실제 버그 6개**를 확정했습니다. 핵심 — 프레임워크 추출기 3개가 조용히 *아무것도* 만들지 못하고 있었습니다.

- **TypeScript Express / Koa / Fastify 앱이 이제 라우트를 추출** — `express.scm`이 JavaScript의 클래스 이름 노드 타입을 하드코딩했는데, 이는 TypeScript grammar에서 "Impossible pattern"이라 쿼리 전체가 컴파일에 실패하고 그 에러가 묻혔습니다: **TS Express 앱은 라우트 0개**. (JavaScript 앱은 정상이었고 테스트 픽스처가 `.js`뿐이라 발각되지 않았습니다.) 동일한 근본 원인이 `vue.scm`에도 있었습니다(JS `<script>` Vue SFC → 컴포넌트 0개). 둘 다 JS·TS 모두에서 컴파일되는 grammar 중립 노드 와일드카드로 수정했습니다.
- **Spring 프로젝트의 Kotlin 파일이 더 이상 에러를 내지 않음** — `spring_boot.scm`은 Java grammar 쿼리인데 Kotlin에 대해 실행이 허용되어 `Invalid node type: marker_annotation`를 내며 모든 `.kt` 파일을 버렸습니다. 이제 Kotlin은 깨끗하게 차단됩니다(Kotlin Spring Boot는 별도 쿼리가 필요).
- **tree-sitter grammar에 상한 핀 추가** — `pyproject.toml`이 grammar를 상한 없이(`>=0.23`) 핀해서, AST 노드 타입을 개명하는 향후 grammar 릴리스가 쿼리를 조용히 다시 깨뜨릴 수 있었습니다. 이제 모든 grammar에 호환 범위 상한이 있고, 모든 출고 `.scm`이 자신이 지원한다고 선언한 모든 grammar에 대해 컴파일되는지 검증하는 테스트가 추가되었습니다.
- **추출 캐시에 버전 도장** — codebeacon 업그레이드 후 증분 `--update`가 변경되지 않은 파일에 대해 *이전* 버전이 추출한 결과를 재사용할 수 있었습니다(콘텐츠 해시는 추출기 자체가 바뀐 것을 감지하지 못함). 이제 캐시에 codebeacon 버전이 찍히고 버전 불일치 시 폐기됩니다.
- **악센트 / 비-ASCII 이름이 macOS에서 해석됨** — `codebeacon query` / `path` / MCP와 `affected`가 라벨과 경로를 Unicode NFC로 정규화하므로, macOS 파일명에서 복사한 이름(NFD로 저장)이 그래프의 NFC 라벨과 매칭됩니다(예: `Auditoría`).
- 추가로: 손상된 추출 `cache.json`을 조용히 리셋한 뒤 덮어쓰는 대신 백업하고 재생성합니다.

---

## 0.6.5 새 소식

`codebeacon upgrade` 가 이제 어떤 환경에서도 동작합니다 — 이전에는 일반 pip 설치를 가정해서, 그렇지 않은 머신에서는 아무것도 못 하고 조용히 실패했습니다.

- **설치 매니저 자동 감지** — upgrade 명령이 codebeacon 의 설치 방식을 감지해 맞는 도구를 실행합니다: pip 설치면 `pip install --upgrade`, pipx 면 `pipx upgrade codebeacon`, uv 면 `uv tool upgrade codebeacon`. pipx/uv tool 의 venv 에는 `pip` 모듈이 *없어서*, 기존의 무조건적인 `python -m pip` 호출은 시작도 못 하고 죽었습니다.
- **업그레이드 검증** — 업그레이드 후 새 인터프리터로 설치된 버전을 다시 읽어 `0.6.4 -> 0.6.5` 처럼 보고합니다. 버전이 그대로인데 PyPI 에 더 새 릴리스가 있으면, 가짜 "Upgrade complete" 대신 PATH 의 `codebeacon` 이 다른 Python 환경 소속일 수 있다는 경고를 출력합니다.
- **실패 메시지가 곧 해결책** — pip 없는 환경이면 실행할 정확한 명령을 안내하고, PEP 668 `externally-managed-environment` 거부에는 원시 pip 에러 대신 해결 방법(pipx 또는 virtualenv)을 설명합니다. 시작 시 현재 버전과 PyPI 최신 버전도 나란히 보여줍니다.

---

## 0.6.4 새 소식

Deep-dive 정리 — 출력물이 찾아보는 곳에 생성되도록 정돈하고, 47개 프로젝트 워크스페이스에서 이를 검증하던 중 발견한 조용한 데이터 손실 버그 2건 수정.

- **Deep-dive가 정확히 두 레벨에만 기록** — 각 *레포 루트*(자체 `.git` 또는 `codebeacon.yaml`이 있는 디렉토리)와 *스캔 루트*. 모노레포의 프레임워크 폴더(`mono/landing`, `mono/server`)마다 `.codebeacon/` + CLAUDE.md가 늘어나지 않으며, 이들의 통합 그래프는 `mono/.codebeacon/`에 위치하고 스캔 루트가 전체 워크스페이스 그래프를 담아 어떤 프로젝트든 한 곳에서 찾을 수 있습니다. 모노레포 *내부*에서 deep-dive를 실행하면 이제 서브폴더마다 하나씩이 아니라 단일 루트 출력이 생성됩니다.
- **캐시 키가 프레임워크로 네임스페이스됨** — 레포 그룹은 하나의 캐시를 공유하는데, 부모 프로젝트가 중첩 프로젝트의 파일을 먼저 순회하면(`desktop/src-tauri` 위를 sveltekit으로 도는 `desktop/`) 빈 결과로 캐시를 오염시키고, 중첩 프로젝트(tauri)가 이를 재사용해 자신의 route와 엔티티를 전부 조용히 잃었습니다.
- **Grammar 로드 race 수정** — 캐시되지 않은 tree-sitter grammar에 병렬 추출 워커 둘이 동시에 도달하면 각자 자신의 `Language` 인스턴스를 만들었고, 진 쪽 스레드의 파일은 identity 체크에 실패해 **아무것도** 추출하지 못했습니다 — 경고도, 실패 기록도 없이 큰 스캔에서 파일 몇 개가 무작위로 route를 전부 잃었습니다. 첫 로드는 이제 단일 공유 인스턴스로 잠깁니다(연속 20회 전체 스캔에서 안정성 검증).

---

## 0.6.3 새 소식

버그 수정 릴리스 — graphify-parity 감사(업스트림 6월 3–10일)에 codebeacon 자체 코드에 대한 독립 감사를 더해 **16건 수정**, 47개 프로젝트 `--deep-dive` 워크스페이스 스캔(노드 5,226 / 엣지 8,715)으로 end-to-end 검증.

- **Git hook이 어디서나 동작** — post-commit 재빌드 hook이 설치 시점의 Python 인터프리터를 스크립트에 고정하고 `nohup` 대신 `subprocess`로 detach하므로, GUI git 클라이언트(Sublime Merge, GitKraken)·CI 러너·Windows처럼 `codebeacon` 런처가 `PATH`에 없어 기존 hook이 조용히 아무것도 하지 않던 환경에서도 동작합니다. `codebeacon hook install`을 다시 실행하면 수정이 적용되며, merge driver도 같은 방식으로 고정됩니다.
- **주석 처리된 JS/TS import가 더 이상 엣지를 만들지 않음** — 배럴 re-export와 `require()` 정규식 패스가 먼저 `//`·`/* */` 주석을 (문자열 리터럴을 인식하며) 제거합니다. 주석 처리된 `export * from './legacy'`가 phantom 엣지와 가짜 import 순환을 만들던 문제 해결.
- **`from pkg import name`이 실제 대상에 바인딩 (Python)** — import 추출기가 import된 이름을 캡처하므로 `from auth.services import UserService`는 `UserService` 노드로, `from src.services import enricher`는 서브모듈로 연결됩니다. 이전엔 모듈 경로의 마지막 세그먼트만 시도해 테스트 파일이 그래프에서 끊겨 있었습니다. 별칭(`import x as y`)은 실제 심볼 이름으로 해석됩니다.
- **"High-Impact Files"가 진짜 high-impact** — hub 랭킹(CLAUDE.md, `analyze`)이 엣지의 `source_file`(항상 import하는 쪽)로 import *fan-out*을 세는 바람에, 엔트리 포인트가 노드 단위로 부풀려진 수치(60개 파일 레포에서 "imported by 392 files")로 진짜 공유 모듈을 제쳤습니다. 두 사본 모두 import되는 파일별로 고유한 import하는 파일 수를 셉니다.
- **DI `injects` 엣지가 실제 파일 경로를 가짐** — 해석된 dependency-injection 엣지가 `source_file`에 그래프 노드 ID(`proj::Name`)를 찍던 문제 수정 → 이제 소스 노드의 실제 파일을 담습니다.
- **Ktor 중첩 route prefix 연결** — `route("/api") { route("/v1") { get("/users") } }`가 바깥 prefix를 전부 버리는 대신 `/api/v1/users`를 추출합니다.
- **같은 경로의 route가 모두 매칭** — 두 서비스가 같은 URL을 노출할 때(gateway + upstream), `calls_api` enrichment가 마지막 하나만 조용히 남기지 않습니다.
- **희소한 YAML 설정 허용** — `output:` / `wave:` / `semantic:`을 비워 둬도 `AttributeError`로 크래시하지 않고, `projects:` 아래 떠도는 bare `-`는 `TypeError` 대신 깔끔한 설정 에러를 냅니다.
- **언어 감지가 vendored 디렉토리 스킵** — 폴백 언어 투표가 `node_modules` / `.git` / `dist`를 제외 → vendored JS가 있는 Python 레포가 *javascript*로 감지되지 않음(그리고 discovery가 수만 개의 vendored 파일을 크롤하지 않음).
- **wiki 링크가 파일과 일치** — 링크 대상이 생성기가 파일을 쓸 때와 정확히 같은 파일명 변환을 사용 → 공백, `#`, 괄호, 제네릭이 포함된 라벨이 깨진 링크를 만들지 않음.
- 추가: 결정적 enrichment 엣지 순서, `None` 라벨 빌드 가드, 스레드 안전 추출 캐시, FastAPI `Depends()` ghost ref 제거, Obsidian 서비스 폴더명 byte 상한.

---

## 0.6.2 새 소식

- **결정적 community ID** — 같은 크기의 community가 partitioner 열거 순서로 번호를 받아 no-op 재스캔에서 `beacon.json`의 77–88 %가 뒤바뀌던 문제 수정; 동일한 그룹은 이제 항상 동일한 ID를 받습니다.
- **노트 파일명 byte 상한** — 85자 이상의 CJK 클래스명이 파일시스템 255바이트 한계를 넘어 `ENAMETOOLONG`으로 wiki/Obsidian 내보내기 전체를 크래시시키던 문제; UTF-8 200바이트로 캡하고 충돌 안전 해시 접미사를 붙입니다.
- **FastAPI / Laravel / ASP.NET DI 엣지 복구** — 해석된 `Depends()` / `bind()` / `AddScoped<>` 참조가 파일 경로로 키잉된 반면 노드는 프로젝트로 키잉되어 엣지가 조용히 버려졌습니다; 이제 최종 노드 ID로 리매핑됩니다.
- **인터페이스 → 구현 DI 부활** — `implements`/`extends` 메타데이터를 어떤 추출기도 채우지 않아 인터페이스 타입 주입이 전혀 해석되지 않았습니다; Spring, ASP.NET, NestJS, Angular가 이제 이를 연결합니다.

---

## 0.6.1 새 소식

패치 릴리스 — 추출 정확성과 재현 가능한 출력.

- **6개 프레임워크 추출기 복구** — `laravel`, `angular`, `aspnet`, `actix`, `ktor`, `vapor` tree-sitter 쿼리가 현재 grammar 버전과 어긋나 **아무것도 추출하지 못하던** 문제 수정: 쿼리가 컴파일에 실패하고 그 에러가 경고로 묻혀 있었습니다. 6개 모두 설치된 grammar로 컴파일·추출되도록 수정(Laravel `scope:`/`name:` 필드, Angular `export class` 데코레이터, ASP.NET `invocation_expression` 필드, Actix 형제 노드 앵커, Kotlin 1.x 노드 개명, Swift 0.0.1 노드셋)했으며, 재발 방지 회귀 테스트를 각각 추가했습니다.
- **재현 가능한 `beacon.json`** — 직렬화 전에 노드 `source_file` 경로를 각 프로젝트 루트 기준 상대경로로 변환 → 같은 커밋을 다른 머신에서 스캔해도 바이트 단위로 동일한 그래프 생성(절대경로 diff 잡음 제거).
- **`affected` 과다 보고 수정** — 변경 파일 seed 매칭을 경로 세그먼트 단위로 정렬 → `src/user.py`가 `foosrc/user.py` 같은 무관한 노드를 끌어오지 않음.
- **`semantic-apply` 크래시 수정** — 아카이브/마이그레이션된 JSONL 엣지의 `confidence_score: null`이 `TypeError`로 실행을 중단시키던 문제 제거, 파이프라인의 나머지와 동일하게 안전 기본값으로 보정.
- **NetworkX 3.6 호환** — `beacon.json`을 `edges="links"` 키로 명시 기록 → 상위 기본값 변경이 디스크 포맷을 조용히 바꾸지 못하게 함. MCP 서버도 동일한 호환 로더 사용.
- **Obsidian 볼트 정리** — stale 노트 정리가 볼트 전체(루트+중첩)를 sweep하고, cross-language import 필터가 파일명 접미사 대신 노트의 실제 소스 언어를 기준으로 동작.
- **gitignore 의미** — `build/*.js` 같은 anchored 패턴에서 `*`가 `/`를 넘지 않도록 수정 → 중첩 파일이 잘못 무시되지 않음.
- **Next.js App Router** — JS 기반 `page.js` / `page.jsx` 라우트도 탐색(이전엔 `.ts` / `.tsx`만).
- **DI 귀속 수정** — FastAPI `Depends()`와 Angular 생성자 주입을 파일 내 첫/마지막이 아니라 byte-range로 감싸는 함수·클래스에 정확히 귀속. Razor `@using`은 더 이상 중복 엣지를 만들지 않음.

---

## 0.6.0 새 소식

- **`codebeacon affected`** — 변경된 파일 목록(또는 `--base <ref>`로 git diff)을 받아 그 영향권에 있는 그래프 노드를 모두 출력. CI 리스크 스코어링·PR 리뷰용.
- **`.NET` 프로젝트 파일** — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml`가 이제 파싱됩니다. `<ProjectReference>` / `<PackageReference>`가 그래프 엣지로, Razor `@inherits` / `@inject` / `@using`이 Blazor 페이지를 백엔드 타입으로 연결합니다.
- **JS/TS 배럴 re-export** — `export { X } from './mod'`, `export * from './mod'`가 명시적 `re_exports` 엣지가 됩니다. Next.js·모노레포 배럴이 더 이상 import 0으로 표시되지 않습니다.
- **`--exclude PATTERN` 플래그** (`scan` / `sync`) + `.codebeaconignore`가 없을 때 자동 `.gitignore` 폴백.
- **`codebeacon install --project [PATH]`** — `~/.claude/` 대신 `<PATH>/.claude/`에 `/codebeacon` 스킬 설치. 팀이 SKILL.md 버전을 레포에 핀할 수 있습니다.
- **wiki 자동 정리** — `--update` 실행 시 더 이상 그래프에 없는 `wiki/<project>/{controllers,services,entities,components}/*.md` 파일을 자동 삭제.
- **명시 삭제 시 shrink-guard 우회** — `--update` 모드에서 캐시가 이미 삭제된 파일을 추적했다면 더 작은 `beacon.json` 쓰기를 거부하지 않습니다. silent corruption에 대한 가드는 그대로.
- **Cross-file 선언 union 머지** — Swift `extension Foo`, C# partial class, Ruby reopened class가 `fields` / `methods`를 마지막 파일에 덮어쓰지 않고 단일 canonical 노드로 합쳐집니다.
- **query 강화** — `BeaconIndex`가 `casefold()`를 사용해 독일어 `ß`, 터키어 `i/İ`, 그리스어 `σ/ς`, CJK 라벨 매칭이 올바르게 동작합니다.
- **시맨틱 컨텍스트 강화** — 각 task chunk에 그래프 caller·callee가 `neighbors`로 동봉되어 LLM이 실제 노드 라벨에서 벗어나기 어렵습니다. `SKILL.md`에 **Step 0 — Constrained query expansion** 추가로 `/codebeacon query` 흐름이 phantom 토큰을 만들지 못하도록 명시.
- **`semantic-apply` zero-yield 가드** — 모든 chunk가 0 엣지로 archive되면 CLI가 exit 1로 종료해 CI가 LLM의 silent 실패를 잡습니다.
- **ArkTS (`.ets`) + worktree 안전** — `.ets` 수집, 중첩 `worktrees/` 디렉토리는 스킵해 linked worktree가 중복 인덱싱되지 않습니다.

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
- **Graphify 스타일 semantic 보강** — AST 추출 후 스킬이 청크당 subagent 1개를 병렬로 띄워 `{nodes, edges, hyperedges}` 풀 그래프 단편을 추출. 관계 8종(`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`) + 신뢰도 3단계(EXTRACTED/INFERRED/AMBIGUOUS) 지원. Claude Code에서는 subagent가 호스트 모델보다 한 단계 아래(Opus→Sonnet, Sonnet→Haiku)로 자동 강등되어 코퍼스 크기에 비례한 비용 유지. 코드 노드는 AST 전담, LLM은 `concept`/`document`/`paper` 노드만 기여 가능. 기존 0.3.x 아카이브는 새 스키마로 그대로 replay됨
- **지식 모드 (`codebeacon knowledge`)** — 마크다운 노트(ADR, 회의록, 회고, 스펙, 리서치)를 스캔해서 `.codebeacon/` 옆에 단일 `KNOWLEDGE.md` 생성. 파일명·제목 패턴으로 자동 분류, Obsidian YAML frontmatter와 `[[backlinks]]` 파싱, 최상단에 "Key Decisions" + "Open Questions" 롤업을 제공해 코드베이스가 *왜* 이런 모습인지 에이전트에게 전달. 휴리스틱만 사용 — LLM 호출 없음
- **경로 단축 입력** — `codebeacon ./src`가 이제 `codebeacon scan ./src`와 동일. 첫 인자가 등록된 서브커맨드가 아니면 `scan`이 자동 주입되어, `graphify <path>` / `codesight <path>` 머슬 메모리도 그대로 동작
- **강화된 semantic 파이프라인** — `semantic-apply`가 agent JSONL의 비정상 라인(null/리스트/code-fence/필수 필드 누락)을 가드, 잘못된 `confidence_score`(None/NaN/문자열/범위 초과)를 안전 기본값으로 coerce, merge 직전 `beacon.json` → `beacon.json.bak` 스냅샷으로 AST 베이스라인 복구 가능 보장, `beacon.html`/`callflow.html`도 재생성해서 새 inferred 엣지가 시각화에 반영됨
- **민감 파일·디렉토리 가드** — `secrets/`, `credentials/`, `.ssh/`, `.aws/`, `.gnupg/` 디렉토리는 항상 스킵. credential 패턴(`api_token`, `oauth_token`, `private_key`, `client_secret`; 언더스코어 *및* 하이픈 변형) 파일명은 추출기에 도달하기 전 수집 단계에서 제외

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
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`); `.sln` / `.csproj` / `.fsproj` / `.vbproj`에서 `ProjectReference` + `PackageReference` 파싱 |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) 수집 — extractor는 framework-agnostic |

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
      pending/           ← prepare 가 chunk_NNN.jsonl 작성 (chunk 당 --chunk-size 개)
        chunk_001.jsonl
        chunk_002.jsonl
      results/           ← 에이전트가 같은 이름의 chunk_NNN.jsonl 작성
        chunk_001.jsonl
      original/          ← apply 가 완료 chunk 를 이동 (영구 아카이브)
        chunk_001.jsonl
        chunk_002.jsonl  ← (과거 실행 분이 누적; chunk 번호는 monotonic)
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
/codebeacon upgrade               # pip 업그레이드 + 이 스킬 SKILL.md 갱신 (이후 Claude Code 재시작)
```

기본적으로 `scan` 과 `sync` 호출은 마지막에 **AI-시맨틱** 파이프라인을 자동 실행합니다 ([AI-시맨틱 보강](#ai-시맨틱-보강-codebeacon-스킬에서-자동) 섹션 참고). 에이전트는 Claude Code 세션이 **현재 실행 중인 모델**을 그대로 사용 — Opus, Sonnet, Haiku — codebeacon 은 절대 모델을 하드코딩하지 않고 API 키도 필요 없습니다.

### 새 버전으로 업그레이드

어디서든 한 줄:

```bash
codebeacon upgrade
```

이 명령은 설치에 사용된 도구(`pip`, `pipx upgrade`, `uv tool upgrade` — 자동 감지)로 패키지를 업그레이드하고, 설치된 버전이 실제로 바뀌었는지 검증한 뒤 `codebeacon install` 을 다시 실행해 `~/.claude/skills/codebeacon/SKILL.md` 을 새 릴리스의 사본으로 덮어씁니다. 새 SKILL.md 가 로드되려면 Claude Code 세션을 재시작하세요. editable 모드 (`pip install -e .`) 로 설치되어 있다면 패키지 단계는 스킵됩니다 — 강제로 진행하려면 `--force` 를 붙이세요.

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
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # gitignore-스타일 패턴, 반복 가능
                                          # .codebeaconignore / .gitignore 와 병합

# 설정 기반 모드
codebeacon init [path]                    # codebeacon.yaml 자동 생성
codebeacon sync                           # codebeacon.yaml 기반 실행 (신규 워크스페이스 프로젝트 자동 추가)
codebeacon sync --config <file>           # 특정 설정 파일 사용
codebeacon sync --no-rediscover           # 신규 프로젝트 자동 추가 비활성화 (수동 큐레이션 모드)
codebeacon sync --exclude PATTERN         # 동일 플래그 동일 의미

# PR / CI: 이 diff 가 실제로 무엇을 깰까?
codebeacon affected --base main           # 변경 파일들의 업스트림 호출자 walk
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # 명시 경로 — git 없이도 동작

# AI-시맨틱 보강 (LLM 작업은 에이전트가, 부기는 codebeacon이 담당)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # .codebeacon/semantic/original/*.jsonl 아카이브를 fresh
                                          # beacon.json 에 재적용 + 사라진 노드를 가리키는 stale 엔트리
                                          # prune, 그 후 **모든** NEW 후보 (god 폴더 + hub file +
                                          # unresolved 타겟) 를 .codebeacon/semantic/pending/
                                          # chunk_NNN.jsonl 로 작성 (chunk 당 --chunk-size 개, 기본 10).
                                          # --max-tasks 는 선택적 cap (0 = no cap, 기본 — 모두 emit).
                                          # task_id 에 콘텐츠 해시가 포함되어 파일 내용이 바뀌면 자동 재발행.
codebeacon semantic-apply   [--dir .codebeacon]
                                          # 에이전트가 작성한 .codebeacon/semantic/results/
                                          # chunk_NNN.jsonl 각각을 INFERRED references 엣지로
                                          # beacon.json 에 머지 + pending/chunk_NNN.jsonl 을
                                          # original/chunk_NNN.jsonl 로 이동 (영구 아카이브).
                                          # results 파일 삭제, wiki/obsidian/컨텍스트 맵 재생성.

# 지식 그래프 쿼리
codebeacon query <term> [--dir .codebeacon] [--limit N]   # 라벨 부분 문자열로 노드 검색
codebeacon path <source> <target> [--dir .codebeacon]     # 최단 의존성 경로

# 멀티 개발자 지원 (git plumbing)
codebeacon hook install [path]            # merge driver + post-commit 증분 재빌드 설치
codebeacon merge-driver <base> <cur> <other>  # `hook install` 후 git이 자동 호출; beacon.json union 머지

# 통합
codebeacon serve [--dir .codebeacon]      # MCP 서버 시작 (stdio)
codebeacon install                        # Claude Code 스킬 설치 (user 스코프: ~/.claude/)
codebeacon install --project [PATH]       # <PATH>/.claude/ 에 설치 (팀 공유, 레포 핀)
codebeacon upgrade                        # pip 으로 업그레이드 + ~/.claude/skills/codebeacon/SKILL.md 갱신
                                          # (`--force` 로 editable 설치 환경에서도 강제 업그레이드)
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
2. `codebeacon semantic-prepare` 가 `.codebeacon/semantic/original/*.jsonl` 아카이브를 새 그래프에 재적용하고, 그래프에서 사라진 노드를 가리키는 stale 엔트리를 **prune** 한 뒤, 신규 task 들을 `.codebeacon/semantic/pending/chunk_NNN.jsonl` 로 작성 (`--chunk-size` 당 1 chunk, 기본 10). chunk 번호는 영구 아카이브의 다음 번호부터 시작 — 절대 충돌하지 않음.
3. 스킬이 pending chunk 들을 **한 번에 하나씩** 처리. 각 `pending/chunk_NNN.jsonl` 에 대해 에이전트(현재 세션의 모델)가 각 task 의 `excerpt` 를 읽고 같은 이름의 `semantic/results/chunk_NNN.jsonl` 을 작성.
4. `codebeacon semantic-apply` 가 결과를 `INFERRED references` 엣지로 `beacon.json` 에 머지하고, 각 완료된 `pending/chunk_NNN.jsonl` 을 **`semantic/original/chunk_NNN.jsonl`** 로 **이동** (적용된 엣지를 함께 적재, 감사 가능). results 파일은 삭제, wiki + obsidian + 컨텍스트 맵 재생성.
5. 다음 스캔: `semantic-prepare` 가 `original/` 의 모든 chunk 엣지를 새 그래프에 재적용 (과거 추론 보존) 하고, 이미 처리된 task_id 는 스킵. `task_id` = `SHA1(file_path | node_id | excerpt_hash[:8])` — 파일 시맨틱 내용이 바뀌면 자동으로 새 id 가 되어 재분석.

→ 증분 + 멱등 보강. 같은 (파일, 내용) 조합을 두 번 분석하지 않고, 누적된 AI 시그널은 매 재스캔을 살아남으며 chunk 분할로 에이전트의 working set 도 작게 유지됩니다.

### 직접 CLI 사용

스킬 없이 (예: CI) 같은 두 명령을 직접 운영할 수 있습니다 — `results/chunk_NNN.jsonl` 파일들을 본인이 채우면 됩니다:

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# .codebeacon/semantic/pending/chunk_001.jsonl ... 이 생성됨.
# 각 pending chunk 에 대해 같은 이름의 results/chunk_NNN.jsonl 을 작성. 각 라인:
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
