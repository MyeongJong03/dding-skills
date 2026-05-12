import json

from ctf_solver_core.web_workflow import (
    browser_probe as core_browser_probe,
    callback_probe as core_callback_probe,
    close_workflow as core_close_workflow,
    collect_evidence as core_collect_evidence,
    generate_payloads_for_workflow as core_generate_payloads,
    init_workflow as core_init_workflow,
    list_workflows as core_list_workflows,
)


def _json_result(callback, *args, **kwargs) -> str:
    try:
        return json.dumps(callback(*args, **kwargs), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True)


def _types(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in str(value).split(",") if item.strip()]


def register(mcp):
    @mcp.tool()
    def web_workflow_init(
        run_id: str = None,
        challenge_id: str = None,
        worker_id: str = None,
        target_url: str = None,
        start_browser: bool = False,
        start_callback: bool = False,
        browser_profile: str = None,
        external_base_url: str = None,
    ) -> str:
        """
        Initialize a local-only web exploit workflow and optionally start a
        browser session and callback listener associated with run_id.
        """
        return _json_result(
            core_init_workflow,
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            target_url=target_url,
            start_browser=start_browser,
            start_callback=start_callback,
            browser_profile=browser_profile,
            external_base_url=external_base_url,
        )

    @mcp.tool()
    def web_payload_generate(
        workflow_id: str = None,
        callback_url: str = None,
        types: str = None,
        target_param: str = None,
        encode: str = None,
    ) -> str:
        """
        Generate helper XSS/SSRF/CSP/CSS/file-upload payload snippets for a
        workflow callback URL. Snippets are helpers only and are not proof.
        """
        return _json_result(
            core_generate_payloads,
            workflow_id=workflow_id,
            callback_url=callback_url,
            types=_types(types),
            target_param=target_param,
            encode=encode,
        )

    @mcp.tool()
    def web_browser_probe(
        workflow_id: str,
        action: str,
        url: str = None,
        selector: str = None,
        value: str = None,
        file: str = None,
        expression: str = None,
        timeout_ms: int = None,
    ) -> str:
        """
        Run one bounded browser action through the workflow browser session.
        Actions are non-destructive scaffolding operations only.
        """
        return _json_result(
            core_browser_probe,
            workflow_id=workflow_id,
            action=action,
            url=url,
            selector=selector,
            value=value,
            file=file,
            expression=expression,
            timeout_ms=timeout_ms,
        )

    @mcp.tool()
    def web_callback_probe(
        workflow_id: str,
        wait_timeout_sec: float = 15,
        pattern: str = None,
        min_hits: int = 1,
    ) -> str:
        """
        Wait for workflow callback hits and store a redacted evidence summary.
        """
        return _json_result(
            core_callback_probe,
            workflow_id=workflow_id,
            wait_timeout_sec=wait_timeout_sec,
            pattern=pattern,
            min_hits=min_hits,
        )

    @mcp.tool()
    def web_evidence_collect(
        workflow_id: str,
        include_browser_summary: bool = False,
        include_callback_summary: bool = False,
        include_verifier_summary: bool = False,
    ) -> str:
        """
        Write a redacted local-only web workflow evidence bundle and summary.
        """
        return _json_result(
            core_collect_evidence,
            workflow_id=workflow_id,
            include_browser_summary=include_browser_summary,
            include_callback_summary=include_callback_summary,
            include_verifier_summary=include_verifier_summary,
        )

    @mcp.tool()
    def web_workflow_close(
        workflow_id: str,
        close_browser: bool = True,
        close_callback: bool = True,
        reason: str = "closed",
    ) -> str:
        """
        Close a web workflow and associated browser/callback resources by default.
        """
        return _json_result(
            core_close_workflow,
            workflow_id=workflow_id,
            close_browser=close_browser,
            close_callback=close_callback,
            reason=reason,
        )

    @mcp.tool()
    def web_workflow_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str:
        """
        List web workflows, optionally filtered by run_id or challenge_id.
        """
        return _json_result(
            core_list_workflows,
            run_id=run_id,
            challenge_id=challenge_id,
            include_closed=include_closed,
        )
