import json

from ctf_solver_core.verifier import verify_run as core_verify_run


def _json_result(callback, *args, **kwargs) -> str:
    try:
        return json.dumps(callback(*args, **kwargs), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True)


def register(mcp):
    @mcp.tool()
    def verify_run(
        mode: str,
        run_dir: str = None,
        command: str = None,
        cwd: str = None,
        timeout_sec: int = 30,
        retries: int = 0,
        flag_regex: str = None,
        success_regex: str = None,
        fail_regex: str = None,
        session_id: str = None,
        session_input: str = None,
        expect: list[str] = None,
        evidence_text: str = None,
        target: str = "unknown",
        local: bool = False,
        remote: bool = False,
        label: str = "",
        save: bool = True,
        save_evidence: bool = False,
        max_output_bytes: int = 8000,
    ) -> str:
        """
        Verify solve evidence for a tracked challenge run.
        Supports command, session, and manual modes. Output is bounded and redacted;
        raw flag values and raw transcripts are not returned by default.
        """
        return _json_result(
            core_verify_run,
            mode=mode,
            run_dir=run_dir,
            command=command,
            cwd=cwd,
            timeout_sec=timeout_sec,
            retries=retries,
            flag_regex=flag_regex,
            success_regex=success_regex,
            fail_regex=fail_regex,
            session_id=session_id,
            session_input=session_input,
            expect=expect or [],
            evidence_text=evidence_text,
            target=target,
            local=local,
            remote=remote,
            label=label,
            save_result=save,
            save_evidence=save_evidence,
            redact_output=True,
            max_output_bytes=max_output_bytes,
        )
