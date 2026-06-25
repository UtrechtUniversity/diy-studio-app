import pytest

import app_manager


def test_parse_app_info_reads_key_values_in_any_order():
    content = """
    branch=development
    version=v1.0.0-rc1
    """

    version, branch = app_manager.parse_app_info(content)

    assert version == "v1.0.0-rc1"
    assert branch == "development"


def test_parse_app_info_ignores_blank_lines_and_comments():
    content = """
    # local application metadata

    version=1.2.3
    branch=main
    """

    version, branch = app_manager.parse_app_info(content)

    assert version == "1.2.3"
    assert branch == "main"


def test_parse_app_info_supports_legacy_single_line_version():
    version, branch = app_manager.parse_app_info("dev-20260604.3")

    assert version == "dev-20260604.3"
    assert branch == "development"


def test_parse_stable_version_accepts_only_stable_tags():
    assert app_manager.parse_stable_version("v1.2.3") == [1, 2, 3]
    assert app_manager.parse_stable_version("1.2.3") == [1, 2, 3]
    assert app_manager.parse_stable_version("v1.0.0-rc1") is None
    assert app_manager.parse_stable_version("v1.0.0-beta1") is None


def test_split_version_rejects_prerelease_tags():
    with pytest.raises(ValueError):
        app_manager.split_version("v1.0.0-rc1")
