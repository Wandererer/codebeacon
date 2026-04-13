---

1. PyPI (pip install codebeacon)

# 빌드 도구 설치

pip install build twine

# 빌드

cd /Users/wanderer/Desktop/personal/codebeacon
python -m build

# → dist/codebeacon-0.1.0.tar.gz

# → dist/codebeacon-0.1.0-py3-none-any.whl

# PyPI 계정 없으면 https://pypi.org/account/register/ 에서 가입

# API 토큰 발급: Account Settings → API tokens

# 테스트 배포 (권장: 먼저 TestPyPI로)

twine upload --repository testpypi dist/\*
pip install --index-url https://test.pypi.org/simple/ codebeacon

# 실제 배포

twine upload dist/\*

API 토큰을 ~/.pypirc에 저장하면 편합니다:
[pypi]
username = **token**
password = pypi-xxxx...

이후 버전 올릴 때는 pyproject.toml의 version = "0.1.1" 바꾸고 재빌드.

---

2. Claude Code Skill (/codebeacon)

이미 skill/install.py가 있어서 PyPI 배포 후 자동으로 동작합니다.

pip install codebeacon
codebeacon install

# → ~/.claude/skills/codebeacon/SKILL.md 복사됨

# → ~/.claude/CLAUDE.md에 트리거 추가됨

다른 사람이 설치하는 흐름:
pip install codebeacon # PyPI에서 설치
codebeacon install # 스킬 등록

# 새 Claude Code 세션 → /codebeacon 입력하면 동작

별도 배포 없이 PyPI 배포만 되면 끝. skill/SKILL.md는 wheel 안에 포함되어 있어야 합니다. pyproject.toml에 확인:

[tool.hatch.build.targets.wheel]
packages = ["codebeacon"]

skill/ 폴더가 wheel에 포함되려면:

[tool.hatch.build.targets.wheel]
packages = ["codebeacon"]

[tool.hatch.build.targets.wheel.sources]
"skill" = "codebeacon/skill"

또는 더 간단하게 skill/SKILL.md를 codebeacon/skill/SKILL.md로 이동하고 install.py의 경로 수정.

---

3. MCP Server

MCP는 두 가지 방식으로 배포합니다.

A. stdio (현재 구현) — Claude Desktop / Claude Code에서 직접 연결

사용자가 ~/.claude/settings.json (Claude Code) 또는 ~/Library/Application Support/Claude/claude_desktop_config.json (Claude Desktop)에 추가:

{
"mcpServers": {
"codebeacon": {
"command": "codebeacon",
"args": ["serve", "--dir", "/path/to/project/.codebeacon"]
}
}
}

자동화: codebeacon install이 이 설정도 써줄 수 있게 skill/install.py에 추가 가능.

B. npm registry에 MCP wrapper 등록 (선택)

MCP 생태계는 현재 npm 중심이라 Python MCP도 npx로 실행되는 경우가 많습니다. 간단한 package.json wrapper:

{
"name": "@codebeacon/mcp",
"version": "0.1.0",
"bin": { "codebeacon-mcp": "./bin/run.js" }
}

// bin/run.js
#!/usr/bin/env node
const { execSync } = require('child_process');
execSync('codebeacon serve ' + process.argv.slice(2).join(' '), { stdio: 'inherit' });

그러면 사용자가:
{
"mcpServers": {
"codebeacon": {
"command": "npx",
"args": ["-y", "@codebeacon/mcp", "--dir", ".codebeacon"]
}
}
}

---

권장 배포 순서

1. GitHub public repo 생성
2. TestPyPI 테스트 배포 → 설치 검증
3. PyPI 실제 배포 (pip install codebeacon)
4. Claude Code skill은 PyPI와 동시에 자동 배포됨
5. MCP: README에 settings.json 설정법 안내
6. (선택) npm @codebeacon/mcp wrapper

현재 코드베이스는 1~5가 모두 준비된 상태입니다. PyPI 계정만 있으면 python -m build && twine upload dist/\* 한 줄로 끝납니다.
