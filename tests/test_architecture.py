from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "harako_gpu"


def modules_and_edges():
    modules: dict[str, Path] = {}
    for path in PACKAGE.rglob("*.py"):
        parts = list(path.relative_to(PACKAGE).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules["harako_gpu" + (f".{'.'.join(parts)}" if parts else "")] = path
    edges = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package.split(".")[: -(node.level - 1) or None]
                    target = ".".join([*base, *([node.module] if node.module else [])])
                else:
                    target = node.module or ""
                targets.append(target)
                targets.extend(f"{target}.{alias.name}" for alias in node.names if target)
            edges[module].update(target for target in targets if target in modules)
    return modules, edges


def test_core_has_no_cli_ui_subprocess_or_adapter_imports() -> None:
    for path in sorted((PACKAGE / "core").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not any(name == "typer" or name.startswith("typer.") for name in imported)
        assert not any(name == "streamlit" or name.startswith("streamlit.") for name in imported)
        assert not any(name == "subprocess" or name.startswith("subprocess.") for name in imported)
        assert not any("harako_gpu.adapters" in name for name in imported)


def test_subprocess_is_centralized_in_process_and_gui_launcher_adapters() -> None:
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.as_posix().endswith("adapters/process.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "subprocess" for alias in node.names):
                offenders.append(path)
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                offenders.append(path)
    # nextflow uses only the standard-library quoting primitive, never process execution.
    assert offenders == [PACKAGE / "adapters" / "gui_launcher.py", PACKAGE / "adapters" / "nextflow.py"]
    nextflow = (PACKAGE / "adapters" / "nextflow.py").read_text(encoding="utf-8")
    assert "subprocess.run" not in nextflow and "subprocess.Popen" not in nextflow
    launcher = (PACKAGE / "adapters" / "gui_launcher.py").read_text(encoding="utf-8")
    assert "shell=False" in launcher and "shell=True" not in launcher


def test_command_handlers_do_not_embed_backend_or_scientific_decisions() -> None:
    forbidden = ("nf-core/rnaseq", "3.26.0", "star_salmon", "use_parabricks_star", "subprocess.run")
    for path in (PACKAGE / "commands").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden), path


def test_application_import_graph_has_no_cycles() -> None:
    modules, edges = modules_and_edges()
    visited: set[str] = set()
    active: set[str] = set()

    def visit(module: str) -> None:
        if module in active:
            raise AssertionError(f"application import cycle includes {module}")
        if module in visited:
            return
        active.add(module)
        for dependency in edges[module]:
            visit(dependency)
        active.remove(module)
        visited.add(module)

    for module in modules:
        visit(module)


def test_reference_aware_gui_exists_without_snakemake_compatibility() -> None:
    assert (PACKAGE / "ui" / "app.py").is_file()
    assert not any("snakemake" in path.name.lower() for path in ROOT.rglob("*"))


def test_streamlit_is_confined_to_ui_and_command_launcher() -> None:
    offenders = []
    for root in (PACKAGE / "core", PACKAGE / "services"):
        for path in root.rglob("*.py"):
            if "streamlit" in path.read_text(encoding="utf-8"):
                offenders.append(path)
    assert offenders == []


def test_ui_never_imports_subprocess_or_writes_run_state() -> None:
    for path in (PACKAGE / "ui").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "import subprocess" not in source
        assert ".write_text(" not in source
        assert "status.json" not in source
        assert "run.json" not in source
