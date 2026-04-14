#!/bin/bash
# 사용법: ./config/deploy.sh mac  또는  ./config/deploy.sh windows

set -e

PLATFORM="${1:-mac}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [ "$PLATFORM" = "mac" ]; then
    CTF_DIR="$HOME/CTF"
    SKILL_DIR="$HOME/.agents/skills/ctf-personal"
elif [ "$PLATFORM" = "windows" ]; then
    CTF_DIR="$HOME/CTF"
    SKILL_DIR="$HOME/.agents/skills/ctf-personal"
else
    echo "Usage: $0 [mac|windows]"
    exit 1
fi

# 환경 정보 파일 확인
ENV_FILE="$SCRIPT_DIR/$PLATFORM/env.md"
BASE_FILE="$SCRIPT_DIR/CLAUDE.base.md"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi

if [ ! -f "$BASE_FILE" ]; then
    echo "Error: $BASE_FILE not found"
    exit 1
fi

# CLAUDE.md 조립: 환경 정보 + 공통 내용
mkdir -p "$CTF_DIR"
cat "$ENV_FILE" "$BASE_FILE" > "$CTF_DIR/CLAUDE.md"
echo "✓ CLAUDE.md → $CTF_DIR/CLAUDE.md"

# AGENTS.md 심링크 (CLAUDE.md와 동일 내용)
if [ ! -L "$CTF_DIR/AGENTS.md" ] && [ ! -f "$CTF_DIR/AGENTS.md" ]; then
    ln -s "$CTF_DIR/CLAUDE.md" "$CTF_DIR/AGENTS.md"
    echo "✓ AGENTS.md → $CTF_DIR/AGENTS.md (symlink)"
fi

# ctf-personal 스킬 심링크
mkdir -p "$(dirname "$SKILL_DIR")"
ln -sfn "$REPO_DIR/skills/ctf-personal" "$SKILL_DIR"
echo "✓ ctf-personal → $SKILL_DIR"

echo ""
echo "Deploy complete for $PLATFORM"
echo "  CLAUDE.md: $CTF_DIR/CLAUDE.md"
echo "  Skills:    $SKILL_DIR"
