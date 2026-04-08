#!/bin/bash
# dding-skills 설치 스크립트
# 사용법: bash install.sh [mac|windows]
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
OS="${1:-mac}"

echo "=== dding-skills 설치 시작 (${OS}) ==="

# 1. ctf-personal 스킬 심볼릭 링크
SKILLS_DIR="$HOME/.agents/skills"
mkdir -p "$SKILLS_DIR"
if [ -e "$SKILLS_DIR/ctf-personal" ] && [ ! -L "$SKILLS_DIR/ctf-personal" ]; then
    echo "[백업] ~/.agents/skills/ctf-personal → ctf-personal.bak"
    mv "$SKILLS_DIR/ctf-personal" "$SKILLS_DIR/ctf-personal.bak"
fi
ln -sf "$REPO_DIR/skills/ctf-personal" "$SKILLS_DIR/ctf-personal"
echo "[완료] ~/.agents/skills/ctf-personal → 저장소 연결"

# 2. CLAUDE.md 심볼릭 링크
CTF_DIR="$HOME/CTF"
mkdir -p "$CTF_DIR"
if [ -f "$CTF_DIR/CLAUDE.md" ] && [ ! -L "$CTF_DIR/CLAUDE.md" ]; then
    echo "[백업] ~/CTF/CLAUDE.md → CLAUDE.md.bak"
    mv "$CTF_DIR/CLAUDE.md" "$CTF_DIR/CLAUDE.md.bak"
fi
if [ "$OS" = "mac" ]; then
    ln -sf "$REPO_DIR/config/mac/CLAUDE.md" "$CTF_DIR/CLAUDE.md"
else
    ln -sf "$REPO_DIR/config/windows/CLAUDE.md" "$CTF_DIR/CLAUDE.md"
fi
echo "[완료] ~/CTF/CLAUDE.md → 저장소 연결"

# 3. MCP 서버 등록
if command -v uv &>/dev/null; then
    UV_BIN="$(which uv)"
else
    UV_BIN="$HOME/.local/bin/uv"
fi

echo "[등록] Claude Code MCP 서버 등록 중..."
claude mcp add --scope user ctf_solver \
    -- "$UV_BIN" run --with "mcp[cli]" --with requests --with httpx \
    mcp run "$REPO_DIR/server.py"
echo "[완료] MCP 서버 등록 완료"

# 4. 외부 CTF 스킬 설치
if command -v npx &>/dev/null; then
    echo "[설치] CTF 스킬 설치 중 (ljagiello/ctf-skills)..."
    npx skills install ljagiello/ctf-skills
    echo "[완료] CTF 스킬 설치 완료"
else
    echo "[건너뜀] npx 없음 — 수동으로 실행: npx skills install ljagiello/ctf-skills"
fi

# 5. Docker 이미지 빌드
if command -v docker &>/dev/null; then
    echo "[빌드] ctf-pwn Docker 이미지 빌드 중..."
    docker build --platform linux/amd64 -f "$REPO_DIR/Dockerfile.ctf" -t ctf-pwn:latest "$REPO_DIR"
    echo "[완료] Docker 이미지 빌드 완료"
else
    echo "[건너뜀] docker 없음 — Docker 설치 후 수동으로 실행:"
    echo "  docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest ."
fi

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "환경 변수 설정 (선택):"
echo "  export SAGE_PATH=/path/to/sage     # SageMath 경로 (기본: macOS 앱 경로)"
echo ""
echo "추가 설정:"
echo "  ~/wordlists/rockyou.txt            # rockyou 워드리스트 위치"
echo "  ~/RsaCtfTool/                      # RSActfTool 위치 (또는 pip install rsactftool)"
