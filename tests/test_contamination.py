"""Unit tests for kernel-grounded contamination classification (no Lean build needed)."""

from sorrydb.database.contamination import analyze_contamination


def _graph(open_ids, edges):
    nodes = [{"id": "clean1", "kernel": "math.machine-checked"}]
    nodes += [{"id": i, "kernel": "math.open"} for i in open_ids]
    return {
        "nodes": nodes,
        "edges": [{"source": s, "target": t, "relation": "Depends-On"} for s, t in edges],
    }


def test_all_open_silent_when_repo_has_no_literal_sorry(tmp_path):
    # b depends on a; both open; the repo has no .lean source carrying a literal sorry.
    rec = analyze_contamination(tmp_path, graph=_graph(["a", "b"], [("b", "a")]))
    assert rec["n_open"] == 2
    assert rec["repo_has_literal_sorry"] is False
    assert set(rec["source_open"]) == {"a"}
    assert set(rec["downstream_open"]) == {"b"}
    assert set(rec["silent_contamination"]) == {"a", "b"}


def test_only_downstream_silent_when_a_literal_sorry_exists(tmp_path):
    (tmp_path / "X.lean").write_text("theorem a : True := by sorry\n")
    rec = analyze_contamination(tmp_path, graph=_graph(["a", "b"], [("b", "a")]))
    assert rec["repo_has_literal_sorry"] is True
    assert set(rec["downstream_open"]) == {"b"}
    # b is grep-invisible (the sorry is upstream); a carries the literal sorry, so not auto-silent.
    assert set(rec["silent_contamination"]) == {"b"}


def test_lake_dir_is_ignored(tmp_path):
    lake = tmp_path / ".lake" / "x.lean"
    lake.parent.mkdir(parents=True)
    lake.write_text("by sorry")
    rec = analyze_contamination(tmp_path, graph=_graph(["a"], []))
    assert rec["repo_has_literal_sorry"] is False  # .lake is excluded
    assert set(rec["silent_contamination"]) == {"a"}
