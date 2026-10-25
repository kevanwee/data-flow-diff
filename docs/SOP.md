# Standard operating procedure

1. Confirm scope: detect privacy-relevant changes between processing manifests. Read the README's limitations first.
2. Run the documented sample command. The sample is synthetic and licensed for reuse.
3. Open the review HTML. Inspect classification, evidence and configuration before
   accepting any finding. An observed/calculated value is conditional on supplied inputs.
4. Correct a flow or policy in the source JSON and rerun compare into a new directory. Policy exceptions belong in a reasoned review assessment; they do not silently rewrite the policy.
5. Assess every finding. Dismiss false positives with reasons; use correction overlays
   for your replacement assessment; use needs-information for unresolved evidence.
6. Identify the responsible reviewer and review basis. Download decisions. Real matters
   require the actual responsible person's decision; test sign-offs are synthetic only.
7. Finalize into a new directory. The CLI verifies the exact package and complete decision
   set. A mismatched fingerprint, changed source or missing decision is refused.
8. Verify the reviewed export. Retain the original analysis and decision history.
9. Hand off the usable output: `report.json`, `report.md`, `findings.sarif` and `review.html`, with frozen before/after manifests and policy.
10. Confirm any external business outcome separately. Exporting a report makes no
    external change and grants no rights, compliance certification or survey authority.
