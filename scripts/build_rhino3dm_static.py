#!/usr/bin/env python3
"""
Rebuilds rhino3dm's compiled extension from source with the MSVC runtime
statically linked, then overwrites the pip-installed rhino3dm package in
the current Python environment with the result.

Why: rhino3dm's official Windows wheel dynamically links vcruntime140.dll /
msvcp140.dll. On a machine missing that runtime, `import rhino3dm` fails
with "DLL load failed while importing rhino3dm" (see core/vcredist_repair.py
for the earlier fallback this supersedes — it worked, but still meant a
UAC prompt on affected machines). Statically linking the runtime into the
extension itself means there's no separate runtime to be missing, ever,
for any user, and no prompt of any kind.

Windows-only. No-op (prints a message and exits 0) on any other platform,
so it's safe to call unconditionally from a cross-platform build step —
macOS's .so build has no equivalent dependency and isn't touched.

Requires on PATH: git, cmake >= 3.21, and a Visual Studio C++ toolchain.
GitHub's windows-latest runners have all three preinstalled. Run this
*after* `pip install -r requirements.txt` (which installs the normal
PyPI rhino3dm as the thing this script then overwrites) and *before*
running PyInstaller.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RHINO3DM_VERSION = "8.17.0"  # keep in sync with the version used elsewhere
REPO_URL = "https://github.com/mcneel/rhino3dm.git"

# Two real build attempts on Windows CI (12+ min each) confirmed:
#   1. CMAKE_MSVC_RUNTIME_LIBRARY alone: rhino3dm's own src/CMakeLists.txt
#      (cmake_minimum_required 3.16) picked it up fine, but draco — a
#      separate, standalone CMake project of its own (its own
#      `cmake <draco_src_dir>` invocation, pinned at
#      cmake_minimum_required 3.12) — silently ignored it, since
#      CMAKE_MSVC_RUNTIME_LIBRARY only takes effect under CMake policy
#      CMP0091 "NEW", which a project only gets by default at >= 3.15.
#   2. Adding CMAKE_POLICY_DEFAULT_CMP0091=NEW to force that policy on
#      draco's build too: same LNK2038 mismatch anyway. draco.lib stayed
#      dynamically linked regardless.
# So instead of relying on the CMP0091 property mechanism at all, force
# the actual compile flags directly — the traditional, pre-CMP0091
# mechanism (CMake seeds CMAKE_<LANG>_FLAGS_RELEASE with its own /MD
# default as a CACHE variable only if one doesn't already exist; supplying
# it via -D on the command line pre-empts that default entirely,
# regardless of policy state). /O2 /Ob2 /DNDEBUG are CMake's own stock
# MSVC Release defaults, kept here so we're only swapping /MD for /MT, not
# also dropping optimization.
_RELEASE_FLAGS = "/MT /O2 /Ob2 /DNDEBUG"
STATIC_RUNTIME_ARGS = [
    "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
    "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded",
    f"-DCMAKE_C_FLAGS_RELEASE={_RELEASE_FLAGS}",
    f"-DCMAKE_CXX_FLAGS_RELEASE={_RELEASE_FLAGS}",
]
STATIC_RUNTIME_FLAG = "".join(f"'{arg}', " for arg in STATIC_RUNTIME_ARGS)


def run(cmd, **kwargs):
    print(f"[build_rhino3dm_static] $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def patch_setup_py(setup_py: Path) -> None:
    """Inject STATIC_RUNTIME_FLAG into setup.py's two Windows CMake configure
    calls. Upstream's setup.py hardcodes these commands for Windows and
    doesn't expose a hook to pass extra CMake defines through, so we edit
    the file's text directly. Aborts loudly (rather than silently building
    a dynamically-linked binary) if upstream's code no longer matches what
    we expect to patch — a stale patch here must never fail silently, since
    the whole point of this script is what it does NOT bundle afterward.
    """
    text = setup_py.read_text()

    draco_anchor = 'command = [\'cmake\', \'-A\', osplatform, f"{draco_src_dir}"]'
    if text.count(draco_anchor) != 1:
        sys.exit(
            "ERROR: rhino3dm's setup.py draco cmake command didn't match the "
            "expected text (upstream may have changed) — aborting rather than "
            "risk silently building a dynamically-linked binary."
        )
    text = text.replace(
        draco_anchor,
        f'command = [\'cmake\', \'-A\', osplatform, {STATIC_RUNTIME_FLAG}f"{{draco_src_dir}}"]',
    )

    rhino_anchor = 'ext.sourcedir+"/src"]'
    if text.count(rhino_anchor) != 1:
        sys.exit(
            "ERROR: rhino3dm's setup.py main cmake command didn't match the "
            "expected text (upstream may have changed) — aborting rather than "
            "risk silently building a dynamically-linked binary."
        )
    text = text.replace(
        rhino_anchor,
        f'{STATIC_RUNTIME_FLAG}\n                        {rhino_anchor}',
    )

    setup_py.write_text(text)
    print("[build_rhino3dm_static] Patched setup.py for static MSVC runtime linkage.")


def main() -> None:
    if sys.platform != "win32":
        print("[build_rhino3dm_static] Not on Windows — nothing to do.")
        return

    clone_dir = Path(tempfile.gettempdir()) / "rhino3dm-static-build"
    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    run([
        "git", "clone", "--recurse-submodules", "--depth", "1",
        "--branch", RHINO3DM_VERSION, REPO_URL, str(clone_dir),
    ])

    patch_setup_py(clone_dir / "setup.py")

    run([sys.executable, "setup.py", "build_ext", "--inplace"], cwd=str(clone_dir))

    built_pkg_dir = clone_dir / "src" / "rhino3dm"
    built_pyds = list(built_pkg_dir.glob("_rhino3dm*.pyd"))
    if not built_pyds:
        sys.exit(
            f"ERROR: no _rhino3dm*.pyd found in {built_pkg_dir} after build "
            "— the build must have failed silently."
        )
    print(f"[build_rhino3dm_static] Built: {built_pyds[0]} ({built_pyds[0].stat().st_size} bytes)")

    import rhino3dm as _installed  # the pip-installed copy `pip install -r requirements.txt` put in place
    installed_dir = Path(_installed.__file__).resolve().parent
    print(f"[build_rhino3dm_static] Overwriting installed package at: {installed_dir}")

    # Remove the old (dynamically-linked) compiled extension(s) first so a
    # stale copy can't shadow the new one, then copy our freshly-built
    # package over the top.
    for old_pyd in installed_dir.glob("_rhino3dm*.pyd"):
        old_pyd.unlink()
    for item in built_pkg_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, installed_dir / item.name)

    print("[build_rhino3dm_static] Done. rhino3dm now uses the statically-linked build.")


if __name__ == "__main__":
    main()
