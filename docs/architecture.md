# Architecture

## Execution lifecycle boundary

Core owns immutable run/task/artifact models, state transitions, and failure
taxonomy. Services own preparation, fixed-stage execution, status/resume,
matrix/concordance coordination, artifact verification, and support bundles.
Adapters alone own subprocess, WSL/native exec, Docker inspection, filesystem,
liveness, samtools, resource monitoring, and archives. Commands and Streamlit
pages remain thin
Typer projections. Mutable run state has one writer (`RunStateStore`); core does
not import subprocess, adapters, Typer, or UI code.
The implementation deliberately uses four concrete responsibility groups:

```text
Typer commands
    -> application services
        -> pure core rules and schemas
        -> explicit infrastructure adapters
```

`core` owns FASTQ naming, sample structure, analysis eligibility, canonical
serialization, identity hashes, versioned data contracts, artifact types, and
the BAM state machine. It has no CLI, UI, subprocess, Docker, or Nextflow
knowledge.

`services` owns input inspection, preflight orchestration, fixed backend profile
generation, run-plan creation, plan validation, and independent FASTQ Salmon
identity/trace gates. The Salmon 1.12.1 upgrade service models only an exact
candidate release/image/index, structured argv, fixed process selectors, and
comparison gates. It does not launch processes or add a generic version plugin;
its override generator fails closed for the observed rejected status.
Scientific/backend choices are not made in command
handlers. The independent contract is concrete to nf-core/rnaseq 3.26.0; it is
not a generic workflow abstraction.

`salmon_2x_qualification` models only the exact 2.5.1 supply-chain/index/argv,
reproducibility, and truth gates. It contains no process execution and emits
its narrow nf-core fragment only after all direct and truth gates pass.
`decoy_accounting` independently models sequence identifiability, immutable
absolute/relative gates, and truth-v2 biological summaries without importing
subprocess or Salmon. Qualification scripts perform structured runtime
execution outside core/services. Truth-v2 internal gates passed and therefore
made the narrow conditional integration path reachable; this does not expose a
default product profile.

`external_truth_validation` is likewise pure metric/contract code. It models
metadata-only ERCC lane selection, official truth-table identity, abundance and
fold-change gates, deterministic identity, cross-mapping limits, and
zero-variance failure states. It neither downloads data nor launches Salmon;
external acquisition remains isolated to qualification activity.

`adapters` owns filesystem I/O, process execution, environment detection,
Docker/WSL inspection, and structured Nextflow argv/quoting. Scientific
child-process execution is centralized in `adapters/process.py`; the sole GUI
exception is `adapters/gui_launcher.py`, which launches only fixed Streamlit
and exact `harako_gpu run start|resume` argv. Shell execution is disabled.

The `ui` package contains presentation state, bilingual labels, view models,
fixed pages, and components. It calls application services and never owns run
state or scientific eligibility. There is no generic engine interface,
Snakemake compatibility, database, Docker SDK, or Nextflow Python wrapper.
Import-cycle and dependency-boundary tests enforce these decisions.

The concrete execution transport freezes WSL2 or native Linux identity without
introducing a generic executor abstraction. See
[native Linux execution](native-linux-execution.md) for the authoritative contract.

Versioned expression functionality preserves the same direction. The
`quantification_profiles`, `star_gene_counts`, and `concordance` services own
catalog, immutable-series, parsing, and descriptive metric contracts without
launching child processes. `versioned_salmon` is a narrow adapter that creates
structured Docker argv and executes the two fixed profiles sequentially.
Command modules only translate CLI input. STAR generation remains in the
pinned Nextflow/Parabricks boundary; the comparator parser never invokes STAR
or substitutes another counter.

Reference-aware routing preserves this boundary. Pure capability models bind
an exact host profile, reference-pack identity, alignment profile, BAM mode,
and quantification profiles to a versioned decision with evidence. Planning
freezes either `gpu_bam_alignment` or `fastq_quantification_only`; it never
silently converts one route to the other. The quantification-only application
service runs the fixed, qualified fastp and Salmon adapters, while core records
only route, state, task, and artifact semantics. BAM, STAR GeneCounts, and
junction artifacts are `NOT_APPLICABLE` on that CPU-only route rather than
being inferred as missing.

Usability components remain inside `ui`: centralized bilingual labels, page
introductions, semantic message presentation, result summaries, and UI-only
polling preferences. They consume service results without changing scientific
eligibility or state. Playwright is an exact-pinned test dependency only and is
not imported by runtime packages.
