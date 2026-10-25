import copy
from pathlib import Path

import pytest

from data_flow_diff.audit import read_json
from data_flow_diff.cli import main
from data_flow_diff.engine import Manifest, Policy, compare

SAMPLE = Path(__file__).parents[1] / "examples/support-platform"


def manifests():
    return [
        Manifest.model_validate(read_json(SAMPLE / name)) for name in ("before.json", "after.json")
    ]


def test_realistic_changes_and_policy_failures():
    before, after = manifests()
    rows = compare(before, after, Policy())["findings"]
    rules = {r["rule"] for r in rows}
    assert {
        "field-changed",
        "unapproved-country",
        "retention-limit",
        "encryption-required",
        "sensitive-data",
    } <= rules
    assert next(r for r in rows if r["rule"] == "retention-limit")["after"] == 730
    assert all(
        r["classification"] == "policy-assessment" for r in rows if r["rule"] != "field-changed"
    )


def test_set_reordering_is_not_a_change():
    before, _ = manifests()
    after = before.model_copy(deep=True)
    after.flows[0].data_categories.reverse()
    after.revision = "2"
    assert compare(before, after, Policy())["findings"] == []


def test_added_and_removed_flow():
    before, _ = manifests()
    after = before.model_copy(deep=True)
    after.flows[0].id = "new-flow"
    assert {r["rule"] for r in compare(before, after, Policy())["findings"]} == {
        "flow-added",
        "flow-removed",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("retention_days", -1),
        ("retention_days", True),
        ("encrypted_in_transit", "false"),
        ("countries", ["Singapore"]),
        ("countries", ["SG", "SG"]),
        ("data_categories", []),
        ("unexpected", "value"),
    ],
)
def test_invalid_input(field, value):
    raw = read_json(SAMPLE / "before.json")
    raw["flows"][0][field] = value
    with pytest.raises(ValueError):
        Manifest.model_validate(raw)


def test_duplicate_identity_refused():
    raw = read_json(SAMPLE / "before.json")
    raw["flows"].append(copy.deepcopy(raw["flows"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        Manifest.model_validate(raw)


def test_different_system_refused():
    before, after = manifests()
    after.system = "other"
    with pytest.raises(ValueError, match="identities"):
        compare(before, after, Policy())


def test_unknown_values_are_not_safe_defaults():
    before, _ = manifests()
    after = before.model_copy(deep=True)
    after.flows[0].retention_days = None
    after.flows[0].lawful_basis = None
    assert {r["rule"] for r in compare(before, after, Policy())["findings"]} >= {
        "unknown-retention",
        "basis-required",
    }


def test_ci_exit_code_and_report(tmp_path):
    args = [
        "compare",
        str(SAMPLE / "before.json"),
        str(SAMPLE / "after.json"),
        "--policy",
        str(SAMPLE / "policy.json"),
        "--out",
        str(tmp_path / "out"),
        "--fail-on",
        "error",
    ]
    assert main(args) == 1
    assert (tmp_path / "out/findings.sarif").exists()


def test_invalid_input_has_exit_two_and_no_output(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{}")
    assert (
        main(
            [
                "compare",
                str(path),
                str(SAMPLE / "after.json"),
                "--policy",
                str(SAMPLE / "policy.json"),
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("allowed_countries", ["Singapore"]),
        ("allowed_countries", ["SG", "SG"]),
        ("sensitive_categories", [" "]),
    ],
)
def test_invalid_policy_values_fail(field, value):
    with pytest.raises(ValueError):
        Policy.model_validate({field: value})
