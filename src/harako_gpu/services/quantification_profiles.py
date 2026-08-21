"""Fixed versioned Salmon profiles and immutable analysis-series contracts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

from harako_gpu.core.canonical import sha256_payload
from harako_gpu.services.alignment_profiles import TWO_PASS_PROFILE_ID, get_alignment_profile


PROFILE_CATALOG_VERSION = "harako-quantification-profiles-v1"
VERSIONED_QUANTIFICATION_SCHEMA_VERSION = 2
SALMON_1103_ID = "salmon_1_10_3_compatibility"
SALMON_251_ID = "salmon_2_5_1_deterministic"
SALMON_1121_ID = "salmon_1_12_1_rejected_hidden"
VISIBLE_PROFILE_IDS = (SALMON_251_ID, SALMON_1103_ID)
_HEX = re.compile(r"^[0-9a-f]{64}$")


class AnalysisMode(StrEnum):
    RECOMMENDED_ONLY = "recommended_only"
    COMPATIBILITY_ONLY = "compatibility_only"
    COMPARE_BOTH = "compare_both"


@dataclass(frozen=True)
class QuantificationProfile:
    profile_id: str
    display_name_ja: str
    display_name_en: str
    version: str
    implementation: str
    image_reference: str
    image_identity: str
    deterministic: bool
    decoder: str | None
    threads: int
    reproducibility_class: str
    product_status: str
    visible: bool
    command_profile_id: str
    qualification_report_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def validate(self) -> None:
        if self.threads != 6 or not self.image_reference or not _HEX.fullmatch(self.image_identity.removeprefix("sha256:")):
            raise ValueError("Profile image identity and six-thread policy must be pinned")
        if self.profile_id == SALMON_251_ID:
            if (self.version, self.implementation, self.deterministic, self.decoder) != ("2.5.1", "rust", True, "serial"):
                raise ValueError("Salmon 2.5.1 deterministic profile identity mismatch")
        elif self.profile_id == SALMON_1103_ID:
            if (self.version, self.implementation, self.deterministic, self.decoder) != ("1.10.3", "cpp_legacy", False, None):
                raise ValueError("Salmon 1.10.3 compatibility profile identity mismatch")
        elif self.profile_id == SALMON_1121_ID:
            if self.visible or self.product_status != "rejected_candidate_hidden":
                raise ValueError("Salmon 1.12.1 must remain hidden and rejected")
        else:
            raise ValueError("Unknown quantification profile")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


_PROFILES = {
    SALMON_251_ID: QuantificationProfile(
        SALMON_251_ID, "再現性優先・推奨", "Reproducibility-first — recommended",
        "2.5.1", "rust", "harako-gpu/salmon:2.5.1-qualification",
        "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f",
        True, "serial", 6, "exact_deterministic", "recommended_internal_research_profile", True,
        "salmon-2.5.1-deterministic-serial-isr-v1",
        ("salmon-2.5.1-deterministic-qualification", "expression-truth-decoy-accounting-remediation", "external-truth-failure-cause-isolation"),
        ("internal research use only", "non-diagnostic", "non-clinical", "full-size human qualification incomplete"),
    ),
    SALMON_1103_ID: QuantificationProfile(
        SALMON_1103_ID, "互換性優先", "Compatibility-first", "1.10.3", "cpp_legacy",
        "quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2",
        "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e",
        False, None, 6, "bounded_numerical", "available_compatibility_profile", True,
        "salmon-1.10.3-isr-compatibility-v1", ("independent-fastq-salmon-quantification",),
        ("bounded numerical variability", "not byte-exact", "not identical to Harako-RNAseq Salmon 1.10.0", "not first recommendation for new projects"),
    ),
    SALMON_1121_ID: QuantificationProfile(
        SALMON_1121_ID, "非表示", "Hidden rejected candidate", "1.12.1", "cpp_legacy",
        "harako-gpu/salmon:1.12.1-qualification",
        "sha256:88b88863b8830ca6eb6747c305522c220bf660caa16eb82400240ba7637d81dd",
        False, None, 6, "rejected", "rejected_candidate_hidden", False,
        "rejected-no-command", ("salmon-1.12.1-upgrade-qualification",), ("new runs forbidden",),
    ),
}


def visible_profiles() -> tuple[QuantificationProfile, ...]:
    return tuple(_PROFILES[item] for item in VISIBLE_PROFILE_IDS)


def get_profile(profile_id: str, *, allow_hidden: bool = False) -> QuantificationProfile:
    try:
        profile = _PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown quantification profile: {profile_id}") from exc
    profile.validate()
    if not profile.visible and not allow_hidden:
        raise ValueError("Hidden/rejected quantification profile cannot be selected")
    return profile


@dataclass(frozen=True)
class ModeSelection:
    mode: AnalysisMode
    primary_profile_id: str
    secondary_profile_id: str | None
    downstream_primary_profile_id: str

    @classmethod
    def create(cls, mode: AnalysisMode, primary: str | None = None) -> "ModeSelection":
        if mode is AnalysisMode.RECOMMENDED_ONLY:
            selected = primary or SALMON_251_ID
            if selected != SALMON_251_ID:
                raise ValueError("recommended_only requires the recommended profile")
            return cls(mode, selected, None, selected)
        if mode is AnalysisMode.COMPATIBILITY_ONLY:
            selected = primary or SALMON_1103_ID
            if selected != SALMON_1103_ID:
                raise ValueError("compatibility_only requires the compatibility profile")
            return cls(mode, selected, None, selected)
        if primary is None:
            raise ValueError("compare_both requires an explicit primary profile")
        get_profile(primary)
        secondary = SALMON_1103_ID if primary == SALMON_251_ID else SALMON_251_ID
        return cls(mode, primary, secondary, primary)


@dataclass(frozen=True)
class ProcessedFastqPair:
    sample_id: str
    r1_path: str
    r2_path: str
    r1_sha256: str
    r2_sha256: str
    paired_fragments: int
    preprocessing_contract_id: str
    fastp_version: str
    fastp_argv: tuple[str, ...]
    library_type: str

    def validate(self) -> None:
        if not self.sample_id or not self.r1_path or not self.r2_path or self.r1_path == self.r2_path:
            raise ValueError("Processed paired FASTQ roles must be explicit and distinct")
        if not _HEX.fullmatch(self.r1_sha256) or not _HEX.fullmatch(self.r2_sha256) or self.paired_fragments < 1:
            raise ValueError("Processed FASTQ identity and fragment count are required")
        if self.library_type not in {"ISR", "ISF", "U"} or not self.fastp_argv or self.fastp_argv[0] != "fastp":
            raise ValueError("Explicit library type and structured fastp provenance are required")


@dataclass(frozen=True)
class ProfileIndex:
    profile_id: str
    index_id: str
    path: str
    builder_version: str
    image_identity: str
    transcript_source_sha256: str
    genome_source_sha256: str
    gtf_sha256: str
    tx2gene_sha256: str
    manifest_sha256: str

    def validate(self) -> None:
        profile = get_profile(self.profile_id)
        if self.builder_version != profile.version or self.image_identity != profile.image_identity:
            raise ValueError("Salmon profile/version/index/image mismatch")
        if not self.index_id or not self.path or any(not _HEX.fullmatch(value) for value in (
            self.transcript_source_sha256, self.genome_source_sha256, self.gtf_sha256,
            self.tx2gene_sha256, self.manifest_sha256,
        )):
            raise ValueError("Complete version-specific index identity is required")


def validate_comparable_indices(indices: Sequence[ProfileIndex]) -> None:
    if {item.profile_id for item in indices} != set(VISIBLE_PROFILE_IDS):
        raise ValueError("Comparison requires exactly the two visible profile indices")
    for item in indices:
        item.validate()
    sources = {(item.transcript_source_sha256, item.genome_source_sha256, item.gtf_sha256, item.tx2gene_sha256) for item in indices}
    if len(sources) != 1:
        raise ValueError("Profile indices must share the same biological reference source")


def versioned_quantification_contract(
    selection: ModeSelection,
    *,
    explicit_library_type: str,
    indices: Mapping[str, ProfileIndex],
) -> dict[str, Any]:
    """Build the neutral new-plan FASTQ Salmon contract.

    Historical schema-v1 Salmon contracts remain owned by the compatibility
    reader in ``independent_fastq_salmon``.  New plans freeze only the profiles
    selected by ``ModeSelection``.
    """
    if explicit_library_type not in {"U", "ISF", "ISR"}:
        raise ValueError("Versioned quantification requires an explicit library type")
    selected = tuple(
        item for item in (selection.primary_profile_id, selection.secondary_profile_id)
        if item is not None
    )
    if set(indices) != set(selected):
        raise ValueError("Execution indices must exactly match the selected profiles")
    for profile_id in selected:
        index = indices[profile_id]
        index.validate()
        if index.profile_id != profile_id:
            raise ValueError("Execution index profile identity mismatch")
    if selection.mode is AnalysisMode.COMPARE_BOTH:
        validate_comparable_indices(tuple(indices[item] for item in selected))
    payload = {
        "schema_version": VERSIONED_QUANTIFICATION_SCHEMA_VERSION,
        "backend": "fastq_salmon",
        "input_kind": "processed_fastq",
        "explicit_library_type": explicit_library_type,
        "threads": 6,
        "mode": selection.mode.value,
        "primary_profile_id": selection.primary_profile_id,
        "secondary_profile_id": selection.secondary_profile_id,
        "downstream_primary_profile_id": selection.downstream_primary_profile_id,
        "profiles": {
            profile_id: {**get_profile(profile_id).as_dict(), "index": asdict(indices[profile_id])}
            for profile_id in selected
        },
        "execution_indices_ready": True,
    }
    validate_versioned_quantification_contract(payload)
    return payload


def validate_versioned_quantification_contract(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != VERSIONED_QUANTIFICATION_SCHEMA_VERSION:
        raise ValueError("Versioned quantification schema_version must be 2")
    if (data.get("backend"), data.get("input_kind"), data.get("threads")) != (
        "fastq_salmon", "processed_fastq", 6,
    ):
        raise ValueError("Versioned quantification backend/input/thread contract mismatch")
    library_type = str(data.get("explicit_library_type") or "")
    if library_type not in {"U", "ISF", "ISR"}:
        raise ValueError("Versioned quantification library type is invalid")
    try:
        selection = ModeSelection.create(
            AnalysisMode(str(data["mode"])), str(data["primary_profile_id"]),
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid versioned profile selection: {exc}") from exc
    if data.get("secondary_profile_id") != selection.secondary_profile_id:
        raise ValueError("Stored secondary profile does not match the fixed mode")
    if data.get("downstream_primary_profile_id") != selection.downstream_primary_profile_id:
        raise ValueError("Missing or mismatched downstream primary profile")
    if data.get("execution_indices_ready") is not True:
        raise ValueError("Selected execution indices are not ready")
    profiles = dict(data.get("profiles") or {})
    selected = {
        value for value in (selection.primary_profile_id, selection.secondary_profile_id)
        if value is not None
    }
    if set(profiles) != selected:
        raise ValueError("Frozen profile set must exactly match mode selection")
    indices: list[ProfileIndex] = []
    for profile_id in sorted(selected):
        try:
            profile_data = dict(profiles[profile_id])
            index = ProfileIndex(**dict(profile_data["index"]))
        except (KeyError, TypeError) as exc:
            raise ValueError("Missing fixed execution index contract") from exc
        expected = get_profile(profile_id)
        for key in ("profile_id", "version", "image_identity", "threads"):
            if profile_data.get(key) != getattr(expected, key):
                raise ValueError("Frozen quantification profile identity mismatch")
        index.validate()
        indices.append(index)
    if selection.mode is AnalysisMode.COMPARE_BOTH:
        validate_comparable_indices(indices)


@dataclass(frozen=True)
class AnalysisSeries:
    project_id: str
    selection: ModeSelection
    reference_pack_id: str
    fasta_sha256: str
    gtf_sha256: str
    tx2gene_sha256: str
    library_type: str
    preprocessing_contract_id: str
    samples: tuple[ProcessedFastqPair, ...]
    indices: tuple[ProfileIndex, ...]
    commands: Mapping[str, tuple[str, ...]]
    star_comparator_status: str
    created_at: str
    parent_series_id: str | None = None
    series_status: str = "immutable"
    alignment_profile_id: str = TWO_PASS_PROFILE_ID

    def canonical_payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "project_id": self.project_id, "selection": asdict(self.selection),
            "reference_pack_id": self.reference_pack_id, "fasta_sha256": self.fasta_sha256,
            "gtf_sha256": self.gtf_sha256, "tx2gene_sha256": self.tx2gene_sha256,
            "library_type": self.library_type, "preprocessing_contract_id": self.preprocessing_contract_id,
            "samples": [asdict(item) for item in self.samples], "indices": [asdict(item) for item in self.indices],
            "commands": {key: list(value) for key, value in sorted(self.commands.items())},
            "star_comparator_status": self.star_comparator_status, "created_at": self.created_at,
            "parent_series_id": self.parent_series_id, "series_status": self.series_status,
            "alignment_profile_id": self.alignment_profile_id,
        }

    @property
    def analysis_series_id(self) -> str:
        return sha256_payload({"kind": "harako-analysis-series-v1", "payload": self.canonical_payload()})

    def validate(self) -> None:
        if not self.project_id or self.series_status != "immutable" or self.library_type not in {"ISR", "ISF", "U"}:
            raise ValueError("Immutable analysis-series identity is required")
        get_alignment_profile(self.alignment_profile_id)
        if not self.samples or len({item.sample_id for item in self.samples}) != len(self.samples):
            raise ValueError("Analysis series requires unique samples")
        for sample in self.samples:
            sample.validate()
            if sample.library_type != self.library_type or sample.preprocessing_contract_id != self.preprocessing_contract_id:
                raise ValueError("Mixed library/preprocessing contracts are forbidden")
        required = {self.selection.primary_profile_id} | ({self.selection.secondary_profile_id} if self.selection.secondary_profile_id else set())
        if {item.profile_id for item in self.indices} != required or set(self.commands) != required:
            raise ValueError("Profile indices/commands must exactly match series selection")


def salmon_argv(profile_id: str, *, index: str, gene_map: str, r1: str, r2: str, output: str, library_type: str) -> tuple[str, ...]:
    profile = get_profile(profile_id)
    if library_type not in {"ISR", "ISF", "U"} or any(not value or "\x00" in value for value in (index, gene_map, r1, r2, output)):
        raise ValueError("Pinned paths and explicit library type are required")
    argv = ["salmon", "quant"]
    if profile.deterministic:
        argv += ["--deterministic", "--decoder", "serial"]
    salmon_library_type = salmon_library_type_for_product(library_type)
    argv += ["--geneMap", gene_map, "--threads", "6", "--libType", salmon_library_type,
             "--index", index, "-1", r1, "-2", r2, "-o", output]
    return tuple(argv)


def salmon_library_type_for_product(library_type: str) -> str:
    if library_type not in {"U", "ISF", "ISR"}:
        raise ValueError("Library type must be explicit U, ISF, or ISR")
    return "IU" if library_type == "U" else library_type


def artifact_names(profile_id: str) -> dict[str, str]:
    get_profile(profile_id)
    prefix = profile_id
    return {
        "quant_dir": f"quantification/{prefix}/<sample>",
        "transcript_counts": f"matrices/{prefix}.transcript_counts.tsv",
        "transcript_tpm": f"matrices/{prefix}.transcript_tpm.tsv",
        "transcript_effective_length": f"matrices/{prefix}.transcript_effective_length.tsv",
        "gene_counts": f"matrices/{prefix}.gene_counts.tsv",
        "gene_tpm": f"matrices/{prefix}.gene_tpm.tsv",
        "gene_effective_length": f"matrices/{prefix}.gene_effective_length.tsv",
    }
