# @codebeacon/mcp

`npx` launcher for the [codebeacon](https://github.com/codebeacon/codebeacon)
MCP server. It exposes a repo's pre-built knowledge graph and wiki (routes,
services, entities, blast radius, PR context, knowledge notes) to MCP-speaking
AI clients — Claude Desktop, Claude Code, Cursor, and friends.

codebeacon is a Python package; this is a thin, zero-dependency Node shim so
MCP clients can launch it the npx-first way they expect. It resolves a working
`codebeacon` on the host and runs `codebeacon serve` for you.

## Prerequisites

The Python package must be installed (the wrapper does not bundle it). Any one
of these works:

```bash
pipx install codebeacon      # recommended
uv tool install codebeacon
pip install codebeacon
```

Then generate the index once for the repo you want to query:

```bash
codebeacon scan /path/to/your/repo
```

That writes a `.codebeacon/` directory the server reads.

## Usage

The one-liner clients run under the hood:

```bash
npx -y @codebeacon/mcp --dir /path/to/your/repo/.codebeacon
```

Any arguments after `@codebeacon/mcp` are forwarded verbatim to
`codebeacon serve`. The only flag `serve` takes is `--dir` (the path to a
`.codebeacon` output directory); it defaults to `.codebeacon` in the current
working directory when omitted.

### Runner resolution

The wrapper probes for a working codebeacon in this order and uses the first
that responds to `--version`:

1. `codebeacon` on `PATH` (pip / pipx / uv install)
2. `uvx codebeacon`
3. `pipx run codebeacon`
4. `python3 -m codebeacon`

If none resolve, it exits non-zero with the install options above printed to
stderr. It never writes to stdout, so it can't corrupt the MCP JSON-RPC stream.

## Client configuration

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) /
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "npx",
      "args": ["-y", "@codebeacon/mcp", "--dir", "/path/to/your/repo/.codebeacon"]
    }
  }
}
```

### Cursor

`~/.cursor/mcp.json` (or the per-project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "npx",
      "args": ["-y", "@codebeacon/mcp", "--dir", "/path/to/your/repo/.codebeacon"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add codebeacon -- npx -y @codebeacon/mcp --dir /path/to/your/repo/.codebeacon
```

## License

MIT
