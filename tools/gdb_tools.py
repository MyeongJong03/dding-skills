import json

from ctf_solver_core.gdb_session import (
    backtrace,
    close_gdb,
    continue_gdb,
    list_gdb_sessions,
    registers,
    run_gdb_cmd,
    start_gdb,
    telescope,
    vmmap,
    wait_crash,
)


def _json_result(callback, *args, **kwargs) -> str:
    try:
        return json.dumps(callback(*args, **kwargs), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True)


def register(mcp):
    @mcp.tool()
    def gdb_start(
        binary: str,
        mode: str = "docker",
        workspace: str = None,
        run_id: str = None,
        challenge_id: str = None,
        worker_id: str = None,
        args: str = None,
        breakpoint: list[str] = None,
        image: str = "ctf-pwn:latest",
        timeout_ms: int = 2000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Start a local-only GDB debug session for a challenge binary.
        mode is docker, local, or mock; docker uses ctf-pwn:latest by default.
        """
        return _json_result(
            start_gdb,
            binary_path=binary,
            mode=mode,
            workspace=workspace,
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            args=args,
            breakpoint=breakpoint or [],
            image=image,
            timeout_ms=timeout_ms,
            max_bytes=max_bytes,
        )

    @mcp.tool()
    def gdb_cmd(
        gdb_session_id: str,
        cmd: str,
        timeout_ms: int = 2000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Run one bounded GDB command and return redacted output.
        Do not use this to dump large memory regions.
        """
        return _json_result(run_gdb_cmd, gdb_session_id, cmd, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def gdb_continue(
        gdb_session_id: str,
        timeout_ms: int = 2000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Continue execution in a GDB session and parse crash status if present.
        """
        return _json_result(continue_gdb, gdb_session_id, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def gdb_wait_crash(
        gdb_session_id: str,
        timeout_ms: int = 5000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Continue execution and wait for SIGSEGV/SIGABRT-style crash output.
        """
        return _json_result(wait_crash, gdb_session_id, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def gdb_registers(
        gdb_session_id: str,
        timeout_ms: int = 2000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Run info registers and parse register values into JSON where possible.
        """
        return _json_result(registers, gdb_session_id, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def gdb_backtrace(
        gdb_session_id: str,
        timeout_ms: int = 2000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Run bt and return a bounded public-safe backtrace summary.
        """
        return _json_result(backtrace, gdb_session_id, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def gdb_vmmap(
        gdb_session_id: str,
        timeout_ms: int = 2000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Run pwndbg vmmap with an info proc mappings fallback and parse mappings.
        """
        return _json_result(vmmap, gdb_session_id, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def gdb_telescope(
        gdb_session_id: str,
        address: str,
        count: int = 8,
        timeout_ms: int = 2000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Run pwndbg telescope or a bounded x/gx fallback at the requested address.
        """
        return _json_result(
            telescope,
            gdb_session_id,
            address=address,
            count=count,
            timeout_ms=timeout_ms,
            max_bytes=max_bytes,
        )

    @mcp.tool()
    def gdb_close(gdb_session_id: str, reason: str = "closed") -> str:
        """
        Close one GDB session and terminate the backing process/container.
        """
        return _json_result(close_gdb, gdb_session_id, reason=reason)

    @mcp.tool()
    def gdb_list(
        run_id: str = None,
        challenge_id: str = None,
        include_closed: bool = False,
    ) -> str:
        """
        List GDB sessions without raw logs, transcripts, core dumps, or memory dumps.
        """
        return _json_result(
            list_gdb_sessions,
            run_id=run_id,
            challenge_id=challenge_id,
            include_closed=include_closed,
        )
