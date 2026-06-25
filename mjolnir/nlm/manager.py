"""NetworkLifecycleManager: the brain that schedules stage execution.

Main loop: find_eligible_work() -> execute() -> mark_exhausted. Kill-switch
and mode-toggled via system_state. Mode persisted across reboots.
"""
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mjolnir.config import BjornConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.repositories import RepositoryBundle, bundle_for
from mjolnir.nlm.executor import StageExecutor
from mjolnir.nlm.gates import GateEvaluator
from mjolnir.nlm.identity import IdentityResolver
from mjolnir.nlm.scope import ScopeChecker
from mjolnir.stages.base import Stage
from mjolnir.stages.registry import StageRegistry


@dataclass
class WorkItem:
    network_id: int
    stage_name: str


class NetworkLifecycleManager:
    """Schedules stage execution across all known networks."""

    def __init__(
        self,
        db_path: Path,
        config: BjornConfig,
        registry: StageRegistry,
        kill_switch_event: Any,
        executor: Any = None,
    ):
        self.db_path = Path(db_path)
        self.config = config
        self.registry = registry
        self.kill_switch_event = kill_switch_event
        self.scope_checker = ScopeChecker()
        self.identity_resolver = IdentityResolver()
        # Executor is injectable: production uses StageExecutor (subprocess,
        # RLIMIT_AS isolation); tests use InProcessExecutor (no fork, avoids
        # the ADR 0001 fork-from-multithreaded deadlock). If None, a
        # StageExecutor is constructed per-run_once() call (production path).
        self._executor = executor
        # Construct an initial GateEvaluator bound to a fresh bundle so
        # introspection (and tests) can confirm the NLM was wired
        # correctly at construction time. find_eligible_work() rebuilds
        # it with a fresh bundle on each pass because each pass opens
        # its own short-lived DB connection.
        conn, bundle = self._open_db()
        try:
            self.gate_evaluator = GateEvaluator(bundle)
        finally:
            conn.close()

    def _open_db(self) -> tuple[sqlite3.Connection, RepositoryBundle]:
        factory = ConnectionFactory(db_path=self.db_path)
        conn = factory.connect()
        return conn, bundle_for(conn)

    def find_eligible_work(self) -> list[tuple[Any, type[Stage]]]:
        """Find all (network, stage) pairs that can run right now."""
        if self.kill_switch_event.is_set():
            return []

        conn, bundle = self._open_db()
        try:
            global_mode = bundle.system_state.get_global_mode()
            eligible_stages = self.registry.stages_eligible_for_mode(global_mode)

            if not eligible_stages:
                return []

            gate_eval = GateEvaluator(bundle)
            self.gate_evaluator = gate_eval
            networks = bundle.networks.list_eligible_for_processing()
            work: list[tuple[Any, type[Stage]]] = []

            for net in networks:
                for stage_cls in eligible_stages:
                    scope_decision = self.scope_checker.check(
                        global_mode=global_mode,
                        kill_switch_engaged=False,
                        stage_operates_in_view_only=stage_cls.operates_in_view_only,
                        stage_requires_extra_auth=stage_cls.requires_extra_auth,
                        network=net,
                        host_persistence_authorized=None,
                    )
                    if not scope_decision.allowed:
                        continue

                    gate_result = gate_eval.evaluate(stage_cls.name, net.id)
                    # Unknown stages have no data prerequisites — treat as
                    # runnable. The GateEvaluator fails closed for unknown
                    # stages (safer default for the evaluator itself), but
                    # the NLM's scheduling decision is: a stage with no
                    # defined gate has no prerequisites.
                    if not gate_result.satisfied and not gate_result.reason.startswith("unknown_stage"):
                        continue

                    work.append((net, stage_cls))

            return work
        finally:
            conn.close()

    def run_once(self) -> int:
        """Single pass: find work, execute one item, return number executed."""
        work = self.find_eligible_work()
        if not work:
            return 0

        net, stage_cls = work[0]

        if self._executor is not None:
            executor = self._executor
        else:
            executor = StageExecutor(
                db_path=self.db_path,
                mem_limit_mb=self.config.nlm.stage_memory_limit_mb,
                kill_switch_event=self.kill_switch_event,
            )

        conn, bundle = self._open_db()
        try:
            bundle.stage_states.mark_running(net.id, stage_cls.name)
            bundle.networks.set_current_stage(net.id, stage_cls.name)
        finally:
            conn.close()

        result = executor.execute(
            stage_name=stage_cls.name,
            network_id=net.id,
            timeout_seconds=stage_cls.resources.est_duration_seconds * 3,
        )

        conn, bundle = self._open_db()
        try:
            if result.status == "succeeded":
                bundle.stage_states.mark_succeeded(net.id, stage_cls.name)
                if result.outputs:
                    bundle.stage_outputs.set_many(net.id, stage_cls.name, result.outputs)
            elif result.status == "permanently_failed":
                bundle.stage_states.mark_permanently_failed(net.id, stage_cls.name, result.error)
            else:
                bundle.stage_states.mark_failed(net.id, stage_cls.name, result.error)
            bundle.networks.set_current_stage(net.id, None)
        finally:
            conn.close()

        return 1
