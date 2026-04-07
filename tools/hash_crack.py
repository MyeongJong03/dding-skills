import subprocess
import json
import hashlib
import re

# 일반 CTF 해시 타입 패턴
HASH_PATTERNS = [
    (r'^[a-f0-9]{32}$', "MD5", "0"),
    (r'^[a-f0-9]{40}$', "SHA1", "100"),
    (r'^[a-f0-9]{64}$', "SHA256", "1400"),
    (r'^[a-f0-9]{96}$', "SHA384", "10800"),
    (r'^[a-f0-9]{128}$', "SHA512", "1700"),
    (r'^\$2[aby]\$.{56}$', "bcrypt", "3200"),
    (r'^\$apr1\$', "MD5-APR", "1600"),
]

def identify_hash(hash_str: str) -> list:
    matches = []
    for pattern, name, hashcat_mode in HASH_PATTERNS:
        if re.match(pattern, hash_str.strip(), re.IGNORECASE):
            matches.append({"type": name, "hashcat_mode": hashcat_mode})
    return matches

def register(mcp):
    @mcp.tool()
    def hash_crack(
        hash_value: str,
        wordlist_path: str = "/Users/myeongjong/wordlists/rockyou.txt",
        hashcat_mode: str = None,
        extra_flags: str = ""
    ) -> str:
        """
        해시를 식별하고 hashcat으로 크랙을 시도합니다.
        hash_value: 크랙할 해시값
        wordlist_path: 워드리스트 경로 (기본: rockyou.txt)
        hashcat_mode: hashcat 모드 번호 (미입력 시 자동 감지)
        """
        result = {}

        # 해시 타입 식별
        identified = identify_hash(hash_value)
        result["identified_types"] = identified

        if not identified and not hashcat_mode:
            return json.dumps({
                "error": "해시 타입을 자동 감지할 수 없습니다. hashcat_mode를 직접 지정해 주세요.",
                "identified_types": []
            })

        mode = hashcat_mode or identified[0]["hashcat_mode"]

        # hashcat 크랙 시도
        try:
            cmd = [
                "hashcat", "-m", mode,
                hash_value, wordlist_path,
                "--quiet", "--potfile-disable"
            ] + extra_flags.split()

            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
                stdin=subprocess.DEVNULL
            )
            output = r.stdout.strip() + r.stderr.strip()

            # 크랙 성공 시 결과 파싱
            if ":" in output:
                for line in output.splitlines():
                    if hash_value.lower() in line.lower() and ":" in line:
                        cracked = line.split(":")[-1].strip()
                        result["cracked"] = cracked
                        break

            result["hashcat_output"] = output[:2000]
            result["return_code"] = r.returncode

        except FileNotFoundError:
            result["hashcat_error"] = "hashcat이 설치되어 있지 않습니다. brew install hashcat"
        except subprocess.TimeoutExpired:
            result["hashcat_error"] = "크랙 타임아웃 (60초 초과)"

        return json.dumps(result, ensure_ascii=False, indent=2)
