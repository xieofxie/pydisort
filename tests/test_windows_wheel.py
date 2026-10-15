"""Windows wheels must load their bundled solver without build-tree DLLs."""

from pathlib import Path
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DLL packaging")
def test_windows_wheel_is_self_contained(tmp_path):
    import pydisort

    package = Path(pydisort.__file__).parent
    assert (package / "disort_release.dll").is_file()
    assert not list(package.glob("torch*.dll"))
    assert not list(package.glob("c10*.dll"))

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import pydisort; "
            "assert pydisort.scattering_moments(4, 'isotropic').shape == (4,)",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
    )
