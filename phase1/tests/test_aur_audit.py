"""Tests for the pure logic in phase1/tools/aur-audit.py (no network/pacman).

conftest.py already puts phase1/tools on sys.path.
"""

import pytest

from aur_audit import (
    ATTACK_WINDOWS,
    cross_check,
    flag_install_windows,
    normalize,
)


# --- normalize -------------------------------------------------------------

def test_normalize_strips_bin_suffix():
    assert normalize("grayjay-bin") == "grayjay"


def test_normalize_strips_git_suffix():
    assert normalize("gimp-plugin-resynthesizer-git") == "gimp-plugin-resynthesizer"


def test_normalize_leaves_plain_names():
    assert normalize("ocenaudio") == "ocenaudio"


# --- cross_check -----------------------------------------------------------

def test_cross_check_exact_match():
    result = cross_check(["ocenaudio", "hexchat"], ["ocenaudio"])
    assert result["exact"] == ["ocenaudio"]
    assert result["fuzzy"] == []


def test_cross_check_fuzzy_match_via_bin_suffix():
    result = cross_check(["grayjay-bin"], ["grayjay"])
    assert result["exact"] == []
    assert result["fuzzy"] == ["grayjay-bin"]


def test_cross_check_fuzzy_match_via_git_suffix():
    result = cross_check(["boringssl-git"], ["boringssl"])
    assert result["exact"] == []
    assert result["fuzzy"] == ["boringssl-git"]


def test_cross_check_no_matches():
    result = cross_check(["ocenaudio", "debtap"], ["unrelated-package", "another"])
    assert result["exact"] == []
    assert result["fuzzy"] == []


def test_cross_check_empty_inputs():
    assert cross_check([], []) == {"exact": [], "fuzzy": []}


def test_cross_check_ignores_blank_lines():
    result = cross_check(["ocenaudio"], ["", "ocenaudio", "  "])
    assert result["exact"] == ["ocenaudio"]


# --- flag_install_windows --------------------------------------------------

def test_flag_install_inside_wave1():
    installed = {"evil-pkg": "Thu 11 Jun 2026 12:00:00 UTC"}
    flags = flag_install_windows(installed)
    assert len(flags) == 1
    assert flags[0][0] == "evil-pkg"
    assert flags[0][1] == "Wave 1"


def test_flag_install_inside_wave3():
    installed = {"sus2-pkg": "Tue 28 Jul 2026 13:02:46 BST"}
    flags = flag_install_windows(installed)
    assert len(flags) == 1
    assert flags[0][1] == "Wave 3"


def test_flag_install_inside_write_freeze():
    installed = {"sus-pkg": "Sat 08 Aug 2026 09:32:16 BST"}
    flags = flag_install_windows(installed)
    assert len(flags) == 1
    assert flags[0][1] == "Write freeze"


def test_no_flag_for_clean_install():
    installed = {"good-pkg": "Sat 10 Aug 2025 16:41:49 BST"}
    assert flag_install_windows(installed) == []


def test_no_flag_for_unparseable_date():
    installed = {"weird-pkg": "yesterday"}
    assert flag_install_windows(installed) == []


def test_windows_are_defined_and_sane():
    assert len(ATTACK_WINDOWS) >= 3
    for _, start, end in ATTACK_WINDOWS:
        assert start < end
