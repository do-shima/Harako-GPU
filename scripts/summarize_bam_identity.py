"""Create a scientific BAM identity from pre-extracted SAM text."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harako_gpu.services.salmon_reproducibility import (
    BamScientificIdentity,
    bam_scientific_checksum,
    header_normalized_sha256,
    inspect_sam_records,
    validate_bam_identity,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bam", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.records.open("r", encoding="utf-8") as records:
        inventory = inspect_sam_records(records)
    identity = BamScientificIdentity(
        byte_sha256=_sha256(args.bam),
        header_normalized_sha256=header_normalized_sha256(
            args.header.read_text(encoding="utf-8")
        ),
        record_multiset_sha256=inventory.record_multiset_sha256,
        record_order_sha256=inventory.record_order_sha256,
        record_count=inventory.record_count,
    )
    validate_bam_identity(identity)
    payload = {
        "schema_version": 1,
        "role": args.role,
        "identity": {
            "byte_sha256": identity.byte_sha256,
            "header_normalized_sha256": identity.header_normalized_sha256,
            "record_multiset_sha256": identity.record_multiset_sha256,
            "record_order_sha256": identity.record_order_sha256,
            "record_count": identity.record_count,
        },
        "salmon_input_scientific_checksum": bam_scientific_checksum(identity),
        "qname_groups_contiguous": inventory.qname_groups_contiguous,
        "unique_qname_count": inventory.unique_qname_count,
        "qname_group_count": inventory.qname_group_count,
        "split_qname_count": inventory.split_qname_count,
        "tag_counts": inventory.tag_counts,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
