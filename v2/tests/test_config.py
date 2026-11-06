#!/usr/bin/env python3
"""Reject configuration errors which could select unavailable pins or break OTA."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_board import validate
from check_layout import validate_layout


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / "boards/legacy_n16r8.json").read_text())

    def test_forbidden_memory_pins(self):
        for gpio in (26, 34, 35, 36, 37):
            with self.subTest(gpio=gpio):
                candidate = copy.deepcopy(self.profile)
                candidate["pins"]["epd_sclk"] = gpio
                with self.assertRaises(ValueError):
                    validate(candidate)

    def test_duplicate_pin(self):
        self.profile["pins"]["sd_clk"] = self.profile["pins"]["epd_sclk"]
        with self.assertRaises(ValueError):
            validate(self.profile)

    def test_usb_repurposed(self):
        self.profile["pins"].pop("usb_dm")
        self.profile["pins"]["new_power_enable"] = 19
        with self.assertRaises(ValueError):
            validate(self.profile)

    def test_unreviewed_strap(self):
        self.profile["pins"]["epd_sclk"] = 45
        with self.assertRaises(ValueError):
            validate(self.profile)

    def test_input_only_gpio_as_output(self):
        self.profile["pins"]["epd_sclk"] = 46
        self.profile["acknowledged_strapping_roles"].append("epd_sclk")
        with self.assertRaises(ValueError):
            validate(self.profile)

    def test_four_bit_without_all_lanes(self):
        self.profile["sd_bus_width"] = 4
        del self.profile["pins"]["sd_d3"]
        with self.assertRaises(ValueError):
            validate(self.profile)

    def test_sd_required_signals_in_each_mode(self):
        for width in (1, 4):
            for signal in ("sd_clk", "sd_cmd", "sd_d0"):
                with self.subTest(width=width, signal=signal):
                    profile = copy.deepcopy(self.profile)
                    profile["sd_bus_width"] = width
                    del profile["pins"][signal]
                    with self.assertRaises(ValueError):
                        validate(profile)

    def test_profile_shape(self):
        with self.assertRaises(ValueError):
            validate([])
        self.profile["sd_bus_width"] = True
        with self.assertRaises(ValueError):
            validate(self.profile)

    def test_memory_upgrade_not_silent(self):
        self.profile["psram_bytes"] *= 2
        with self.assertRaises(ValueError):
            validate(self.profile)


class PartitionTests(unittest.TestCase):
    def assert_bad(self, old, new):
        content = (ROOT / "partitions.csv").read_text()
        self.assertIn(old, content)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partitions.csv"
            path.write_text(content.replace(old, new))
            with self.assertRaises(ValueError):
                validate_layout(path)

    def test_overlap(self):
        self.assert_bad("0x520000", "0x510000")

    def test_flash_overflow(self):
        self.assert_bad("0x1e0000", "0x2e0000")

    def test_missing_slot(self):
        self.assert_bad("ota_1,   app,  ota_1", "other,   app,  test")

    def test_invalid_ota_metadata(self):
        self.assert_bad("0xf000,   0x2000", "0xf000,   0x1000")


if __name__ == "__main__":
    unittest.main()
