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
EXPECTED_EXTERNAL_SKILLS=(
    ctf-ai-ml
    ctf-crypto
    ctf-forensics
    ctf-malware
    ctf-misc
    ctf-osint
    ctf-pwn
    ctf-reverse
    ctf-web
    ctf-writeup
    solve-challenge
)

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
  --with-external-skills  Install optional ljagiello/ctf-skills only under ~/.agents/skills.
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

is_expected_external_skill() {
    local candidate="$1"
    local skill
    for skill in "${EXPECTED_EXTERNAL_SKILLS[@]}"; do
        if [ "$candidate" = "$skill" ]; then
            return 0
        fi
    done
    return 1
}

find_external_skill_source() {
    local clone_dir="$1"
    local skill="$2"
    local direct="$clone_dir/$skill"
    local found

    if [ -f "$direct/SKILL.md" ]; then
        echo "$direct"
        return 0
    fi

    found="$(find "$clone_dir" -type f -path "*/$skill/SKILL.md" -print -quit)"
    if [ -n "$found" ]; then
        dirname "$found"
        return 0
    fi

    return 1
}

safe_replace_external_skill() {
    local skill="$1"
    local source_dir="$2"
    local target="$EXTERNAL_SKILLS_DIR/$skill"
    local external_parent
    local target_parent

    if ! is_expected_external_skill "$skill"; then
        echo "[fail] Refusing to install unexpected external skill: $skill" >&2
        return 1
    fi

    if [ ! -f "$source_dir/SKILL.md" ]; then
        echo "[fail] Source skill is missing SKILL.md: $source_dir" >&2
        return 1
    fi

    mkdir -p "$EXTERNAL_SKILLS_DIR"
    external_parent="$(cd "$EXTERNAL_SKILLS_DIR" && pwd -P)"
    target_parent="$(cd "$(dirname "$target")" && pwd -P)"

    if [ "$target_parent" != "$external_parent" ] || [ "$(basename "$target")" != "$skill" ]; then
        echo "[fail] Refusing unsafe external skill target: $target" >&2
        return 1
    fi

    rm -rf "$target"
    cp -a "$source_dir" "$target"
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

    if ! command -v git >/dev/null 2>&1; then
        echo "[warn] git not found; cannot clone ljagiello/ctf-skills"
        return
    fi

    echo "[warn] ljagiello/ctf-skills is an external skill package."
    echo "       Review before use; installed skills can run with full agent permissions."
    echo "[info] Installing deterministic copies only under:"
    echo "       $EXTERNAL_SKILLS_DIR"

    EXTERNAL_SKILLS_TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "${EXTERNAL_SKILLS_TMP_DIR:-}"' EXIT

    local clone_dir="$EXTERNAL_SKILLS_TMP_DIR/ctf-skills"
    local skill
    local source_dir
    local installed=()
    local missing=()

    git clone --depth 1 https://github.com/ljagiello/ctf-skills.git "$clone_dir"

    for skill in "${EXPECTED_EXTERNAL_SKILLS[@]}"; do
        if source_dir="$(find_external_skill_source "$clone_dir" "$skill")"; then
            safe_replace_external_skill "$skill" "$source_dir"
            installed+=("$skill")
        else
            missing+=("$skill")
        fi
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        echo "[fail] Missing expected external skills: ${missing[*]}" >&2
        return 1
    fi

    echo "[ok] External skills installed under $EXTERNAL_SKILLS_DIR:"
    for skill in "${installed[@]}"; do
        echo "       - $skill"
    done
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
