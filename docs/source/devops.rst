Developer's guide to this repo
==============================

pre-commit hooks
~~~~~~~~~~~~~~~~

This repo uses ``pre-commit`` hooks for formatting and lint checks. Run the
solver tests separately; the hooks do not execute them.
This `pre-commit` hook is defined in the `.pre-commit-config.yaml` file in the root directory of this repo.
To install the `pre-commit` hooks, run `pre-commit install` in the root directory.
This will install the `pre-commit` hooks in the local `.git` directory.
The `pre-commit` hooks will run automatically when you try to commit code.
If the `pre-commit` hooks fail, the commit will be aborted.
To run the `pre-commit` hooks manually, run `pre-commit run --all-files` in the root directory of this repo.

CI/CD
~~~~~

Three workflows live in ``.github/workflows`` and between them cover the life
of a change:

.. list-table::
   :widths: 22 30 48
   :header-rows: 1

   * - Workflow
     - Trigger
     - What it does
   * - ``ci.yml``
     - Pull request to ``main``, and pushes to ``main``
     - Style checks, then builds and runs the CTest suite across a matrix
       of operating systems and Python versions.
   * - ``cd.yml``
     - A pull request to ``main`` is merged
     - Works out the next version from the PR labels, pushes the tag, and
       creates a GitHub release.
   * - ``release.yml``
     - Manual dispatch, given a tag
     - Builds wheels with ``cibuildwheel`` and publishes them to PyPI.

Publishing is the only manual step. Merging a pull request produces a tag and a
release on its own, but nothing reaches PyPI until someone runs **Publish to
PyPI** against that tag.

The ``ci.yml`` workflow
~~~~~~~~~~~~~~~~~~~~~~~

The Linux/macOS and Windows build jobs both depend on the style-check job.

``pre-commit`` runs the hooks from ``.pre-commit-config.yaml`` across the whole
repository, with ``~/.cache/pre-commit`` cached against the hash of that file so
hook environments are not rebuilt on every run.

``build-and-test`` then builds and tests on a four-way matrix:

.. code-block:: yaml

    strategy:
      fail-fast: true
      matrix:
        os: [ubuntu-latest, macOS-latest]
        python-version: ["3.11", "3.14"]

CI exercises Python 3.11 and 3.14, not every supported Python version; ``release.yml`` builds
wheels for every version from 3.10 to 3.14.

``build-and-test-windows`` uses ``windows-2022`` with x64 Python 3.11 and
3.14, MSVC and Ninja. It builds the CPU library, builds and installs a wheel,
runs pytest outside the checkout, then runs CTest. The installed-wheel test
also imports in a subprocess with build directories removed from PATH to
verify that the solver DLL is packaged correctly.

On Linux, ``torch`` comes from the CPU index so the runner does not download a
multi-gigabyte CUDA wheel it has no use for:

.. code-block:: yaml

    if [[ "$RUNNER_OS" == "Linux" ]]; then
      pip install 'torch==2.10.0' --index-url https://download.pytorch.org/whl/cpu
    else
      pip install 'torch==2.10.0'
    fi

The package is then installed with ``pip install --no-build-isolation --no-deps
.``, which reuses the library CMake has just built rather than compiling a
second copy inside an isolated build environment.

Tests run through CTest rather than pytest directly:

.. code-block:: bash

    ctest --test-dir build --output-on-failure

The C, C++ and Python solver tests are registered as CTest cases (see
:doc:`testing`). Tooling checks for benchmarks, documentation rendering and
setup guidance are :ref:`separate developer checks <separate-developer-checks>`;
they are not exercised by this CI command.

The ``cd.yml`` workflow
~~~~~~~~~~~~~~~~~~~~~~~

This fires when a pull request to ``main`` closes, and stops immediately unless
the pull request was actually merged:

.. code-block:: yaml

    if: ${{ github.event.pull_request.merged == true }}

The size of the version bump comes from the labels on the merged pull request.
``release:major``, ``release:minor`` and ``release:patch`` choose which
component to increment, ``patch`` is assumed when none is present, and more
than one is an error. The new number is derived from the most recent tag, and
the workflow queries the remote before claiming a tag so it can never reuse one
that already exists.

The release workflow uses three guards:

- The job is serialised through ``concurrency: {group: auto-tag-main}`` with
  ``cancel-in-progress: false``, so two pull requests merged close together
  cannot race for the same version number.
- If the merge commit already carries a ``vX.Y.Z`` tag, the job skips instead
  of bumping again.
- It authenticates as a GitHub App (``bump-bot``) through
  ``actions/create-github-app-token`` rather than using the default token.

The trigger is ``pull_request_target`` rather than ``pull_request`` so that the
App credentials are available even when the pull request comes from a fork.
That event is privileged, so the job is careful never to check out or execute
contributor code: the checkout takes the base branch, and every value read from
the pull request is passed through ``env:`` instead of being interpolated into a
shell command or a script body.

It finishes by creating the GitHub release with ``--generate-notes`` and posting
those notes back as a comment on the merged pull request.

The ``release.yml`` workflow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Triggered by hand, taking the tag to publish and a choice of platforms:

.. code-block:: yaml

    on:
      workflow_dispatch:
        inputs:
          tag:
            description: "Tag to publish, for example v2.1.0"
            required: true
          build_os:
            description: "OS"
            default: "All"
            type: choice
            options: [All, Both, MacOS, Ubuntu, Windows]

``build-macos`` and ``build-linux`` each run ``cibuildwheel`` over Python 3.10
to 3.14, producing ``arm64`` wheels on macOS and ``x86_64`` on Linux. Both skip
free-threaded builds (``*t-*``), because the pybind11 extension is not declared
free-threaded safe and cibuildwheel would otherwise build ``cp3XXt`` on 3.14 and
later. Linux additionally skips ``musllinux``.

``build-windows`` builds CPU-only ``win_amd64`` wheels for Python 3.10-3.14
on ``windows-2022`` with MSVC and Ninja, skipping free-threaded builds.
``All`` selects all three platforms; ``Both`` retains its original meaning
of macOS and Linux only. ``Windows`` selects just Windows x64.
The Windows build disables build isolation to use the same PyTorch
installation for CMake and the bindings, bundles the solver DLL beside the
extension, and tests the installed wheel with pytest before uploading it.
Automatic Windows wheel repair is disabled because the solver DLL is already
packaged and PyTorch supplies its own libraries. It does not bundle PyTorch's
DLLs or build Windows CUDA/ARM64 wheels.

Two details matter for a compiled PyTorch extension:

- ``CIBW_BEFORE_BUILD`` configures and builds the C++ library first, pointing
  CMake at the installed torch through ``torch.utils.cmake_prefix_path``. The
  Linux job does this inside ``pytorch/manylinux2_28-builder:cuda12.8`` and
  configures with ``-DCUDA=ON``.
- The repair step deliberately leaves the torch libraries out of the wheel,
  using ``delocate-wheel -e torch -e disort_release`` on macOS and
  ``auditwheel repair --exclude lib*.so`` on Linux. Vendoring them would
  duplicate the user's own torch installation and clash with it at import time.

``publish-pypi`` collects every ``wheels-*`` artifact into ``dist/`` and uploads
through ``pypa/gh-action-pypi-publish``. The job itself runs with ``if:
always()`` so that a failure on one platform does not throw away the wheels from
the other, but the upload step is still guarded: it needs at least one build job
to have succeeded and none to have failed or been cancelled.

Build system: CMake
~~~~~~~~~~~~~~~~~~~

The build needs CMake 3.20 or newer and a C++17 compiler. Three options control
what gets configured:

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Option
     - Default
     - Effect
   * - ``BUILD_TESTS``
     - ``ON``
     - Adds ``tests/``, which registers the C, C++ and Python tests with CTest.
   * - ``BUILD_EXAMPLES``
     - ``OFF``
     - Adds ``examples/``, registering each example script as a test.
   * - ``CUDA``
     - ``OFF``
     - Declares CUDA as a project language and requires ``CUDAToolkit``. When
       ``CMAKE_CUDA_ARCHITECTURES`` is not set, a list is chosen from the
       detected toolkit version.

Configuration starts by importing the installed ``torch`` to read
``_GLIBCXX_USE_CXX11_ABI``, then mirrors that value with
``add_compile_definitions``. This is why ``torch`` has to be importable before
``cmake`` runs, and why configuration fails outright rather than producing a
library whose ABI disagrees with the torch it will be loaded beside.

``cmake/modules/`` is added to ``CMAKE_MODULE_PATH`` (it holds
``FindTorch.cmake``), and every file in ``cmake/macros/`` is globbed and
included, which is where ``setup_test`` and friends come from. Libraries are
written to ``build/lib``.

Two subdirectories build the library itself. ``cdisort213/`` is a header-only
``INTERFACE`` target exposed as ``pydisort::cdisort``, and ``src/`` compiles the
C++ wrapper into ``libdisort_<buildtype>`` (``disort_<buildtype>.dll`` on
Windows) and exposes it as
``pydisort::disort``.

Windows uses MSVC with the shared runtime. CMake generates the public
``disort_export.h`` header for DLL exports and copies public headers into
``build/disort`` so a checkout does not need Windows symlink privileges.
The Windows dispatcher calls the CPU or CUDA kernel directly rather than
using PyTorch's private dispatch macros, which mark custom stubs as DLL
imports. With ``-DCUDA=ON``, CMake compiles CUDA sources into the same solver
DLL and requires a CUDA-enabled PyTorch installation. The default and the
Windows release workflow remain CPU-only.

The two-step build
~~~~~~~~~~~~~~~~~~

``setup.py`` does not invoke CMake. It links the pybind11 extension against
whatever already exists in ``build/lib``, so the order matters:

.. code-block:: bash

    cmake -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --parallel
    pip install . --no-build-isolation

The build requirements in ``pyproject.toml`` include PyTorch, so PEP 517
isolation does not inherently mean that torch is missing. However, an isolated
build can use a different torch installation from the one used by CMake.
Install the declared build tools first, then disable isolation to keep the
C++ library and Python extension on the same environment. Neither form of
``pip install .`` replaces the CMake step. See :doc:`installation` for the
complete dependency list and commands.

The extension is linked with rpath entries for ``@loader_path/lib`` and
``@loader_path/../torch/lib`` (``$ORIGIN`` on Linux), so at import time it
resolves both the disort library and torch's own shared objects.
``setup.py`` also chooses between ``CppExtension`` and ``CUDAExtension``
depending on whether ``torch.cuda.is_available()`` on Linux/macOS. Windows
always uses ``CppExtension`` and packages the solver DLL next to the
``.pyd`` instead of using Unix rpaths, including for CUDA source builds:
their CUDA kernels are already in the CMake-built solver DLL.

Reference articles
~~~~~~~~~~~~~~~~~~

- `Official pre-commit documentation <https://pre-commit.com/>`_
