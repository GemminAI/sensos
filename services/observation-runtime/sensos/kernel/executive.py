"""Kernel Executive — central SensOS operating manager."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from sensos.abi.nvs76.stream import SemanticStream
from sensos.abi.nvs76.trajectory import SemanticTrajectory
from sensos.dak.decision import DAKDecision
from sensos.dak.kernel import TrajectoryDifferentialSafetyKernel
from sensos.memory.crystallized import CrystallizedMemoryStorage
from sensos.observation.engine import ObservationEngine
from sensos.runtime.plugin import RuntimePlugin


@dataclass
class SchedulerCycleResult:
    """Structured outcome of a kernel scheduler run."""

    outcome: str
    steps_executed: int
    final_decision: Optional[DAKDecision] = None
    final_risk: Optional[float] = None


class KernelExecutive:
    """
    The central operating manager of SensOS. Orchestrates the scheduler loop:
    Pre-Observation -> CPU Execution -> Post-Observation -> DAK Auditing -> Action Dispatch.
    """

    def __init__(
        self,
        runtime: RuntimePlugin,
        memory: CrystallizedMemoryStorage,
        *,
        observation_engine: Optional[ObservationEngine] = None,
        stream_id: str = "kernel_stream_0",
        trajectory_window: int = 5,
        dak: Optional[TrajectoryDifferentialSafetyKernel] = None,
        verbose: bool = True,
    ):
        self.runtime = runtime
        self.memory = memory
        self.verbose = verbose

        self.observation_engine = observation_engine or ObservationEngine()
        self.stream = SemanticStream(stream_id=stream_id)
        self.trajectory = SemanticTrajectory(self.stream, window_size=trajectory_window)
        self.dak = dak or TrajectoryDifferentialSafetyKernel()

    def run_cycle(self, initial_reality_prompt: str, max_iterations: int = 4) -> str:
        result = self.run_cycle_structured(initial_reality_prompt, max_iterations=max_iterations)
        return result.outcome

    def run_cycle_structured(
        self,
        initial_reality_prompt: str,
        max_iterations: int = 4,
    ) -> SchedulerCycleResult:
        self._log(f"\033[94m[Reality Stream Input]\033[0m {initial_reality_prompt}")
        self._log(f"\033[90m[SensOS Boot] Mounted pluggable CPU: {self.runtime.get_name()}\033[0m")

        current_prompt = initial_reality_prompt
        system_directive = (
            "You are the Core Reasoning Runtime acting inside SensOS v2.0.\n"
            "Your output must align with crystallized safe states, maintaining zero logical contradictions."
        )

        final_decision: Optional[DAKDecision] = None
        final_risk: Optional[float] = None

        for step in range(1, max_iterations + 1):
            self._log(f"\n\033[1m┌─── SCHEDULER CYCLE {step} ──────────────────────────────────────\033[0m")

            context = {"safe_memories": self.memory.safe_pathways}
            pre_obj = self.observation_engine.observe(step, current_prompt, context)
            self._log(f"\033[90m[Pre-Observe ABI] Target state hash: {pre_obj.state_hash}\033[0m")

            self._log(f"\033[93m[CPU Execution] Invoking {self.runtime.get_name()}...\033[0m")
            raw_response = self.runtime.execute(current_prompt, system_directive)

            post_obj = self.observation_engine.observe(step, raw_response, context)
            self.stream.append(post_obj)

            self._log("\n\033[96m[Observation Object ABI Output (RFC-NVS74)]\033[0m")
            self._log(json.dumps(post_obj.to_dict(), indent=2))

            risk, decision = self.dak.evaluate(self.trajectory)
            final_decision = decision
            final_risk = risk
            self._log(f"\n\033[1m[DAK Auditing Results]\033[0m")
            self._log(f"Calculated Dynamic Risk (RH): \033[91m{risk:.4f}\033[0m")
            self._log(f"Dispatched DAK Decision:      \033[1m\033[95m{decision.value}\033[0m")

            if decision == DAKDecision.CONTINUE:
                self._log("\033[92m✔ [EXECUTIVE ACTION: CONTINUE] State verified. Local action authorized.\033[0m")
                return SchedulerCycleResult(
                    outcome=raw_response,
                    steps_executed=step,
                    final_decision=decision,
                    final_risk=risk,
                )

            if decision == DAKDecision.CORRECT:
                self._log("\033[93m⚠ [EXECUTIVE ACTION: CORRECT] Local deviation. Rewriting trajectory prompts...\033[0m")
                current_prompt = (
                    f"OBSERVATION CORRECTIVE INTERRUPT.\n"
                    f"Your last output generated high curvature (κ={post_obj.metrics['curvature_kappa']:.2f}) "
                    f"and low memory matching.\n"
                    f"Please rewrite the logic. Align strictly with crystallized parameters. "
                    f"Eliminate contradiction markers.\n"
                    f"Draft to correct:\n---\n{raw_response}\n---\n"
                )
                continue

            if decision == DAKDecision.RETRIEVE:
                self._log("\033[94mℹ [EXECUTIVE ACTION: RETRIEVE] Pulling safe crystallized memory block...\033[0m")
                recovered_pattern = self.memory.query_nearest(self.trajectory.get_current_trajectory())
                current_prompt = (
                    f"OBSERVATION EXCEPTION. Memory Injection triggered.\n"
                    f"Anchor template applied: {recovered_pattern}\n"
                    f"Please reformulate and stabilize the output state immediately."
                )
                continue

            if decision == DAKDecision.ESCALATE:
                self._log(
                    "\033[91m⚡ [EXECUTIVE ACTION: ESCALATE] Escalation threshold breached. "
                    "Handing off execution.\033[0m"
                )
                return SchedulerCycleResult(
                    outcome=(
                        f"[Kernel Escalate] Trajectory unstable (Risk {risk:.4f}). "
                        "Context handed over to safe recovery pipeline."
                    ),
                    steps_executed=step,
                    final_decision=decision,
                    final_risk=risk,
                )

            if decision == DAKDecision.ABORT:
                self._log("\033[91m✖ [EXECUTIVE ACTION: ABORT] Critical safety breach. Shutting down runtime.\033[0m")
                return SchedulerCycleResult(
                    outcome="[Kernel Halt] Run aborted due to terminal trajectory divergence.",
                    steps_executed=step,
                    final_decision=decision,
                    final_risk=risk,
                )

        return SchedulerCycleResult(
            outcome="Scheduler threshold exceeded. Execution timeout without state crystallization.",
            steps_executed=max_iterations,
            final_decision=final_decision,
            final_risk=final_risk,
        )

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)
