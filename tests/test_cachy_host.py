import unittest
import os
from unittest.mock import patch, mock_open
from syntropia.cachy_host import CachyHostPossessor

class TestCachyHostPossessor(unittest.TestCase):
    def setUp(self):
        self.possessor = CachyHostPossessor()

    def test_detect_host_environment_defaults(self):
        env = self.possessor.detect_host_environment()
        self.assertIn("host_os", env)
        self.assertIn("kernel_cachyos", env)
        self.assertIn("bore_scheduler", env)
        self.assertIn("pipewire_active", env)
        self.assertIn("wine_installed", env)
        self.assertIn("yabridge_installed", env)
        self.assertIn("cpu_cores", env)

    @patch("os.path.exists")
    def test_detect_cachyos_environment(self, mock_exists):
        # Mock os-release and version paths
        def exists_side_effect(path):
            if path in ["/etc/os-release", "/proc/version"]:
                return True
            return False
        mock_exists.side_effect = exists_side_effect

        # Mock reading /etc/os-release and /proc/version
        os_release_data = "NAME=\"CachyOS\"\nID=cachyos\n"
        proc_version_data = "Linux version 6.9.1-cachyos-bore (gcc version 14.1.0) #1 SMP PREEMPT_DYNAMIC"

        with patch("builtins.open") as mock_file:
            # We side-effect the file reading based on filename
            def open_side_effect(filename, *args, **kwargs):
                if filename == "/etc/os-release":
                    return mock_open(read_data=os_release_data).return_value
                elif filename == "/proc/version":
                    return mock_open(read_data=proc_version_data).return_value
                raise FileNotFoundError()
            
            mock_file.side_effect = open_side_effect

            env = self.possessor.detect_host_environment()
            self.assertEqual(env["host_os"], "CachyOS")
            self.assertTrue(env["kernel_cachyos"])
            self.assertTrue(env["bore_scheduler"])

    def test_optimize_audio_performance(self):
        success, logs = self.possessor.optimize_audio_performance()
        self.assertTrue(success)
        self.assertIn("Tuning kernel watches", logs)
        self.assertIn("limits", logs)



    def test_configure_wine_yabridge(self):
        success, logs = self.possessor.configure_wine_yabridge("/path/to/my_vst.dll", is_vst3=True)
        self.assertTrue(success)
        self.assertIn("WINE_AUDIO_BACKGROUND=1", logs)
        self.assertIn("yabridgectl", logs)
        self.assertEqual(os.environ.get("WINE_AUDIO_BACKGROUND"), "1")

        # Clean up env
        os.environ.pop("WINE_AUDIO_BACKGROUND", None)

    def test_init_harden_security(self):
        success, logs = self.possessor.init_harden_security()
        self.assertTrue(success)
        self.assertIn("Landlock", logs)
        self.assertIn("seccomp", logs)

    def test_resource_sacrifice(self):
        self.assertFalse(self.possessor.sacrifice_active)
        
        # Test default (5%)
        self.possessor.start_resource_sacrifice()
        self.assertTrue(self.possessor.sacrifice_active)
        self.assertEqual(self.possessor.sacrifice_percentage, 5)
        self.possessor.stop_resource_sacrifice()
        
        # Test 50%
        self.possessor.start_resource_sacrifice(50)
        self.assertEqual(self.possessor.sacrifice_percentage, 50)
        self.possessor.stop_resource_sacrifice()

        # Test 0% (Chicken mode)
        self.possessor.start_resource_sacrifice(0)
        self.assertEqual(self.possessor.sacrifice_percentage, 0)
        self.possessor.stop_resource_sacrifice()

        # Test 100% (Unleashed)
        self.possessor.start_resource_sacrifice(100)
        self.assertEqual(self.possessor.sacrifice_percentage, 100)
        self.possessor.stop_resource_sacrifice()


if __name__ == "__main__":
    unittest.main()
