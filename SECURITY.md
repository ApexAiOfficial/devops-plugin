# Security

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/ApexAiOfficial/devops-plugin/security/advisories/new)
for this repository, not in a public issue. Include what you found, how to reproduce it, and the
plugin version.

What the plugin promises:
- it starts only the pinned engine distribution, at its exact version, after verifying every
  installed file against its `RECORD` digests, isolated from the environment (`python -I`);
- it exposes reads only: no tool grants authority, requests a remediation or runs a command;
- it holds no secret: the store path and evidence directory come from your environment.

The ApexAI DevOps engine is a separate, proprietary product.
