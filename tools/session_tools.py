import json

from ctf_solver_core.session_client import (
    close_session,
    expect_session,
    list_sessions,
    read_session,
    start_session,
    write_session,
)


def _json_result(callback, *args, **kwargs) -> str:
    try:
        return json.dumps(callback(*args, **kwargs), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True)


def _env_from_json(env_json: str | None) -> dict[str, str] | None:
    if not env_json:
        return None
    parsed = json.loads(env_json)
    if not isinstance(parsed, dict):
        raise ValueError("env_json must decode to a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


def register(mcp):
    @mcp.tool()
    def session_start(
        kind: str,
        command: str = None,
        cwd: str = None,
        run_id: str = None,
        challenge_id: str = None,
        worker_id: str = None,
        host: str = None,
        port: str = None,
        image: str = None,
        workspace: str = None,
        timeout_ms: int = 1000,
        env_json: str = None,
    ) -> str:
        """
        Start a persistent local session via the loopback-only session daemon.
        kind: shell, python, sage, nc, or docker-shell.
        Associate run_id/challenge_id when solving a tracked challenge.
        """
        return _json_result(
            start_session,
            kind=kind,
            command=command,
            cwd=cwd,
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            host=host,
            port=port,
            image=image,
            workspace=workspace,
            timeout_ms=timeout_ms,
            env=_env_from_json(env_json),
        )

    @mcp.tool()
    def session_write(
        session_id: str,
        data: str,
        newline: bool = True,
        encoding: str = "text",
    ) -> str:
        """
        Write text or base64 data to a persistent session.
        newline defaults to true for menu prompts and REPL commands.
        """
        return _json_result(write_session, session_id, data, newline=newline, encoding=encoding)

    @mcp.tool()
    def session_read(
        session_id: str,
        timeout_ms: int = 1000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Read bounded output from a persistent session without closing it.
        Use timeout_ms and max_bytes to avoid blocking or large transcripts.
        """
        return _json_result(read_session, session_id, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def session_expect(
        session_id: str,
        patterns: list[str],
        timeout_ms: int = 1000,
        max_bytes: int = 8000,
    ) -> str:
        """
        Read until one literal pattern appears or timeout expires.
        Returns the matched pattern index, timeout status, and bounded output.
        """
        return _json_result(expect_session, session_id, patterns, timeout_ms=timeout_ms, max_bytes=max_bytes)

    @mcp.tool()
    def session_close(session_id: str, reason: str = "closed") -> str:
        """
        Close one persistent session and terminate its child process safely.
        """
        return _json_result(close_session, session_id, reason=reason)

    @mcp.tool()
    def session_list(
        run_id: str = None,
        challenge_id: str = None,
        include_closed: bool = False,
    ) -> str:
        """
        List persistent sessions, optionally filtered by run_id or challenge_id.
        Closed sessions are hidden unless include_closed is true.
        """
        return _json_result(
            list_sessions,
            run_id=run_id,
            challenge_id=challenge_id,
            include_closed=include_closed,
        )
