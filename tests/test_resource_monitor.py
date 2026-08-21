from harako_gpu.adapters.resources import parse_trace_counts


def test_trace_counts_classify_completed_cached_failed() -> None:
    text = "task_id\tprocess\tstatus\n1\tA\tCOMPLETED\n2\tB\tCACHED\n3\tC\tFAILED\n"
    assert parse_trace_counts(text) == {"completed": 1, "cached": 1, "failed": 1}
