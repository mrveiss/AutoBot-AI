# Contributing to AutoBot

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

Before making your first commit, install pre-commit hooks to catch code quality issues locally:

```bash
# Install pre-commit (one-time setup)
pip install pre-commit

# Install the git hooks
pre-commit install

# Optional: Run hooks on all files to verify setup
pre-commit run --all-files
```

Pre-commit hooks automatically check your code for:
- **Black** formatting (line length: 120)
- **isort** import sorting
- **flake8** linting
- **autoflake** unused imports/variables
- **mypy** type checking
- **bandit** security issues
- Custom AutoBot-specific checks

These hooks run automatically before each commit, catching issues **before** they reach CI. This saves time and reduces CI failures.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/AutoBot-AI.git`
3. **Install pre-commit hooks** (see Development Setup above)
4. Create a branch: `git checkout -b feature/your-feature`
5. Make your changes
6. Commit: `git commit -m "feat: description of changes"`
   - Pre-commit hooks will run automatically and may auto-fix some issues
   - If hooks fail, review the output, fix the issues, and commit again
7. Push to your fork: `git push origin feature/your-feature`
8. Open a Pull Request

## Code of Conduct

Please treat all contributors with respect. We follow standard open-source norms:
- Be respectful and constructive
- No spam, harassment, or discrimination
- Focus on the code, not the person

## Guidelines

- Keep commits focused and descriptive
- Write tests for new features
- Update documentation as needed
- Follow existing code style

## Getting Help

- Open an issue for bugs or feature requests
- Use GitHub Discussions for questions and ideas
- Check existing issues/discussions before creating new ones

## Bounties

Some issues are marked with a `bounty` label. These are available for community contributions with financial rewards via [Polar.sh](https://polar.sh/mrveiss/AutoBot-AI). Check there for details.

## Good First Issues

Looking for something easy to start with? Check out issues tagged with `good-first-issue`.

Thank you for contributing! 🚀
