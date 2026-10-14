"""CUDA discovery tests that run without NVIDIA hardware."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pixydeck import cuda  # noqa: E402


class FakeRuntime:
    def getDeviceCount(self):
        return 1

    def getDeviceProperties(self, _index):
        return {"name": b"Test NVIDIA"}


class FakeCuda:
    runtime = FakeRuntime()


class FakeCuPy:
    cuda = FakeCuda()


class CudaDiscoveryTest(unittest.TestCase):
    def test_missing_cupy_is_cpu_only(self):
        with mock.patch.object(cuda, "cp", None):
            self.assertFalse(cuda.cuda_available())
            self.assertIsNone(cuda.cuda_device_name())

    def test_device_is_found_and_named(self):
        with mock.patch.object(cuda, "cp", FakeCuPy()), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PIXYDECK_DISABLE_CUDA", None)
            self.assertTrue(cuda.cuda_available())
            self.assertEqual(cuda.cuda_device_name(), "Test NVIDIA")

    def test_cuda_can_be_disabled_for_diagnostics(self):
        with mock.patch.object(cuda, "cp", FakeCuPy()), \
                mock.patch.dict(os.environ, {"PIXYDECK_DISABLE_CUDA": "1"}):
            self.assertFalse(cuda.cuda_available())

    def test_driver_error_falls_back(self):
        fake = FakeCuPy()
        fake.cuda.runtime.getDeviceCount = mock.Mock(side_effect=RuntimeError("driver"))
        with mock.patch.object(cuda, "cp", fake):
            self.assertFalse(cuda.cuda_available())


if __name__ == "__main__":
    unittest.main()
