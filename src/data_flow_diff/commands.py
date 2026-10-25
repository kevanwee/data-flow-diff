from pathlib import Path

from .audit import Decisions, read_json
from .cli import analysis_args
from .engine import Manifest, Policy, compare


def arguments(sub):
    p = sub.add_parser("compare", help="compare processing manifests under a supplied policy")
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--policy", type=Path, required=True)
    analysis_args(p)


def schemas():
    return {"manifest": Manifest, "policy": Policy, "decisions": Decisions}


def execute(args):
    report = compare(
        Manifest.model_validate(read_json(args.before)),
        Manifest.model_validate(read_json(args.after)),
        Policy.model_validate(read_json(args.policy)),
    )
    snapshots = {
        name: path.read_bytes()
        for name, path in [
            ("before.json", args.before),
            ("after.json", args.after),
            ("policy.json", args.policy),
        ]
    }
    return report, snapshots, {}
