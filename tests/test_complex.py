from pathlib import Path

import pytest

from data_flow_diff.audit import read_json
from data_flow_diff.engine import Manifest, Policy, compare

CASE = Path(__file__).parents[1] / "examples/clinical-platform"


def result():
    return compare(
        Manifest.model_validate(read_json(CASE / "before.json")),
        Manifest.model_validate(read_json(CASE / "after.json")),
        Policy.model_validate(read_json(CASE / "policy.json")),
    )


def test_complex_network_matches_independent_ledger():
    report = result()
    expected = read_json(CASE / "expected.json")
    rows = report["findings"]
    assert report["coverage"]["before_flows"] == expected["before_flows"]
    assert report["coverage"]["after_flows"] == expected["after_flows"]
    for rule, key in [
        ("flow-added", "added"),
        ("flow-removed", "removed"),
        ("field-changed", "changed"),
    ]:
        assert {r["entity"] for r in rows if r["rule"] == rule} == set(expected[key])
    for severity, key in [("error", "policy_errors"), ("warning", "policy_warnings")]:
        assert {
            (r["rule"], r["entity"])
            for r in rows
            if r["classification"] == "policy-assessment" and r["severity"] == severity
        } == {tuple(row) for row in expected[key]}
    assert len(rows) == expected["expected_total_findings"]
    assert not any(r["entity"].split(".")[0] in expected["unchanged"] for r in rows)


def test_persistent_legacy_failures_remain_visible():
    legacy = [r for r in result()["findings"] if r["entity"] == "legacy-metrics"]
    assert len(legacy) == 3
    assert all("persists" in r["explanation"] for r in legacy)


def test_sensitive_label_ambiguity_is_not_silently_normalised():
    row = next(r for r in result()["findings"] if r["rule"] == "ambiguous-category")
    assert row["after"] == ["Health "]
    assert row["entity"] == "fraud-model"


@pytest.mark.parametrize("label", ["S1", "1S", "ÜS", "sg", "SG "])
def test_country_syntax_is_letters_only(label):
    raw = read_json(CASE / "before.json")
    raw["flows"][0]["countries"] = [label]
    with pytest.raises(ValueError):
        Manifest.model_validate(raw)
    with pytest.raises(ValueError):
        Policy.model_validate({"allowed_countries": [label]})


@pytest.mark.parametrize("field", ["source", "destination", "recipient", "owner"])
def test_blank_flow_identity_fields_are_refused(field):
    raw = read_json(CASE / "before.json")
    raw["flows"][0][field] = "   "
    with pytest.raises(ValueError):
        Manifest.model_validate(raw)


def test_complex_rehearsal_keeps_unresolved_questions_pending(tmp_path):
    import importlib.util

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("rehearsal", root / "scripts/rehearse_complex.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run("scripts/complex-scenario.json", tmp_path / "rehearsal")
    assert result["review_status"] == "needs-information"
    assert result["pending"] > 0
    assert result["external_actions"] == "none"
