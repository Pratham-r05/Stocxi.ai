"""
agent_verifier.py — Pure-Python Anti-Hallucination Gate.

Contract (AGENTS.md §4):
  Input:  AnalysisDraft + list[Node] (the original node set)
  Output: VerifiedAnalysis

Rules:
  - Pure Python. No LLM call. No network I/O.
  - Every claim's node_ids are checked against the supplied node set.
  - Claims with zero valid node_ids are stripped and counted.
  - Agreement / contradiction links whose node_ids are not in the supplied set are removed.
  - If stripped_claims > LOW_FIDELITY_THRESHOLD: set low_fidelity=True.
  - Verdict supporting_node_ids are filtered to only valid ids (not stripped,
    but invalid ids are silently removed).
  - This agent is NEVER skipped. AGENTS.md Rule 10.
"""

from __future__ import annotations

import logging

from schemas.messages import (
    AnalysisDraft,
    Claim,
    Verdict,
    VerifiedAnalysis,
)
from schemas.node import Node

logger = logging.getLogger(__name__)

LOW_FIDELITY_THRESHOLD = 2   # strip more than this → flag the whole analysis


def _valid_node_ids(nodes: list[Node]) -> set[str]:
    return {n.node_id for n in nodes}


def _filter_claims(claims: list[Claim], valid: set[str]) -> tuple[list[Claim], int]:
    """
    Return (kept, stripped_count).
    A claim is kept only if it has ≥1 node_id that exists in valid.
    Claims with empty node_ids list are always stripped.
    """
    kept: list[Claim] = []
    stripped = 0
    for claim in claims:
        good_ids = [nid for nid in claim.node_ids if nid in valid]
        if good_ids:
            kept.append(Claim(
                text=claim.text,
                node_ids=good_ids,
                is_positive=claim.is_positive,
            ))
        else:
            stripped += 1
            logger.warning(
                "agent_verifier: stripped claim — no valid node_ids found. "
                "text[:80]=%r  node_ids=%r",
                claim.text[:80],
                claim.node_ids,
            )
    return kept, stripped


def _filter_verdict(verdict: Verdict, valid: set[str]) -> Verdict:
    """Remove invalid node_ids from verdict's supporting_node_ids."""
    good_ids = [nid for nid in verdict.supporting_node_ids if nid in valid]
    return Verdict(
        category=verdict.category,
        direction=verdict.direction,
        summary=verdict.summary,
        supporting_node_ids=good_ids,
        confidence=verdict.confidence,
    )


def run(draft: AnalysisDraft, nodes: list[Node]) -> VerifiedAnalysis:
    """
    Verify AnalysisDraft against the supplied node set.
    Strips any claim whose node_ids don't exist in the supplied nodes.
    Returns VerifiedAnalysis with stripped_claims count and low_fidelity flag.

    This function is synchronous and CPU-only. Call it directly from the orchestrator.
    """
    valid = _valid_node_ids(nodes)
    total_stripped = 0

    # Verify and filter the three claim lists
    wds, n1  = _filter_claims(draft.what_data_suggests, valid)
    favor, n2 = _filter_claims(draft.signals_in_favor, valid)
    against, n3 = _filter_claims(draft.signals_against, valid)
    total_stripped = n1 + n2 + n3

    # Filter verdicts (keep structure, prune invalid node_ids only)
    clean_verdicts = {
        cat: _filter_verdict(v, valid)
        for cat, v in draft.verdicts.items()
    }

    # Filter agreement links — both node_ids must exist
    clean_agreements = [
        ag for ag in draft.agreements
        if ag.node_id_a in valid and ag.node_id_b in valid
    ]
    removed_ags = len(draft.agreements) - len(clean_agreements)

    # Filter contradiction links — both node_ids must exist
    clean_contradictions = [
        ct for ct in draft.contradictions
        if ct.node_id_positive in valid and ct.node_id_negative in valid
    ]
    removed_cts = len(draft.contradictions) - len(clean_contradictions)

    if removed_ags or removed_cts:
        logger.warning(
            "agent_verifier: removed %d agreement(s) and %d contradiction(s) with invalid node_ids",
            removed_ags, removed_cts,
        )

    # Build clean draft (same shape, updated claim lists + filtered verdicts)
    from schemas.messages import AnalysisDraft as AD
    clean_draft = AD(
        what_data_suggests=wds,
        signals_in_favor=favor,
        signals_against=against,
        verdicts=clean_verdicts,
        agreements=clean_agreements,
        contradictions=clean_contradictions,
        overall_signal=draft.overall_signal,
        raw_confidence=draft.raw_confidence,
        model_id=draft.model_id,
        prompt_version=draft.prompt_version,
        weight_version=draft.weight_version,
    )

    low_fidelity = total_stripped > LOW_FIDELITY_THRESHOLD

    logger.info(
        "agent_verifier: stripped=%d low_fidelity=%s overall=%s",
        total_stripped, low_fidelity, clean_draft.overall_signal,
    )

    return VerifiedAnalysis(
        draft=clean_draft,
        stripped_claims=total_stripped,
        low_fidelity=low_fidelity,
        verification_method="python",
    )
