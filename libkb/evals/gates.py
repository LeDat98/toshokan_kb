"""Pass/fail gates for an eval report (P3, principle P8 — eval-gated changes).

Armed from the A/B (D-031), and ONLY from it. The gate is `answer_acc`, measured
`--mode walk --cases evals/holdout.json` (held-out paraphrases, no catalog):

    routing_mode=shelf  →  answer_acc 96.7%   ← the shipped default, and the baseline
    routing_mode=book   →  answer_acc 90.0%   ← the control it replaced

`min_answer_acc = 0.90` sits ~1.6 standard errors below the shelf baseline (se ≈ 0.033 at n=30,
p≈0.97), so ordinary sampling noise does not trip it — but a regression all the way back to the
book-gated walk lands exactly ON the line, which is the property we want.

The other two gates stay `None` by design. `page_acc` in particular must NOT be gated: it scores a
walk by whether it reached the exact page a question was generated from, and a walk that answers
perfectly from a *sibling* page is scored a miss. Gating it would punish the system for being right
(see evals/judge.py).

Re-tune after any change that moves the baseline (routing mode, descriptions, model tier), and
re-measure on the SAME held-out case file — a gate calibrated on the leaked set protects nothing.
Later these same gates protect tree refactors (P4): a rebalance that drops answer_acc auto-reverts.
"""

from __future__ import annotations

from dataclasses import dataclass

from libkb.evals.runner import EvalReport


@dataclass
class EvalGates:
    """`None` = not armed. The primary gate is answer_acc; the others are diagnostics and stay
    unarmed on purpose (a page_acc gate punishes answering correctly from a sibling page)."""

    min_answer_acc: float | None = 0.90  # shelf baseline 96.7% − 1.6 se (D-031)
    min_page_acc: float | None = None
    min_book_acc: float | None = None

    @property
    def armed(self) -> bool:
        return any(
            v is not None for v in (self.min_answer_acc, self.min_page_acc, self.min_book_acc)
        )


def check_gates(report: EvalReport, gates: EvalGates | None = None) -> tuple[bool, list[str]]:
    gates = gates or EvalGates()
    failures: list[str] = []
    if gates.min_answer_acc is not None and report.answer_acc < gates.min_answer_acc:
        failures.append(f"answer_acc {report.answer_acc:.2f} < min {gates.min_answer_acc:.2f}")
    if gates.min_page_acc is not None and report.page_acc < gates.min_page_acc:
        failures.append(f"page_acc {report.page_acc:.2f} < min {gates.min_page_acc:.2f}")
    if gates.min_book_acc is not None and report.book_acc < gates.min_book_acc:
        failures.append(f"book_acc {report.book_acc:.2f} < min {gates.min_book_acc:.2f}")
    return (not failures, failures)
