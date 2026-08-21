import pytest

from harako_gpu.core.artifacts import BamState, DISCARD_GATES, transition_bam


def test_bam_discard_requires_every_validation_gate() -> None:
    gates = {gate: True for gate in DISCARD_GATES}
    assert transition_bam(BamState.VERIFIED, BamState.DISCARDED_AFTER_VALIDATION, gates) is BamState.DISCARDED_AFTER_VALIDATION
    gates["multiqc_success"] = False
    with pytest.raises(ValueError, match="multiqc_success"):
        transition_bam(BamState.VERIFIED, BamState.DISCARDED_AFTER_VALIDATION, gates)


def test_bam_cannot_skip_generated_and_verified_states() -> None:
    with pytest.raises(ValueError, match="Invalid BAM transition"):
        transition_bam(BamState.PLANNED, BamState.RETAINED)

