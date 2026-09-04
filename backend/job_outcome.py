def normalize_job_outcome(status: str | None, outcome: object) -> str:
    """Keep execution lifecycle separate from the agent-reported task outcome."""
    if status == "failed":
        return "unknown" if outcome == "unknown" else "blocked"
    # A finished call is not proof of success; old records and invalid model
    # metadata remain unknown. Active jobs cannot expose a stale terminal result.
    if status == "completed" and isinstance(outcome, str):
        if outcome in {"done", "blocked", "needs_input"}:
            return outcome
    return "unknown"
