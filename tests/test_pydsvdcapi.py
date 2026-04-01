"""Basic tests for pydsvdcapi."""

from importlib.metadata import version

import pydsvdcapi


def test_version():
    """Test that the package version matches the installed metadata."""
    assert isinstance(pydsvdcapi.__version__, str)
    assert pydsvdcapi.__version__ == version("pydsvdcapi")
