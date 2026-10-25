"""Compare declared processing flows. No network inspection or legal conclusions."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from .audit import Strict, finding


class Flow(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    data_categories: list[str] = Field(min_length=1)
    purposes: list[str] = Field(min_length=1)
    recipient: str = Field(min_length=1)
    countries: list[str] = Field(min_length=1)
    retention_days: StrictInt | None = Field(ge=0)
    encrypted_in_transit: StrictBool | None
    lawful_basis: str | None
    owner: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sets(self):
        for key in ("data_categories", "purposes", "countries"):
            values = getattr(self, key)
            if len(set(values)) != len(values) or any(not v.strip() for v in values):
                raise ValueError(f"{key} must contain distinct nonblank values")
        if any(
            len(country) != 2 or not country.isascii() or not country.isupper()
            for country in self.countries
        ):
            raise ValueError("countries must use uppercase two-letter codes")
        return self


class Manifest(Strict):
    schema_version: Literal["1"] = "1"
    system: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    synthetic: StrictBool = False
    flows: list[Flow]

    @model_validator(mode="after")
    def identities(self):
        ids = [f.id for f in self.flows]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate flow IDs; identity must be stable across revisions")
        return self


class Policy(Strict):
    schema_version: Literal["1"] = "1"
    allowed_countries: list[str] = Field(default_factory=lambda: ["SG"])
    max_retention_days: StrictInt = Field(default=365, ge=0)
    require_encryption: StrictBool = True
    require_lawful_basis: StrictBool = True
    sensitive_categories: list[str] = Field(default_factory=lambda: ["health", "biometric"])

    @model_validator(mode="after")
    def policy_values(self):
        if len(set(self.allowed_countries)) != len(self.allowed_countries) or any(
            len(c) != 2 or not c.isascii() or not c.isupper() for c in self.allowed_countries
        ):
            raise ValueError("Policy countries must be distinct uppercase two-letter codes")
        if len(set(self.sensitive_categories)) != len(self.sensitive_categories) or any(
            not value.strip() for value in self.sensitive_categories
        ):
            raise ValueError("Sensitive categories must be distinct and nonblank")
        return self


SETS = {"data_categories", "purposes", "countries"}


def normalized(flow):
    row = flow.model_dump(mode="json")
    for key in SETS:
        row[key] = sorted(row[key])
    return row


def pointer(source, fid, field=""):
    # Stable semantic selector; no claim that this is an RFC 6901 array index.
    return {"source": source, "locator": f"flow[id={fid}]" + (f".{field}" if field else "")}


def compare(before: Manifest, after: Manifest, policy: Policy):
    if before.system != after.system:
        raise ValueError("System identities differ; compare revisions of the same system")
    if before.synthetic != after.synthetic:
        raise ValueError("Both manifests must agree on synthetic status")
    old, new = ({f.id: normalized(f) for f in m.flows} for m in (before, after))
    rows = []
    for fid in sorted(old.keys() | new.keys()):
        a, b = old.get(fid), new.get(fid)
        if a is None or b is None:
            rows.append(
                finding(
                    "flow-added" if a is None else "flow-removed",
                    fid,
                    f"{'Added' if a is None else 'Removed'} processing flow: {fid}",
                    before=a,
                    after=b,
                    evidence=[pointer("after.json" if a is None else "before.json", fid)],
                    explanation="Observed difference in supplied declarations; actual processing is not inspected.",
                )
            )
        else:
            for field in sorted(a.keys() - {"id"}):
                if a[field] != b[field]:
                    rows.append(
                        finding(
                            "field-changed",
                            f"{fid}.{field}",
                            f"{fid}: {field.replace('_', ' ')} changed",
                            before=a[field],
                            after=b[field],
                            evidence=[
                                pointer("before.json", fid, field),
                                pointer("after.json", fid, field),
                            ],
                            explanation="Set order is ignored; stable IDs preserve flow identity.",
                        )
                    )
        if b is None:
            continue
        checks = [
            (
                "unapproved-country",
                "countries",
                bool(set(b["countries"]) - set(policy.allowed_countries)),
                "Destination includes a country outside the supplied policy",
                "error",
            ),
            (
                "retention-limit",
                "retention_days",
                b["retention_days"] is not None and b["retention_days"] > policy.max_retention_days,
                "Declared retention exceeds the configured limit",
                "error",
            ),
            (
                "unknown-retention",
                "retention_days",
                b["retention_days"] is None,
                "Retention period is unknown",
                "warning",
            ),
            (
                "encryption-required",
                "encrypted_in_transit",
                policy.require_encryption and b["encrypted_in_transit"] is not True,
                "Required transport encryption is not established",
                "error",
            ),
            (
                "basis-required",
                "lawful_basis",
                policy.require_lawful_basis and not (b["lawful_basis"] or "").strip(),
                "No processing basis is recorded",
                "error",
            ),
            (
                "sensitive-data",
                "data_categories",
                bool(set(b["data_categories"]) & set(policy.sensitive_categories)),
                "Sensitive-category processing needs review under the configured policy",
                "warning",
            ),
        ]
        for rule, field, triggered, title, severity in checks:
            if triggered:
                rows.append(
                    finding(
                        rule,
                        fid,
                        f"{fid}: {title}",
                        before=a.get(field) if a else None,
                        after=b[field],
                        severity=severity,
                        classification="policy-assessment",
                        evidence=[
                            pointer("after.json", fid, field),
                            {"source": "policy.json", "locator": rule},
                        ],
                        explanation="This evaluates the supplied organisational policy, not statutory compliance. "
                        + (
                            "The issue is new or changed."
                            if a is None or a.get(field) != b[field]
                            else "The issue persists from the earlier declaration."
                        ),
                    )
                )
    return {
        "tool": "data-flow-diff",
        "title": f"Privacy change review — {after.system}",
        "summary": f"Processing manifest {before.revision} → {after.revision}",
        "review_status": "unreviewed",
        "synthetic": after.synthetic,
        "configuration": policy.model_dump(mode="json"),
        "findings": rows,
        "coverage": {
            "before_flows": len(old),
            "after_flows": len(new),
            "compared_fields": sorted(Flow.model_fields),
        },
        "assumptions": [
            "Stable IDs refer to the same processing flow across revisions.",
            "Manifest declarations have not been verified against live systems.",
        ],
        "boundary": "Verified comparisons concern supplied declarations. Policy findings require "
        "review and are not findings of PDPA compliance or breach.",
    }
