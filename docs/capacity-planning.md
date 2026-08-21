# Human capacity planning

Capacity qualification uses deterministic, nested paired-read prefixes from a
single preregistered public run. It is a resource and artifact exercise, not an
expression-accuracy benchmark. Each scale receives a new immutable run and
Nextflow work directory; references, version-specific indices, and container
images are shared only by fixed identity.

The frozen ladder is 1M pairs (`recommended_only`), 5M pairs
(`compare_both`), 10M pairs (`recommended_only`), and a conditional 20M pairs.
The first three levels are required. The 20M level may run only after a
comfortable 10M result. The source order is preserved by taking the first N
pairs, validating every four-line FASTQ record and normalized mate QNAME, and
writing deterministic gzip streams (mtime 0). This makes all levels exact
nested prefixes. It does not make the leading reads biologically representative.

Before each stage, free space minus a conservative 1.5x high-water estimate
must retain the larger of 30 GiB or 15% of filesystem capacity. Scaling stops
after OOM/CUDA failure, RAM use at or above 90%, available RAM below 4 GiB for
30 seconds, VRAM at or above 95%, or loss of the disk reserve. RAM at 80%, VRAM
at 90%, and available RAM below 8 GiB are warnings.

The 2026-08-17 workstation exercise did not establish a supported human-read
envelope. Full-reference Parabricks 4.6.0-1 exhausted the visible 47.05 GiB WSL
memory during the 1M-pair C1 alignment: measured use reached 48.42 GB
(95.85%), available memory fell to 2.10 GB, and the process ended by SIGKILL.
GPU memory peaked at 12,695 MiB of 24,576 MiB, so GPU capacity was not the
limiting resource. C2-C4 were not run. No estimator is published because no
capacity level reached terminal success.

The reference/index build measurements are still useful preparation evidence,
but they are not an operating-scale claim. No value may be extrapolated to a
full run, multiple simultaneous samples, or standard-memory operation.

The prospective one-pass ladder used a stricter 40-GiB/15% disk reserve and
changed only `two-pass-mode` to explicit `None`. C1 still failed during mapping
at 46,235,611,136 bytes RAM (91.53%) with 3.99 GiB available and no swap.
VRAM peaked at 12,686 MiB and disk reserve remained intact. C2-C4 were
safety-gated. This second profile therefore also establishes no supported
full-human scale on the current host.
The separate CPU quantification-only envelope completed 1M, 5M compare-both,
10M, 20M compare-both, and full 36.35M-pair ERR188044. Its conservative internal
operating recommendation is 20M pairs. These observations do not qualify
full-human Parabricks BAM.
