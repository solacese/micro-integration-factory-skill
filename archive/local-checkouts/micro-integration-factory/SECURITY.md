# Security Policy

## Supported Versions

Security fixes target the `main` branch until the project starts publishing tagged releases.

## Reporting A Vulnerability

Do not open public issues for vulnerabilities, leaked credentials, or exploitable build-worker behavior.

Use GitHub Security Advisories for this repository or contact the maintainers privately. Include:

- affected commit or version
- reproduction steps
- impact and reachable attack surface
- logs with secrets redacted

## Secret Handling

- Never commit `.env` files or generated credentials.
- Rotate credentials that appear in chat, screenshots, logs, issues, or pull requests.
- Use AWS Secrets Manager or the encrypted settings store for production deployments.
- Restrict local worker access to trusted developer machines.
