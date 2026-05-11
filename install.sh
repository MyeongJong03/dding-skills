#!/bin/bash
# dding-skills 설치 스크립트
# 사용법: bash install.sh [mac|windows]
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
OS="${1:-mac}"

echo "=== dding-skills 설치 시작 (${OS}) ==="

# 1. Codex/Claude 공통 설정 배포
if [ "$OS" != "mac" ] && [ "$OS" != "windows" ]; then
    echo "Usage: bash install.sh [mac|windows]"
    exit 1
fi

echo "[배포] config/deploy.sh ${OS}"
bash "$REPO_DIR/config/deploy.sh" "$OS"

# 2. Claude Code MCP 서버 등록 (optional/legacy compatibility)
if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(which uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
    UV_BIN="$HOME/.local/bin/uv"
else
    UV_BIN=""
fi

if command -v claude >/dev/null 2>&1 && [ -n "$UV_BIN" ]; then
    echo "[등록] Claude Code MCP 서버 등록 중... (ctf_solver)"
    if claude mcp add --scope user ctf_solver \
        -- "$UV_BIN" run --with "mcp[cli]" --with requests --with httpx \
        mcp run "$REPO_DIR/server.py"; then
        echo "[완료] Claude MCP 서버 등록 완료"
    else
        echo "[건너뜀] Claude MCP 등록 실패 — Codex-first 설치는 계속 진행"
    fi
else
    echo "[건너뜀] claude 또는 uv 없음 — Claude MCP 등록은 optional"
fi

# 3. 외부 CTF 스킬 설치
if command -v npx >/dev/null 2>&1; then
    echo "[설치] CTF 스킬 설치 중 (ljagiello/ctf-skills)..."
    if npx skills install ljagiello/ctf-skills; then
        echo "[완료] CTF 스킬 설치 완료"
    else
        echo "[건너뜀] 외부 CTF 스킬 설치 실패 — 수동 설치 가능"
    fi
else
    echo "[건너뜀] npx 없음 — 수동으로 실행: npx skills install ljagiello/ctf-skills"
fi

# 4. Docker 이미지 빌드
if command -v docker >/dev/null 2>&1; then
    if ! docker info >/dev/null 2>&1; then
        echo "[건너뜀] Docker daemon off — Docker Desktop 실행 후 수동 빌드"
        echo "  docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest ."
    else
        echo "[빌드] ctf-pwn Docker 이미지 빌드 중..."
        docker build --platform linux/amd64 -f "$REPO_DIR/Dockerfile.ctf" -t ctf-pwn:latest "$REPO_DIR"
        echo "[완료] Docker 이미지 빌드 완료"
    fi
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
