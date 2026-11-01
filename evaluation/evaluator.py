"""
PALIMPSEST Evaluator
Runs a scripted multi-turn conversation through both agents and records metrics.
"""

from __future__ import annotations

import time

from config import Config
from evaluation.baseline import BaselineAgent
from palimpsest.agent import PalimpsestAgent
from palimpsest.models import EvaluationReport

# Cost estimate: $0.15 per 1M tokens (gpt-4o-mini input pricing)
COST_PER_TOKEN = 0.15 / 1_000_000

# Default scripted conversation for evaluation
DEFAULT_SCRIPT = [
    {"user": "I want to build a REST API in Python using FastAPI.", "probe": False},
    {"user": "Use PostgreSQL as the database. Always use async SQLAlchemy.", "probe": False},
    {"user": "Authentication must use JWT tokens. Remember that.", "probe": False},
    {"user": "What's the capital of France?", "probe": False},
    {"user": "Tell me a joke about programming.", "probe": False},
    {"user": "What is machine learning in simple terms?", "probe": False},
    {"user": "Explain recursion with an example.", "probe": False},
    {"user": "What database should I use for this API project?", "probe": True, "expected": "postgresql"},
    {"user": "What authentication method should the API use?", "probe": True, "expected": "jwt"},
    {"user": "Which ORM should I use for the database?", "probe": True, "expected": "sqlalchemy"},
]


class Evaluator:
    """Compares PALIMPSEST vs Baseline on token efficiency, cost, latency, and memory quality."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.palimpsest = PalimpsestAgent(self.config)
        self.baseline = BaselineAgent(self.config)
        self.report = EvaluationReport()

    def run_comparison(
        self, conversation_script: list[dict] | None = None
    ) -> EvaluationReport:
        """Run the comparison and return the EvaluationReport."""
        script = conversation_script or DEFAULT_SCRIPT
        objective = "Build a REST API in Python using FastAPI."

        # Start sessions
        self.palimpsest.start_session(objective=objective)
        self.baseline.start_session(objective=objective)

        turns = []
        palimpsest_quality_hits = 0
        baseline_quality_hits = 0
        probe_count = 0

        for turn in script:
            user_msg = turn["user"]
            is_probe = turn.get("probe", False)
            expected = turn.get("expected", "").lower()

            # Run both agents
            t0 = time.time()
            p_response = self.palimpsest.chat(user_msg)
            p_latency = (time.time() - t0) * 1000

            t0 = time.time()
            b_response = self.baseline.chat(user_msg)
            b_latency = (time.time() - t0) * 1000

            turn_data = {
                "user": user_msg,
                "palimpsest_response": p_response[:200],
                "baseline_response": b_response[:200],
                "palimpsest_latency_ms": round(p_latency, 1),
                "baseline_latency_ms": round(b_latency, 1),
                "is_probe": is_probe,
            }

            if is_probe and expected:
                probe_count += 1
                p_hit = expected in p_response.lower()
                b_hit = expected in b_response.lower()
                palimpsest_quality_hits += int(p_hit)
                baseline_quality_hits += int(b_hit)
                turn_data["palimpsest_recalled"] = p_hit
                turn_data["baseline_recalled"] = b_hit
                turn_data["expected_keyword"] = expected

            turns.append(turn_data)

        # Build report
        p_metrics = {
            "total_tokens": self.palimpsest.total_tokens_used,
            "avg_latency_ms": self.palimpsest.total_latency_ms / max(self.palimpsest.turn_count, 1),
        }
        b_metrics = self.baseline.get_metrics()

        self.report = EvaluationReport(
            baseline_total_tokens=b_metrics["total_tokens"],
            palimpsest_total_tokens=p_metrics["total_tokens"],
            baseline_estimated_cost_usd=b_metrics["total_tokens"] * COST_PER_TOKEN,
            palimpsest_estimated_cost_usd=p_metrics["total_tokens"] * COST_PER_TOKEN,
            baseline_avg_latency_ms=b_metrics["avg_latency_ms"],
            palimpsest_avg_latency_ms=p_metrics["avg_latency_ms"],
            baseline_quality_score=baseline_quality_hits / max(probe_count, 1),
            palimpsest_quality_score=palimpsest_quality_hits / max(probe_count, 1),
            turns=turns,
            summary=self._generate_summary(p_metrics, b_metrics, palimpsest_quality_hits,
                                            baseline_quality_hits, probe_count),
        )
        return self.report

    def _generate_summary(self, p, b, p_hits, b_hits, probes) -> str:
        token_save = b["total_tokens"] - p["total_tokens"]
        pct = (token_save / max(b["total_tokens"], 1)) * 100
        return (
            f"PALIMPSEST used {p['total_tokens']} tokens vs Baseline's {b['total_tokens']} "
            f"({pct:.1f}% {'saved' if token_save >= 0 else 'more'}). "
            f"Memory recall: PALIMPSEST {p_hits}/{probes}, Baseline {b_hits}/{probes}."
        )
