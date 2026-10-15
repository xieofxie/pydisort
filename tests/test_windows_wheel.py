"""Windows wheels must load their bundled solver without build-tree DLLs."""

from pathlib import Path
import os
import subprocess
import sys

import pytest
import torch


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DLL packaging")
@pytest.mark.parametrize(
    "device",
    [
        "cpu",
        pytest.param(
            "cuda",
            marks=pytest.mark.skipif(
                not torch.cuda.is_available(), reason="no CUDA device available"
            ),
        ),
    ],
)
def test_windows_wheel_is_self_contained(tmp_path, device):
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
            """
import sys
import torch
import pydisort

assert pydisort.scattering_moments(4, 'isotropic').shape == (4,)
device = sys.argv[1]
op = pydisort.DisortOptions().flags("onlyfl,lamber,quiet")
op.ds().nlyr = 4
op.ds().nstr = op.ds().nmom = op.ds().nphase = 8
tau = torch.tensor([0.1, 0.2, 0.3, 0.4], dtype=torch.float64, device=device)
flux = pydisort.Disort(op)(
    tau.unsqueeze(-1), fbeam=torch.ones(1, dtype=tau.dtype, device=device)
)
expected = torch.exp(-torch.cat((tau.new_zeros(1), tau.cumsum(0))))
assert flux.device.type == device
torch.testing.assert_close(flux[0, 0, :, 1], expected)
torch.testing.assert_close(flux[0, 0, :, 0], torch.zeros_like(expected))
""",
            device,
        ],
        cwd=tmp_path,
        env=env,
        check=True,
    )
