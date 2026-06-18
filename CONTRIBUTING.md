# Contributing to pain001-mcp

Thank you for your interest in contributing to pain001-mcp. This guide covers
the development workflow and standards.

`pain001-mcp` is the Model Context Protocol (MCP) server of the **pain001
suite** - alongside the core [`pain001`](https://github.com/sebastienrousseau/pain001)
library and the [`pain001-lsp`](https://github.com/sebastienrousseau/pain001-lsp)
Language Server. It depends on `pain001` and exposes its public API as agent
tools, so most behaviour lives in the core library.

## Development Setup

### Prerequisites

- Python 3.10+
- [Poetry](https://python-poetry.org/docs/#installation)
- Git with SSH commit signing configured

### Setup

```bash
# Clone and install
git clone git@github.com:sebastienrousseau/pain001-mcp.git
cd pain001-mcp
poetry install

# Verify
poetry run pytest tests/ -q
```

The package depends on the core `pain001` library and `mcp`; both are
installed automatically by `poetry install`.

### On macOS

```bash
brew install python@3.12 poetry
```

### On Linux (Debian/Ubuntu)

```bash
sudo apt install python3 python3-pip
pip install poetry
```

### On WSL

```bash
sudo apt install python3 python3-pip
pip install poetry
# Ensure ~/.local/bin is in PATH
```

## Workflow

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
3. **Make changes** - follow the coding standards below
4. **Run tests**:
   ```bash
   poetry run pytest tests/ -v
   ```
5. **Run linters**:
   ```bash
   poetry run ruff check pain001_mcp/
   poetry run mypy pain001_mcp/
   poetry run black --check pain001_mcp/ tests/
   ```
6. **Sign and commit**:
   ```bash
   git commit -S -m "feat: add my feature"
   ```
7. **Push** and open a pull request

## Commit Signing (Required)

All commits **must** be signed with SSH or GPG.

### SSH Signing

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519
git config --global commit.gpgsign true
```

### Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add a new MCP tool wrapping a pain001 helper
fix: return an error payload instead of raising on bad input
docs: update README with the MCP client config
test: cover the validate_identifier tool
refactor: simplify the tool registration
```

## Coding Standards

- **Line length:** 79 characters (enforced by Black + Ruff)
- **Type hints:** Required on all public functions (mypy strict)
- **Docstrings:** Required on all public classes and functions
- **Tests:** Every new tool or change must include tests

## Testing

```bash
# Full suite
poetry run pytest tests/ -v

# Single file
poetry run pytest tests/test_mcp_server.py -v
```

## Pull Request Checklist

- [ ] All tests pass (`poetry run pytest`)
- [ ] Linters pass (`ruff check`, `mypy`, `black --check`)
- [ ] Commits are signed
- [ ] PR title follows conventional commit format
- [ ] New features include tests and documentation

## License

By contributing, you agree that your contributions will be licensed under
the [Apache License 2.0](LICENSE).
