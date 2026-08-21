from __future__ import annotations

import json
import zipfile

from harako_gpu.services.support_bundle import create_support_bundle


def test_support_bundle_redacts_paths_secrets_and_excludes_biology(tmp_path) -> None:
    run = tmp_path / "run"; (run / "frozen").mkdir(parents=True); (run / "support").mkdir()
    (run / "execution/attempts/0001").mkdir(parents=True)
    (run / "artifacts").mkdir()
    (run / "run.json").write_text(json.dumps({"path": "/home/alice/runtime", "token": "secret-value"}))
    (run / "status.json").write_text("{}")
    (run / "frozen/paths.tsv").write_text("role\tlinux_path\nRUN_DIR\t/home/alice/runtime/run\n")
    (run / "frozen/plan.json").write_text(json.dumps({"reference": {"fasta_path": "/home/alice/ref.fa"}, "samples": []}))
    (run / "execution/attempts/0001/stderr.log").write_text("password=abc /home/alice/runtime/run")
    (run / "results").mkdir(); (run / "results/sample.fastq.gz").write_bytes(b"BIO")
    bundle = create_support_bundle(run)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "bundle-manifest.json" in names and not any("fastq" in name for name in names)
        content = b"\n".join(archive.read(name) for name in names)
        assert b"secret-value" not in content and b"password=abc" not in content
        assert b"/home/alice" not in content
        manifest = json.loads(archive.read("bundle-manifest.json"))
        assert all(len(item["sha256"]) == 64 for item in manifest["entries"])
