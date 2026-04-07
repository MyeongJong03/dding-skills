import logging
import sys
from mcp.server.fastmcp import FastMCP

# STDIO 서버이므로 stdout 사용 금지 — stderr로 로깅
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("ctf_solver")

mcp = FastMCP("ctf_solver")

# === 도구 등록 ===
from tools.file_analysis import register as register_file_analysis
from tools.trivy_scan import register as register_trivy
from tools.cve_lookup import register as register_cve_lookup
from tools.python_exec import register as register_python_exec
from tools.port_scan import register as register_port_scan
from tools.http_request import register as register_http_request
from tools.binary_info import register as register_binary_info
from tools.netcat_interact import register as register_netcat_interact
from tools.dns_lookup import register as register_dns_lookup
from tools.hash_crack import register as register_hash_crack
from tools.rsa_ctftool import register as register_rsa_ctftool
from tools.sage_exec import register as register_sage_exec
from tools.docker_exec import register as register_docker_exec
from tools.dreamhack_vm import register as register_dreamhack_vm

register_file_analysis(mcp)
register_trivy(mcp)
register_cve_lookup(mcp)
register_python_exec(mcp)
register_port_scan(mcp)
register_http_request(mcp)
register_binary_info(mcp)
register_netcat_interact(mcp)
register_dns_lookup(mcp)
register_hash_crack(mcp)
register_rsa_ctftool(mcp)
register_sage_exec(mcp)
register_docker_exec(mcp)
register_dreamhack_vm(mcp)

if __name__ == "__main__":
    mcp.run()
