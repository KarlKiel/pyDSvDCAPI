# pydsvdcapi

Python library for the digitalSTROM vDC API.

## Installation

```bash
pip install pydsvdcapi
```

## Usage

```python
import pydsvdcapi

print(pydsvdcapi.__version__)
```

## Development

Install the package in editable mode with all development extras:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest
```

Lint and format:

```bash
ruff check src/ tests/
ruff format src/ tests/
```

Type-check:

```bash
mypy src/pydsvdcapi
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide.
