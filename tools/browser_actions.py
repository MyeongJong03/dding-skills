import json

from ctf_solver_core.browser_client import (
    browser_click as core_browser_click,
    browser_close as core_browser_close,
    browser_console as core_browser_console,
    browser_cookies as core_browser_cookies,
    browser_eval as core_browser_eval,
    browser_fill as core_browser_fill,
    browser_goto as core_browser_goto,
    browser_list as core_browser_list,
    browser_network as core_browser_network,
    browser_screenshot as core_browser_screenshot,
    browser_start as core_browser_start,
    browser_upload as core_browser_upload,
)


def _json_result(callback, *args, **kwargs) -> str:
    try:
        return json.dumps(callback(*args, **kwargs), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True)


def register(mcp):
    @mcp.tool()
    def browser_start(
        run_id: str = None,
        challenge_id: str = None,
        worker_id: str = None,
        platform: str = None,
        event: str = None,
        profile: str = None,
        storage_state: str = None,
        browser_type: str = "chromium",
        headless: bool = True,
    ) -> str:
        """
        Start a local-only Playwright browser session via the loopback browser daemon.
        Use run_id/challenge_id to isolate concurrent CTF work. Playwright is optional;
        missing installs return reason=playwright_not_installed.
        """
        return _json_result(
            core_browser_start,
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            platform=platform,
            event=event,
            profile=profile,
            storage_state=storage_state,
            browser_type=browser_type,
            headless=headless,
        )

    @mcp.tool()
    def browser_goto(browser_session_id: str, url: str, timeout_ms: int = 10000, wait_until: str = "load") -> str:
        """
        Navigate an active browser session to a URL. URLs in output are redacted.
        Regression tests must use local file, data URL, or mock server targets.
        """
        return _json_result(core_browser_goto, browser_session_id, url=url, timeout_ms=timeout_ms, wait_until=wait_until)

    @mcp.tool()
    def browser_click(browser_session_id: str, selector: str, timeout_ms: int = 10000) -> str:
        """
        Click a selector in an active browser session.
        """
        return _json_result(core_browser_click, browser_session_id, selector=selector, timeout_ms=timeout_ms)

    @mcp.tool()
    def browser_fill(browser_session_id: str, selector: str, value: str, timeout_ms: int = 10000) -> str:
        """
        Fill a selector in an active browser session. Filled values are not echoed.
        """
        return _json_result(core_browser_fill, browser_session_id, selector=selector, value=value, timeout_ms=timeout_ms)

    @mcp.tool()
    def browser_upload(browser_session_id: str, selector: str, files: list[str], timeout_ms: int = 10000) -> str:
        """
        Upload one or more local files through a file input. Output includes only file counts.
        """
        return _json_result(core_browser_upload, browser_session_id, selector=selector, files=files or [], timeout_ms=timeout_ms)

    @mcp.tool()
    def browser_eval(browser_session_id: str, expression: str, timeout_ms: int = 10000, max_bytes: int = 4000) -> str:
        """
        Evaluate JavaScript and return a bounded, redacted result preview.
        """
        return _json_result(
            core_browser_eval,
            browser_session_id,
            expression=expression,
            timeout_ms=timeout_ms,
            max_bytes=max_bytes,
        )

    @mcp.tool()
    def browser_screenshot(browser_session_id: str, name: str = None, full_page: bool = False) -> str:
        """
        Save a screenshot under the local-only browser artifact root, never in the repo by default.
        """
        return _json_result(core_browser_screenshot, browser_session_id, name=name, full_page=full_page)

    @mcp.tool()
    def browser_console(browser_session_id: str, limit: int = 50) -> str:
        """
        Return bounded, redacted console events for a browser session.
        """
        return _json_result(core_browser_console, browser_session_id, limit=limit)

    @mcp.tool()
    def browser_network(browser_session_id: str, limit: int = 50) -> str:
        """
        Return bounded, redacted request/response summaries without bodies or raw cookies.
        """
        return _json_result(core_browser_network, browser_session_id, limit=limit)

    @mcp.tool()
    def browser_cookies(browser_session_id: str) -> str:
        """
        Return redacted cookie summaries. Raw cookie values are never returned.
        """
        return _json_result(core_browser_cookies, browser_session_id)

    @mcp.tool()
    def browser_close(browser_session_id: str, reason: str = "closed") -> str:
        """
        Close one browser session and persist local-only closed metadata.
        """
        return _json_result(core_browser_close, browser_session_id, reason=reason)

    @mcp.tool()
    def browser_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str:
        """
        List browser sessions, optionally filtered by run_id or challenge_id.
        Closed sessions are hidden unless include_closed is true.
        """
        return _json_result(
            core_browser_list,
            run_id=run_id,
            challenge_id=challenge_id,
            include_closed=include_closed,
        )
