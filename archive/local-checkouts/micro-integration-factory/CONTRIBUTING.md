# Contributing Guide

Thank you for contributing to Micro Integration Factory.

## Quick Start

```bash
# 1. Fork and clone the repo
git checkout -b feature/your-feature

# 2. Install dependencies
make install

# 3. Start services and run migrations
make compose-up && make migrate

# 4. Run tests
make test
```

## Development

**API**: `make dev-api` | **Web**: `npm run dev:web` | **All services**: `npm run dev` | **Lint**: `make lint` | **Format**: `make format`

Use pre-commit hooks: `pip install pre-commit && pre-commit install`

## Pull Requests

- ✅ Tests pass with 80%+ coverage
- ✅ Code formatted and linted
- ✅ Conventional Commits format (`feat:`, `fix:`, `docs:`, etc.)
- ✅ Documentation updated

## Security

Do not open public issues for security vulnerabilities or leaked credentials. Use GitHub Security Advisories or the private maintainer channel.

## Code of Conduct

Be respectful and inclusive. Harassment, discrimination, and inappropriate behavior are not tolerated. See [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) for details.

## License

Contributions are licensed under Apache 2.0.
