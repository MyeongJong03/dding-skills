import json

from ctf_solver_core.callback_client import (
    callback_close as core_callback_close,
    callback_hits as core_callback_hits,
    callback_list as core_callback_list,
    callback_start as core_callback_start,
    callback_url as core_callback_url,
    callback_wait as core_callback_wait,
    web_payload_helper as core_web_payload_helper,
)


def _json_result(callback, *args, **kwargs) -> str:
    try:
        return json.dumps(callback(*args, **kwargs), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True)


def register(mcp):
    @mcp.tool()
    def callback_start(
        run_id: str = None,
        challenge_id: str = None,
        worker_id: str = None,
        host: str = "127.0.0.1",
        port: str = None,
        external_base_url: str = None,
        token_path: str = None,
        allow_public_bind: bool = False,
    ) -> str:
        """
        Start a local-only web callback listener through the loopback callback daemon.
        Default bind is 127.0.0.1. Public binds require allow_public_bind.
        External URLs are metadata only and must be supplied manually.
        """
        return _json_result(
            core_callback_start,
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            host=host,
            port=port,
            external_base_url=external_base_url,
            token_path=token_path,
            allow_public_bind=allow_public_bind,
        )

    @mcp.tool()
    def callback_url(listener_id: str, external: bool = False, path: str = None) -> str:
        """
        Return a local or manually configured external callback URL for a listener.
        No tunnel provider is started.
        """
        return _json_result(core_callback_url, listener_id, external=external, path=path)

    @mcp.tool()
    def callback_hits(listener_id: str, since_hit_id: str = None, limit: int = 20) -> str:
        """
        Return bounded, redacted callback hits. Cookies, auth headers, token-like
        query/body fields, and flag-like values are redacted.
        """
        return _json_result(core_callback_hits, listener_id, since_hit_id=since_hit_id, limit=limit)

    @mcp.tool()
    def callback_wait(listener_id: str, timeout_sec: float = 30, pattern: str = None, min_hits: int = 1) -> str:
        """
        Wait for callback hits without busy looping. Pattern matching is performed
        over redacted hit summaries.
        """
        return _json_result(
            core_callback_wait,
            listener_id,
            timeout_sec=timeout_sec,
            pattern=pattern,
            min_hits=min_hits,
        )

    @mcp.tool()
    def callback_close(listener_id: str, reason: str = "closed") -> str:
        """
        Close one callback listener and persist local-only closed metadata.
        """
        return _json_result(core_callback_close, listener_id, reason=reason)

    @mcp.tool()
    def callback_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str:
        """
        List callback listeners, optionally filtered by run_id or challenge_id.
        Closed listeners are hidden unless include_closed is true.
        """
        return _json_result(
            core_callback_list,
            run_id=run_id,
            challenge_id=challenge_id,
            include_closed=include_closed,
        )

    @mcp.tool()
    def web_payload_helper(callback_url: str) -> str:
        """
        Generate simple XSS/SSRF/CSS callback payload snippets for a supplied URL.
        This is a helper scaffold only and does not run an exploit or tunnel.
        """
        return _json_result(core_web_payload_helper, callback_url)
