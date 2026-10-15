#pragma once

// torch
#include <ATen/TensorIterator.h>
#include <ATen/native/DispatchStub.h>

// disort
#include <cdisort213/cdisort.hpp>

namespace at::native {

using disort_fn = void (*)(at::TensorIterator& iter, int upward,
                           bool force_general, disort_state* ds,
                           disort_output* ds_out, at::Tensor* cuda_workspace);

#ifdef _WIN32
// PyTorch's private dispatch macros import custom stubs from its DLL on
// Windows.
void call_disort(c10::DeviceType device, at::TensorIterator& iter, int upward,
                 bool force_general, disort_state* ds, disort_output* ds_out,
                 at::Tensor* cuda_workspace);
#else
DECLARE_DISPATCH(disort_fn, call_disort);
#endif

}  // namespace at::native
