import os
import json

# 읽기를 건너뛸 디렉토리 이름
SKIP_DIRS = {
    '__pycache__', '.git', 'venv', '.venv', 'node_modules',
    '.idea', '.vscode', 'dist', 'build', '.mypy_cache', '.pytest_cache'
}

# 읽기를 건너뛸 확장자 (바이너리/불필요 파일)
SKIP_EXTENSIONS = {
    '.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe',
    '.jpg', '.jpeg', '.png', '.gif', '.ico', '.svg',
    '.zip', '.tar', '.gz', '.rar',
    '.DS_Store', '.lock'
}

MAX_FILE_SIZE = 50 * 1024       # 파일 1개당 최대 50KB
MAX_TOTAL_SIZE = 700 * 1024     # 전체 합계 최대 700KB (여유 있게 1MB 미만 유지)


def register(mcp):
    @mcp.tool()
    def file_analysis(file_path: str) -> str:
        """
        CTF 문제의 소스코드/설정 파일을 분석합니다.
        디렉토리를 지정하면 내부의 텍스트 파일을 읽어 반환합니다.
        (venv, __pycache__, node_modules 등 불필요한 디렉토리 자동 제외)
        """
        results = {}
        total_size = 0

        if os.path.isdir(file_path):
            for root, dirs, files in os.walk(file_path):
                # 건너뛸 디렉토리 필터링 (in-place 수정으로 하위 탐색 차단)
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

                for fname in files:
                    # 건너뛸 확장자 필터링
                    _, ext = os.path.splitext(fname)
                    # .env 계열 파일은 예외적으로 허용 (CTF 문제 분석에 필요)
                    is_dotenv = fname == '.env' or fname.startswith('.env.')
                    if ext.lower() in SKIP_EXTENSIONS:
                        continue
                    if fname.startswith('.') and not is_dotenv:
                        continue

                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, file_path)

                    try:
                        file_size = os.path.getsize(fpath)

                        # 파일 개별 크기 초과 시 메타정보만 기록
                        if file_size > MAX_FILE_SIZE:
                            results[rel_path] = f"[파일 크기 초과: {file_size // 1024}KB — 직접 지정하여 읽으세요]"
                            continue

                        # 전체 누적 크기 초과 시 중단
                        if total_size + file_size > MAX_TOTAL_SIZE:
                            results["__truncated__"] = f"총 크기 제한({MAX_TOTAL_SIZE // 1024}KB) 초과로 일부 파일 생략됨"
                            break

                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        results[rel_path] = content
                        total_size += file_size

                    except Exception as e:
                        results[rel_path] = f"[읽기 실패: {e}]"
                else:
                    continue
                break  # 내부 루프에서 break 시 외부도 중단

        elif os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # 단일 파일은 700KB까지 허용
                results[file_path] = content[:MAX_TOTAL_SIZE]
            except Exception as e:
                return json.dumps({"error": str(e)})
        else:
            return json.dumps({"error": f"경로를 찾을 수 없음: {file_path}"})

        return json.dumps(results, ensure_ascii=False, indent=2)