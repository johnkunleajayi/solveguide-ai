# One-folder bundle: Python and DLLs included, no temporary one-file extraction.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

backend = Path(SPECPATH).resolve()
project = backend.parent
analysis = Analysis(
    [str(backend / "packaged_entry.py")], pathex=[str(backend)],
    datas=collect_data_files("docx") + collect_data_files("certifi"),
    binaries=collect_dynamic_libs("psycopg_binary"),
    hiddenimports=["app.main", "app.runtime", "uvicorn.logging", "uvicorn.lifespan.on",
        "uvicorn.protocols.http.h11_impl", "sqlalchemy.dialects.postgresql.psycopg", "psycopg_binary"],
    excludes=["pytest", "ruff", "tkinter", "IPython"], noarchive=False,
)
# Fail closed if a hook attempts to copy private project configuration/documents.
for destination, source, _ in analysis.datas:
    path = Path(source).resolve()
    if path.name.startswith(".env") or path.is_relative_to(project / ".cache" / "context-library"):
        raise RuntimeError("Private configuration or user documents cannot be bundled")
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries=True,
    name="solveguide-backend", debug=False, strip=False, upx=False, console=True)
collection = COLLECT(executable, analysis.binaries, analysis.datas,
    strip=False, upx=False, name="solveguide-backend")
