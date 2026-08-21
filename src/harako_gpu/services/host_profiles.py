"""Fixed host qualifications and offline runtime closures.

These are product contracts, not hardware scheduling rules.  A detected host is
only a candidate until its installed receipts validate against this catalog.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping

from harako_gpu.adapters.docker import DockerImageContract, canonical_image_identity
from harako_gpu.adapters.filesystem import sha256_path
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.services.alignment_profiles import ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID


WINDOWS_HOST_PROFILE_ID = "windows_wsl2_rtx3090_ram64_v1"
UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID = "ubuntu_native_rtx3090_ram128_v1"
FULL_HUMAN_REFERENCE_PACK_ID = "human_grch38p14_gencode49_harako_gpu_v1"
STAR_INDEX_ID = "star-2.7.2a-c15a9d6fe6df9716"
SALMON_251_INDEX_ID = "salmon-2.5.1-1c037278d376f40f"
PIPELINE_COMMIT = "e7ca46272c8f9d5ceee3f71759f4ba551d3217a4"
QUALIFICATION_REPOSITORY_COMMIT = "27706b9fb65b3c3ccf965e39a582e7947be9482b"
QUALIFICATION_REPOSITORY_TREE = "e2efd73c0ed85b5d8f3e4b5f9190167de10c16f2"
PLUGIN_CLOSURE_ID = "nf-schema-2.5.1-offline-v1"
TASK_IMAGE_CLOSURE_ID = "nfcore-rnaseq-3.26.0-full-human-images-v1"
TASK_IMAGE_CLOSURE_EVIDENCE_SHA256 = "4fc56c8eb1a0a7c7eea75f8dfbffbc459a9d0698e20313e094105e714a3c31bb"
UBUNTU_SAMTOOLS_REFERENCE = (
    "community.wave.seqera.io/library/htslib_samtools:1.23.1--5b6bb4ede7e612e5"
)
UBUNTU_SAMTOOLS_IMAGE_ID = (
    "sha256:b762af53a769d82aa0111bfbc4574c8bb8c07f9257a8e09c8403c4f540a10a07"
)
ONE_PASS_REPORT_ID = "native-high-memory-full-human-one-pass"
TWO_PASS_REPORT_ID = "native-high-memory-full-human-two-pass"
ONE_PASS_REPORT_SHA256 = "4c8017e5f37fe9b530c41ca18e56ac7bc5890ff53534910dd252d720508cca68"
TWO_PASS_REPORT_SHA256 = "6f1511fe70997337971f2849d9b7ee0793d9b57692510788173d69419baed1db"
ARCHIVE_RECEIPT_SHA256 = frozenset({
    "91c2afbbefbd0968f60d59df3ac57966d17c335fd2438edcd3f10ec5d000b68e",
    "71d5a3fa60c569d3ddf84c6696acf0d338379e012205a6c845ac69df5a5ad711",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class HostProfile:
    host_profile_id: str
    execution_context: str
    operating_system_family: str
    minimum_physical_ram_bytes: int
    gpu_model: str
    minimum_vram_mib: int
    qualified_reference_pack_ids: tuple[str, ...]
    qualified_alignment_profile_ids: tuple[str, ...]
    resource_contract_ids: tuple[str, ...]
    qualification_report_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


ONE_PASS_RESOURCE_CONTRACT_ID = "ubuntu_native_rtx3090_ram128_one_pass_42gb_v1"
TWO_PASS_RESOURCE_CONTRACT_ID = "ubuntu_native_rtx3090_ram128_two_pass_96gb_v1"
WSL_RESOURCE_CONTRACT_ID = "full_human_47gib_probe_v1"
PARABRICKS_PROCESS = "NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:PARABRICKS_RNA_FQ2BAM"


@dataclass(frozen=True)
class AlignmentResourceContract:
    contract_id: str
    host_profile_id: str
    reference_pack_id: str
    alignment_profile_id: str
    process_selector: str
    memory_gb: int
    memory_bytes: int
    cpus: int


RESOURCE_CONTRACTS = {
    ONE_PASS_RESOURCE_CONTRACT_ID: AlignmentResourceContract(
        ONE_PASS_RESOURCE_CONTRACT_ID, UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        FULL_HUMAN_REFERENCE_PACK_ID, ONE_PASS_PROFILE_ID, PARABRICKS_PROCESS,
        42, 45_097_156_608, 12,
    ),
    TWO_PASS_RESOURCE_CONTRACT_ID: AlignmentResourceContract(
        TWO_PASS_RESOURCE_CONTRACT_ID, UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        FULL_HUMAN_REFERENCE_PACK_ID, TWO_PASS_PROFILE_ID, PARABRICKS_PROCESS,
        96, 103_079_215_104, 12,
    ),
}


HOST_PROFILES = {
    WINDOWS_HOST_PROFILE_ID: HostProfile(
        WINDOWS_HOST_PROFILE_ID, "wsl2:Ubuntu", "windows", 64 * 1024**3,
        "NVIDIA GeForce RTX 3090", 24_576, (), (), (WSL_RESOURCE_CONTRACT_ID,),
        ("medium-human-capacity-resource-envelope", "parabricks-one-pass-workstation-profile"),
        ("full-human one-pass and two-pass exceed the qualified WSL memory envelope",),
    ),
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID: HostProfile(
        UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "native_linux", "linux", 128_000_000_000,
        "NVIDIA GeForce RTX 3090", 24_576, (FULL_HUMAN_REFERENCE_PACK_ID,),
        (ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID),
        (ONE_PASS_RESOURCE_CONTRACT_ID, TWO_PASS_RESOURCE_CONTRACT_ID),
        (ONE_PASS_REPORT_ID, TWO_PASS_REPORT_ID),
        ("research use only", "non-diagnostic", "cross-host BAM equality not evaluated"),
    ),
}


def get_host_profile(host_profile_id: str) -> HostProfile:
    try:
        return HOST_PROFILES[host_profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown host profile: {host_profile_id}") from exc


def select_resource_contract(
    host_profile_id: str, reference_pack_id: str, alignment_profile_id: str,
) -> AlignmentResourceContract | None:
    matches = [item for item in RESOURCE_CONTRACTS.values() if (
        item.host_profile_id == host_profile_id
        and item.reference_pack_id == reference_pack_id
        and item.alignment_profile_id == alignment_profile_id
    )]
    if len(matches) > 1:
        raise ValueError("Ambiguous fixed resource contract")
    return matches[0] if matches else None


@dataclass(frozen=True)
class HostQualificationReceipt:
    schema_version: int
    host_profile_id: str
    evidence_version: str
    qualification_report_sha256: Mapping[str, str]
    repository_commit: str
    repository_tree: str
    operating_system_family: str
    execution_context: str
    minimum_physical_ram_bytes: int
    gpu_model: str
    minimum_vram_mib: int
    resource_contract_ids: tuple[str, ...]
    reference_pack_id: str
    star_index_id: str
    salmon_index_id: str
    pipeline_version: str
    pipeline_commit: str
    plugin_closure_id: str
    plugin_cache_inventory_sha256: str
    task_image_closure_id: str
    task_image_closure_sha256: str
    archive_receipt_sha256: tuple[str, ...]
    parabricks_archive_sha256: str
    parabricks_provenance_receipt_sha256: str
    product_docker_provenance_status: str
    created_at: str
    product_cli_verified: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "HostQualificationReceipt":
        data = dict(value)
        for name in ("resource_contract_ids", "archive_receipt_sha256"):
            data[name] = tuple(data.get(name) or ())
        return cls(**data)

    @classmethod
    def load(cls, path: Path) -> "HostQualificationReceipt":
        try:
            raw = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read host qualification receipt: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("Host qualification receipt must be an object")
        try:
            return cls.from_mapping(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid host qualification receipt schema: {exc}") from exc

    def validate(self, *, report_root: Path) -> None:
        profile = get_host_profile(self.host_profile_id)
        expected_reports = {
            ONE_PASS_REPORT_ID: ONE_PASS_REPORT_SHA256,
            TWO_PASS_REPORT_ID: TWO_PASS_REPORT_SHA256,
        }
        if self.schema_version != 1 or self.evidence_version != "ubuntu-high-memory-host-capability-v1":
            raise ValueError("Unsupported host qualification receipt version")
        if (self.repository_commit, self.repository_tree) != (
            QUALIFICATION_REPOSITORY_COMMIT, QUALIFICATION_REPOSITORY_TREE,
        ):
            raise ValueError("Host receipt qualification repository identity mismatch")
        if (self.operating_system_family, self.execution_context) != (
            profile.operating_system_family, profile.execution_context,
        ):
            raise ValueError("Host receipt execution identity mismatch")
        if (self.minimum_physical_ram_bytes < profile.minimum_physical_ram_bytes
                or self.gpu_model != profile.gpu_model
                or self.minimum_vram_mib < profile.minimum_vram_mib):
            raise ValueError("Host receipt hardware contract mismatch")
        if set(self.resource_contract_ids) != set(profile.resource_contract_ids):
            raise ValueError("Host receipt resource contracts mismatch")
        if (self.reference_pack_id, self.star_index_id, self.salmon_index_id) != (
            FULL_HUMAN_REFERENCE_PACK_ID, STAR_INDEX_ID, SALMON_251_INDEX_ID,
        ):
            raise ValueError("Host receipt reference/index identity mismatch")
        if (self.pipeline_version, self.pipeline_commit) != ("3.26.0", PIPELINE_COMMIT):
            raise ValueError("Host receipt pipeline identity mismatch")
        if (self.plugin_closure_id, self.task_image_closure_id) != (
            PLUGIN_CLOSURE_ID, TASK_IMAGE_CLOSURE_ID,
        ):
            raise ValueError("Host receipt offline closure identity mismatch")
        if (self.plugin_cache_inventory_sha256
                != "629fcd902958e2cb42a36ca77d083f4860800a984d67aa3f9f72e5f4fa93cd35"
                or self.task_image_closure_sha256 != TASK_IMAGE_CLOSURE_EVIDENCE_SHA256):
            raise ValueError("Host receipt offline closure evidence mismatch")
        if dict(self.qualification_report_sha256) != expected_reports:
            raise ValueError("Host receipt qualification report identities mismatch")
        for report_id, expected_sha in expected_reports.items():
            path = report_root / f"{report_id}.json"
            if not path.is_file() or sha256_path(path) != expected_sha:
                raise ValueError(f"Qualification report missing or changed: {report_id}")
        if set(self.archive_receipt_sha256) != ARCHIVE_RECEIPT_SHA256:
            raise ValueError("Host receipt terminal archive identities are incomplete")
        if (not _SHA256.fullmatch(self.parabricks_archive_sha256)
                or not _SHA256.fullmatch(self.parabricks_provenance_receipt_sha256)
                or self.product_docker_provenance_status != "VERIFIED"):
            raise ValueError("Host receipt Parabricks provenance identity is invalid")


def installed_host_receipt_path(runtime_root: Path, host_profile_id: str) -> Path:
    get_host_profile(host_profile_id)
    return runtime_root / "host-profiles" / f"{host_profile_id}.json"


@dataclass(frozen=True)
class PluginClosureReceipt:
    schema_version: int
    plugin_name: str
    plugin_version: str
    nextflow_version: str
    inventory_sha256: str
    manifest_sha256: str
    offline_probe: str

    def validate(self) -> None:
        if (self.schema_version, self.plugin_name, self.plugin_version, self.nextflow_version) != (
            1, "nf-schema", "2.5.1", "25.04.3",
        ):
            raise ValueError("Pinned nf-schema@2.5.1 / Nextflow 25.04.3 closure mismatch")
        if (self.inventory_sha256 != "629fcd902958e2cb42a36ca77d083f4860800a984d67aa3f9f72e5f4fa93cd35"
                or self.manifest_sha256 != "78285a59f38118ecaa3b875620f01c1f1712c97a834e17cb603f6c5e64f8d2e6"
                or self.offline_probe != "PASS"):
            raise ValueError("Offline nf-schema cache receipt mismatch")


@dataclass(frozen=True)
class TaskImageRequirement:
    process_role: str
    contract: DockerImageContract
    executable_probe: str | None = None


def _image(role: str, reference: str, identity: str, kind: str, probe: str | None = None) -> TaskImageRequirement:
    return TaskImageRequirement(role, DockerImageContract(reference, identity, kind), probe)  # type: ignore[arg-type]


FULL_HUMAN_TASK_IMAGES = (
    _image("BEDTOOLS_GENOMECOV", "community.wave.seqera.io/library/bedtools_coreutils:a623c13f66d5262b", "sha256:02b83cd419b000c305904f5e7a868536c1827c49bc53a13205750eea0866f073", "image_id"),
    _image("SAMTOOLS", UBUNTU_SAMTOOLS_REFERENCE, UBUNTU_SAMTOOLS_IMAGE_ID, "image_id"),
    _image("DUPRADAR", "community.wave.seqera.io/library/bioconductor-dupradar:1.38.0--831da16eb40a64ab", "sha256:4bf2a466effd8c9c08a39f275a22fbd7d8b55b2d0959412b2cec482b7e306879", "image_id"),
    _image("SUBREAD_FEATURECOUNTS", "quay.io/biocontainers/subread:2.0.6--he4a0461_2", "sha256:114390a783c77f7739d86e474bedfa5a4e65309a2f71d4db430803fb04601f5d", "repo_digest", "featureCounts v2.0.6"),
    _image("UCSC_BEDCLIP", "quay.io/biocontainers/ucsc-bedclip:377--h0b8a92a_2", "sha256:d848a443bc2ee59504de4a2389abc196f48b3f1886938eb7d3c1cbf4a260b285", "repo_digest", "bedClip executable"),
    _image("EAUTILS_GTF2BED", "quay.io/biocontainers/perl:5.26.2", "sha256:d3998a9936be0a6f3bd91fe7d304bc3831eb1c9ff5bf83021b79b65dbfd39390", "image_id"),
    _image("RSEQC", "community.wave.seqera.io/library/rseqc_r-base:2e29d2dfda9cef15", "sha256:a636cf7f5d71bcdc5c1d1293a56b4ac429c46669a82055b74ab9c2a15224a789", "image_id"),
    _image("FASTQC", "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0", "sha256:dc85080d4574f19d39404c467ded96a90075f127e5bd3ecea3c06132632edacf", "image_id"),
    _image("UCSC_BEDGRAPHTOBIGWIG", "quay.io/biocontainers/ucsc-bedgraphtobigwig:469--h9b8f530_0", "sha256:8cddd17840d51764316fbf60d8f5a0a5e991eac9b07797bf757472aa25a87048", "image_id"),
    _image("QUALIMAP", "quay.io/biocontainers/qualimap:2.3--hdfd78af_0", "sha256:49d81e27bf995d0ef72ae46c79c22c8c779e21573cd76f7b60cf3f73af61b087", "repo_digest", "QualiMap v.2.3"),
    _image("CUSTOM_GTFFILTER", "quay.io/biocontainers/python:3.9--1", "sha256:34c2b9e3810c9e7341aeb5d38f6516c657e43be7c055368f387d56b3b0280aee", "image_id"),
    _image("FQ_LINT", "quay.io/biocontainers/fq:0.12.0--h9ee0642_0", "sha256:1778d053fa22e9546a7a1c67928ce30322797653291664a05995289d1425ba51", "image_id"),
    _image("MULTIQC", "community.wave.seqera.io/library/multiqc:1.33--ee7739d47738383b", "sha256:abc4ca8bc9cbf4745d07516523f17eb09e1edffbec82b02f06df213ac3ed13ba", "image_id"),
    _image("STRINGTIE", "quay.io/biocontainers/stringtie:2.2.3--h43eeafb_0", "sha256:3ae64324a4729c6af09eb1246cd315920136758c0d5743845fd1980769087aa3", "repo_digest", "StringTie 2.2.3"),
    _image("GUNZIP_GTF", "community.wave.seqera.io/library/coreutils_grep_gzip_lbzip2_pruned:838ba80435a629f8", "sha256:a2fb83afd6e3a0a18d587e80b07b7e9791819c56c4a0a8ea9e12df2641352cdc", "image_id"),
    _image("FASTP", "community.wave.seqera.io/library/fastp:1.0.1--c8b87fe62dcc103c", "sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45", "repo_digest"),
    _image("CUSTOM_MULTIQCCUSTOMBIOTYPE", "quay.io/biocontainers/python:3.12.12", "sha256:e13ececb5c07ee495bf4884d0271335e329926614a1c0f92a70f669ff71ea357", "image_id"),
    _image("SALMON_2_5_1", "harako-gpu/salmon:2.5.1-qualification", "sha256:6ec01c872926f446b20933ed8c948cd66eca2b49c93427d77370fb4a2e403cfe", "image_id", "salmon 2.5.1"),
)


def validate_task_image_closure(observed: Mapping[str, Mapping[str, Any]]) -> None:
    if len(FULL_HUMAN_TASK_IMAGES) != 18:
        raise ValueError("Full-human task-image closure must contain exactly 18 images")
    expected_references = {item.contract.reference for item in FULL_HUMAN_TASK_IMAGES}
    if set(observed) != expected_references:
        missing = sorted(expected_references - set(observed))
        extra = sorted(set(observed) - expected_references)
        raise ValueError(f"Full-human task-image closure mismatch; missing={missing}, extra={extra}")
    for item in FULL_HUMAN_TASK_IMAGES:
        canonical_image_identity(item.contract, observed[item.contract.reference])


def task_image_contract_for_role(
    host_profile_id: str,
    process_role: str,
) -> DockerImageContract | None:
    """Return exactly one qualified task-image role for the native host closure."""
    if host_profile_id != UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
        return None
    matches = [
        item.contract for item in FULL_HUMAN_TASK_IMAGES
        if item.process_role == process_role
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Full-human task-image closure requires exactly one {process_role} role"
        )
    matches[0].validate()
    if (
        matches[0].reference,
        matches[0].identity,
        matches[0].identity_kind,
    ) != (UBUNTU_SAMTOOLS_REFERENCE, UBUNTU_SAMTOOLS_IMAGE_ID, "image_id"):
        raise ValueError("Full-human SAMTOOLS task-image identity mismatch")
    return matches[0]


def runtime_quantification_image_contract(
    host_profile_id: str, profile_id: str,
) -> DockerImageContract | None:
    if host_profile_id != UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID or profile_id != "salmon_2_5_1_deterministic":
        return None
    return next(item.contract for item in FULL_HUMAN_TASK_IMAGES if item.process_role == "SALMON_2_5_1")


PARABRICKS_SOURCE_REFERENCE = "nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1"
PARABRICKS_MANIFEST_LIST_DIGEST = "sha256:d0761eb4b9921bc046c53520287316d545eb79feaeb8f22387e9bb5734650447"
PARABRICKS_AMD64_MANIFEST_DIGEST = "sha256:1a3fe2f3370dbc5808192c5b79c68ab795a516197eb49fc5807596a1949f9332"
PARABRICKS_CONFIG_IMAGE_ID = "sha256:52f2841e4375f2fb5081311875bbedd7dcaa709a37d84b32499e3bfa6eb4ec34"


@dataclass(frozen=True)
class OfflinePlatformImageProvenance:
    schema_version: int
    source_reference: str
    source_manifest_list_digest: str
    selected_platform: str
    platform_manifest_digest: str
    config_image_id: str
    archive_sha256: str
    image_version_output: str
    executable_probe: str
    provenance_receipt_sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OfflinePlatformImageProvenance":
        return cls(**dict(value))

    def validate(self, *, observed_image: Mapping[str, Any], expected_receipt_sha256: str,
                 expected_archive_sha256: str) -> None:
        if (self.schema_version, self.source_reference, self.source_manifest_list_digest,
                self.selected_platform, self.platform_manifest_digest, self.config_image_id) != (
            1, PARABRICKS_SOURCE_REFERENCE, PARABRICKS_MANIFEST_LIST_DIGEST,
            "linux/amd64", PARABRICKS_AMD64_MANIFEST_DIGEST, PARABRICKS_CONFIG_IMAGE_ID,
        ):
            raise ValueError("Parabricks offline platform provenance mismatch")
        if not _SHA256.fullmatch(self.archive_sha256):
            raise ValueError("Parabricks offline archive SHA-256 is invalid")
        if self.archive_sha256 != expected_archive_sha256:
            raise ValueError("Parabricks offline archive identity mismatch")
        if self.image_version_output != "pbrun 4.6.0-1" or self.executable_probe != "PASS":
            raise ValueError("Parabricks version/executable probe mismatch")
        if self.provenance_receipt_sha256 != expected_receipt_sha256:
            raise ValueError("Parabricks provenance receipt identity mismatch")
        canonical_image_identity(
            DockerImageContract(PARABRICKS_SOURCE_REFERENCE, PARABRICKS_CONFIG_IMAGE_ID, "image_id"),
            observed_image,
        )


def load_offline_provenance(path: Path) -> OfflinePlatformImageProvenance:
    try:
        raw = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read Parabricks provenance receipt: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Parabricks provenance receipt must be an object")
    try:
        return OfflinePlatformImageProvenance.from_mapping(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Parabricks provenance receipt schema: {exc}") from exc


def inspect_provenance_image(
    runner: ProcessRunner, provenance: OfflinePlatformImageProvenance,
) -> Mapping[str, Any]:
    result = runner.run(("docker", "image", "inspect", provenance.source_reference), timeout=15)
    if not result.ok:
        raise ValueError("Installed Parabricks image is unavailable for provenance validation")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Docker image inspection returned malformed JSON") from exc
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError("Docker image inspection must return one object")
    return payload[0]


@dataclass(frozen=True)
class TerminalResultsArchivePolicy:
    contract_id: str = "harako-gpu-terminal-results-archive-v1"
    active_work_storage: str = "local_ext4_ssd"
    successful_terminal_storage: str = "verified_pax_archive_on_wd_gold"
    failed_or_resumable_work: str = "retain_on_ssd"
    successful_full_work: str = "not_retained_after_verified_archive"
    deletion_mode: str = "explicit_only"


TERMINAL_RESULTS_ARCHIVE_POLICY = TerminalResultsArchivePolicy()


def featurecounts_contract(reference_pack_id: str, *, feature_type: str = "exon", group_type: str) -> tuple[str, str]:
    if reference_pack_id == FULL_HUMAN_REFERENCE_PACK_ID:
        if feature_type != "exon" or group_type != "gene_type":
            raise ValueError("GENCODE 49 qualified reference fixes FeatureCounts to -t exon -g gene_type")
        return "exon", "gene_type"
    if not feature_type or not group_type:
        raise ValueError("FeatureCounts feature/group types must be explicit")
    return feature_type, group_type
