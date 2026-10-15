import sys
import os
import glob
import shutil
from pathlib import Path
from setuptools import setup

try:
    import torch
    from torch.utils import cpp_extension
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "PyTorch could not be imported while building pydisort from source. "
        "For normal use, install a prebuilt PyPI wheel; no repository "
        "checkout or compiler is needed:\n"
        "    python -m pip install --only-binary=pydisort pydisort\n"
        "If pip reports no matching distribution, check the supported "
        "Python versions and platforms in the installation guide. "
        "If you intended to build from source, follow its source-build "
        "instructions:\n"
        "    https://pydisort.readthedocs.io/en/latest/installation.html"
    ) from exc


def parse_library_names(libdir):
    library_names = []
    for root, _, files in os.walk(libdir):
        for file in files:
            if sys.platform == "win32" and file.endswith(".lib"):
                # Only solver import libraries and the static fmt dependency.
                if (
                    Path(root, file).with_suffix(".dll").is_file()
                    or file == "fmt.lib"
                ):
                    library_names.append(Path(file).stem)
            elif file.endswith((".a", ".so", ".dylib")):
                file_name = os.path.basename(file)
                library_names.append(file_name[3:].rsplit(".", 1)[0])
    return library_names


current_dir = os.getenv("WORKSPACE", Path().absolute())
include_dirs = [
    f"{current_dir}",
    f"{current_dir}/build",
    f"{current_dir}/build/_deps/fmt-src/include",
]
lib_dirs = [f"{current_dir}/build/lib"]
libraries = parse_library_names(f"{current_dir}/build/lib")

if sys.platform == "win32":
    extra_link_args = []
elif sys.platform == "darwin":
    extra_link_args = [
        "-Wl,-rpath,@loader_path/lib",
        "-Wl,-rpath,@loader_path/../torch/lib",
    ]
else:
    extra_link_args = [
        "-Wl,-rpath,$ORIGIN/lib",
        "-Wl,-rpath,$ORIGIN/../torch/lib",
    ]


class BuildExtension(cpp_extension.BuildExtension):
    def run(self):
        super().run()
        if sys.platform == "win32":
            dlls = list(Path(lib_dirs[0]).glob("*.dll"))
            if not dlls:
                raise FileNotFoundError(
                    "No solver DLL found in build/lib; run CMake first."
                )
            destination = Path(
                self.get_ext_fullpath("pydisort.pydisort")
            ).parent
            for dll in dlls:
                shutil.copy2(dll, destination / dll.name)

    def get_outputs(self):
        outputs = super().get_outputs()
        if sys.platform == "win32":
            destination = Path(
                self.get_ext_fullpath("pydisort.pydisort")
            ).parent
            outputs.extend(str(p) for p in destination.glob("*.dll"))
        return outputs


if sys.platform != "win32" and torch.cuda.is_available():
    ext_module = cpp_extension.CUDAExtension(
        name="pydisort.pydisort",
        sources=glob.glob("python/csrc/*.cpp")
        + glob.glob("src/**/*.cu", recursive=True),
        include_dirs=include_dirs,
        library_dirs=lib_dirs,
        libraries=libraries,
        extra_compile_args={"nvcc": ["--extended-lambda"]},
        extra_link_args=extra_link_args,
    )
else:
    ext_module = cpp_extension.CppExtension(
        name="pydisort.pydisort",
        sources=glob.glob("python/csrc/*.cpp"),
        include_dirs=include_dirs,
        library_dirs=lib_dirs,
        libraries=libraries,
        extra_compile_args=["/bigobj", "/utf-8"]
        if sys.platform == "win32"
        else [],
        extra_link_args=extra_link_args,
    )

setup(
    package_dir={"pydisort": "python"},
    packages=["pydisort"],
    ext_modules=[ext_module],
    cmdclass={"build_ext": BuildExtension},
)
