# Medium human capacity dataset selection

`medium-human-err188044-v1` was frozen before FASTQ acquisition or
quantification. The selected public run is ENA `ERR188044` from Geuvadis
project `PRJEB3366` (`ERP001942`), sample `SAMEA1573216`, experiment
`ERX162864`. It is Homo sapiens transcriptomic cDNA RNA-seq, paired-end,
sequenced on an Illumina HiSeq 2000. ENA declares 36,349,964 reads/spots and
5,525,194,528 bases.

The two official FASTQs total 5,155,400,360 bytes. Their file names, URLs,
sizes, and MD5 values are frozen in the adjacent JSON. No fallback dataset is
selected.

The experiment record identifies TruSeq RNA Sample Prep Kit v2 but does not
state strandedness explicitly. Library type therefore remains pending until a
result-independent orientation probe. The probe compares only orientation
consistency for `IU`, `ISF`, and `ISR`; it must achieve at least 80% consistency
and a 20 percentage-point margin. Abundance, truth accuracy, or overall mapping
rate may not select the library type. Failure to meet the rule makes the
dataset unusable rather than triggering an automatic fallback.

The dataset is a capacity/storage fixture. It is not an abundance-accuracy or
diagnostic benchmark.
