#pragma once

// torch
#include <ATen/TensorIterator.h>
#include <ATen/native/DispatchStub.h>

// disort
#include <cdisort213/cdisort.hpp>

#if defined(_WIN32) && defined(PYDISORT_WITH_CUDA)
namespace disort {
void call_disort_cuda(at::TensorIterator& iter, int upward, bool force_general,
                      disort_state* ds, disort_output* ds_out,
                      at::Tensor* cuda_workspace);
}  // namespace disort
#endif

namespace at::native {

using disort_fn = void (*)(at::TensorIterator& iter, int upward,
                           bool force_general, disort_state* ds,
                           disort_output* ds_out, at::Tensor* cuda_workspace);

#ifdef _WIN32
// DECLARE_DISPATCH and REGISTER_* use TORCH_API (dllimport here), so MSVC
// cannot define this library's stub and CPU registrations.
void call_disort(c10::DeviceType device, at::TensorIterator& iter, int upward,
                 bool force_general, disort_state* ds, disort_output* ds_out,
                 at::Tensor* cuda_workspace);
#else
DECLARE_DISPATCH(disort_fn, call_disort);
#endif

}  // namespace at::native
