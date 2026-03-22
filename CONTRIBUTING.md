# Contributing to Jeprum

Thanks for your interest in contributing to Jeprum!

## Development Setup

```bash
git clone https://github.com/jeprum/jeprum.git
cd jeprum
uv sync
uv run pytest tests/ -v
```

## Making Changes

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run tests: `uv run pytest tests/ -v`
5. Commit with a descriptive message
6. Open a pull request

## Code Style

- Type hints on all functions
- Docstrings on all public classes and methods
- Tests for all new functionality
- Follow existing patterns in the codebase

## Reporting Issues

Open an issue at https://github.com/jeprum/jeprum/issues with:

- What you expected
- What happened
- Steps to reproduce
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
