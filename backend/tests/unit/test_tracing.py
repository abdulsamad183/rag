from app.observability.tracing import TraceRecorder


def test_trace_emits_completed_steps():
    seen: list[str] = []
    recorder = TraceRecorder(on_emit=lambda step: seen.append(step.name))
    with recorder.step("generate", provider="mock"):
        pass
    recorder.add_step("confidence", score=0.8)
    assert seen == ["generate", "confidence"]
    assert recorder.steps[0].latency_ms >= 0
    assert recorder.steps_as_dicts()[1]["payload"]["score"] == 0.8


def test_trace_emit_failure_does_not_break_pipeline():
    def boom(_step):
        raise RuntimeError("ui down")

    recorder = TraceRecorder(on_emit=boom)
    with recorder.step("rerank"):
        pass
    assert len(recorder.steps) == 1
    assert recorder.steps[0].status == "ok"
