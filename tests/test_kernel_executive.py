"""Tests for Kernel Executive scheduler."""

from sensos.kernel.executive import KernelExecutive
from sensos.runtime.plugins.mock_gpt import MockGPTPlugin


def test_kernel_executive_reaches_continue(memory, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    executive = KernelExecutive(
        runtime=MockGPTPlugin(),
        memory=memory,
        verbose=False,
    )
    result = executive.run_cycle_structured("Evaluate safety parameters.", max_iterations=3)
    assert result.steps_executed >= 1
    assert result.outcome
