#!/bin/bash
# dding-skills Codex-first installer
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLATFORM="mac"
WITH_CLAUDE_MCP=0
WITH_EXTERNAL_SKILLS=0
CANONICAL_MCP_NAME="ctf_solver"
LEGACY_MCP_NAME="dreamhack_solver"
CTF_DIR="${CTF_DIR:-$HOME/CTF}"
EXTERNAL_SKILLS_DIR="$HOME/.agents/skills"

usage() {
    cat <<EOF
Usage: bash install.sh [mac|windows] [options]

Default:
  bash install.sh
    - run config/deploy.sh
    - create/sync ~/CTF/CLAUDE.md and ~/CTF/AGENTS.md
    - install repo-managed ctf-personal skill to ~/.agents/skills
    - build ctf-pwn Docker image only when Docker is reachable and image is missing
    - do not register Claude MCP
    - do not install external ljagiello/ctf-skills

Options:
  --with-claude-mcp       Register Claude Code MCP server ctf_solver when claude and uv exist.
  --with-external-skills  Install optional ljagiello/ctf-skills globally under ~/.agents/skills.
  --all                   Run both optional tasks above.
  --help, -h              Show this help.

Environment:
  CTF_DIR                 Primary CTF workspace. Default: ~/CTF
  CTF_SOLVER_DOCKER_REBUILD=1
                          Rebuild ctf-pwn even when the image already exists.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        mac|windows)
            PLATFORM="$1"
            ;;
        --with-claude-mcp)
            WITH_CLAUDE_MCP=1
            ;;
        --with-external-skills)
            WITH_EXTERNAL_SKILLS=1
            ;;
        --all)
            WITH_CLAUDE_MCP=1
            WITH_EXTERNAL_SKILLS=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
    shift
done

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
    elif [ -x "$HOME/.local/bin/uv" ]; then
        echo "$HOME/.local/bin/uv"
    else
        return 1
    fi
}

claude_mcp_registered() {
    claude mcp list 2>/dev/null | grep -Eq "(^|[[:space:]])${CANONICAL_MCP_NAME}(:|[[:space:]]|$)"
}

run_deploy() {
    echo "[deploy] config/deploy.sh $PLATFORM"
    bash "$REPO_DIR/config/deploy.sh" "$PLATFORM"
}

register_claude_mcp() {
    if [ "$WITH_CLAUDE_MCP" -ne 1 ]; then
        echo "[skip] Claude MCP registration is optional. Run: bash install.sh --with-claude-mcp"
        return
    fi

    if ! command -v claude >/dev/null 2>&1; then
        echo "[warn] claude CLI not found; skipping optional Claude MCP registration"
        return
    fi

    local uv_bin
    if ! uv_bin="$(find_uv)"; then
        echo "[warn] uv not found; skipping optional Claude MCP registration"
        return
    fi

    if claude_mcp_registered; then
        echo "[skip] Claude MCP server already appears registered: $CANONICAL_MCP_NAME"
        echo "[info] Legacy MCP migration: if $LEGACY_MCP_NAME is still registered, review it manually."
        echo "       This installer does not remove existing Claude MCP entries."
        return
    fi

    echo "[info] Registering Claude MCP server: $CANONICAL_MCP_NAME"
    if claude mcp add --scope user "$CANONICAL_MCP_NAME" \
        -- "$uv_bin" run --with "mcp[cli]" --with requests --with httpx \
        mcp run "$REPO_DIR/server.py"; then
        echo "[ok] Claude MCP server registered: $CANONICAL_MCP_NAME"
    else
        echo "[warn] Claude MCP registration failed; Codex-first install can continue"
    fi

    echo "[info] Legacy MCP migration: if $LEGACY_MCP_NAME is still registered, review it manually."
    echo "       This installer does not remove existing Claude MCP entries."
}

install_external_skills() {
    if [ "$WITH_EXTERNAL_SKILLS" -ne 1 ]; then
        echo "[skip] external CTF skills are optional. Run: bash install.sh --with-external-skills"
        return
    fi

    if ! command -v npx >/dev/null 2>&1; then
        echo "[warn] npx not found; install manually after reviewing the source:"
        echo "       npx --yes skills add ljagiello/ctf-skills --global --all --copy"
        return
    fi

    echo "[warn] ljagiello/ctf-skills is an external skill package."
    echo "       Review before use; installed skills can run with full agent permissions."
    echo "[info] Installing globally so Codex launched from $CTF_DIR can see them:"
    echo "       $EXTERNAL_SKILLS_DIR"
    npx --yes skills add ljagiello/ctf-skills --global --all --copy
}

build_docker_image() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "[skip] docker CLI not found. Manual build:"
        echo "       docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest ."
        return
    fi

    if ! docker info >/dev/null 2>&1; then
        echo "[skip] Docker daemon off or unreachable. Manual build after Docker starts:"
        echo "       docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest ."
        return
    fi

    if [ "${CTF_SOLVER_DOCKER_REBUILD:-0}" != "1" ] && docker image inspect ctf-pwn:latest >/dev/null 2>&1; then
        echo "[skip] Docker image ctf-pwn:latest already exists."
        echo "       Rebuild manually or set CTF_SOLVER_DOCKER_REBUILD=1."
        return
    fi

    echo "[build] ctf-pwn Docker image"
    docker build --platform linux/amd64 -f "$REPO_DIR/Dockerfile.ctf" -t ctf-pwn:latest "$REPO_DIR"
    echo "[ok] Docker image ready: ctf-pwn:latest"
}

print_next_steps() {
    cat <<EOF

=== install complete ===

Codex primary workspace:
  cd ~/CTF
  codex

Optional Claude MCP:
  bash install.sh --with-claude-mcp

Optional external skills:
  bash install.sh --with-external-skills

Doctor:
  python3 scripts/doctor.py
EOF
}

echo "=== dding-skills install start ($PLATFORM, Codex-first) ==="
run_deploy
register_claude_mcp
install_external_skills
build_docker_image
print_next_steps
