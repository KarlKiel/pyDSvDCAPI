"""Basic tests for pyDSvDCAPI."""

from importlib.metadata import version

import pyDSvDCAPI


def test_version():
    """Test that the package version matches the installed metadata."""
    assert isinstance(pyDSvDCAPI.__version__, str)
    assert pyDSvDCAPI.__version__ == version("pyDSvDCAPI")
