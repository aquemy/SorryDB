"""Kernel-grounded contamination analysis: declarations that compile cleanly yet depend on sorryAx.

SorryDB indexes literal ``sorry`` obligations. It never runs ``#print axioms``, so it cannot see
*silent* contamination: a declaration the kernel reports as ``sorryAx`` while carrying no literal
``sorry`` in the source. That is exactly what a text search, a green build, and SorryDB's index all
miss -- the Polynomial Freiman-Ruzsa pattern, where seven ``WeakPFR`` declarations compile cleanly,
contain no ``sorry``, yet depend on ``sorryAx``.

This module adds the missing ``#print axioms`` layer by shelling out to the ``claimgraph lean-graph``
tool on a *built* repository: it grounds every declaration against the kernel, then classifies the
``sorryAx``-contaminated ones. Validated on built PFR (the 7 silent ``WeakPFR`` declarations).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

OPEN = "math.open"  # the kernel reading for a declaration that depends on sorryAx
DEP_RELATIONS = {"Depends-On", "Assumes"}
_LITERAL_SORRY = re.compile(r"\bsorry\b|\badmit\b")


def repo_has_literal_sorry(repo_path: Path) -> bool:
    """True if any non-``.lake`` Lean source file contains a literal ``sorry`` / ``admit``."""
    for f in repo_path.rglob("*.lean"):
        if ".lake" in f.parts:
            continue
        try:
            if _LITERAL_SORRY.search(f.read_text(encoding="utf-8", errors="ignore")):
                return True
        except OSError:
            continue
    return False


def _forward_closure(adj: dict[str, set[str]], start: str) -> set[str]:
    """All nodes reachable from ``start`` over the adjacency map (the things ``start`` rests on)."""
    seen: set[str] = set()
    stack = list(adj.get(start, ()))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(x for x in adj.get(cur, ()) if x not in seen)
    return seen


def run_lean_graph(
    repo_path: str | Path,
    namespace: str | None = None,
    claimgraph_bin: str = "claimgraph",
    axiom_report: str | None = None,
) -> dict | None:
    """Shell out to ``claimgraph lean-graph`` on a BUILT repo; return the graph JSON, or ``None``."""
    cmd = [claimgraph_bin, "lean-graph", str(repo_path)]
    if namespace:
        cmd += ["--namespace", namespace]
    if axiom_report:
        cmd += ["--axiom-report", axiom_report]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError) as exc:
        logger.warning("claimgraph not available (%s); skipping contamination analysis", exc)
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        logger.warning("lean-graph failed (rc=%s): %s", proc.returncode, proc.stderr[-500:])
        return None
    return json.loads(proc.stdout)


def analyze_contamination(
    repo_path: str | Path,
    graph: dict | None = None,
    **lean_graph_kwargs,
) -> dict | None:
    """Classify a built repo's ``sorryAx`` contamination from its kernel-grounded ClaimGraph.

    Returns a record with the open (``sorryAx``) declarations and the headline
    ``silent_contamination``: the ones grep / a green build / SorryDB's literal-``sorry`` index do not
    see. A declaration is downstream-contaminated when it rests (transitively) on another open
    declaration (the sorry is upstream of it); a *source* open declaration is silent iff the
    repository carries no literal ``sorry`` at all (then every ``sorryAx`` is elaboration-introduced,
    as in PFR). ``graph`` may be passed in to analyze an already-built graph (for tests).
    """
    repo_path = Path(repo_path)
    if graph is None:
        graph = run_lean_graph(repo_path, **lean_graph_kwargs)
        if graph is None:
            return None
    nodes = graph.get("nodes", [])
    open_ids = {n["id"] for n in nodes if n.get("kernel") == OPEN}
    adj: dict[str, set[str]] = {}
    for e in graph.get("edges", []):
        if e.get("relation") in DEP_RELATIONS:
            adj.setdefault(e["source"], set()).add(e["target"])
    downstream = {x for x in open_ids if _forward_closure(adj, x) & open_ids}
    source = open_ids - downstream
    has_literal = repo_has_literal_sorry(repo_path)
    silent = set(downstream) | (source if not has_literal else set())
    return {
        "n_declarations": len(nodes),
        "n_open": len(open_ids),
        "open": sorted(open_ids),
        "source_open": sorted(source),
        "downstream_open": sorted(downstream),
        "repo_has_literal_sorry": has_literal,
        "silent_contamination": sorted(silent),
    }
