# Security

Report vulnerabilities privately, by email to support@apexaiofficial.com, not in a public issue.
Include what you found, how to reproduce it, and the plugin version.

What the plugin promises:
- it starts only the pinned engine distribution, at its exact version, after verifying every
  installed file against its `RECORD` digests and the engine's package files against the build
  digest in `pin.json`, isolated from the environment (`python -I`);
- it exposes reads only: no tool grants authority, requests a remediation or runs a command;
- it holds no secret: the store path and evidence directory come from your environment.

The ApexAi DevOps engine is a separate, proprietary product that runs only in environments ApexAi
operates and is not distributed; report a vulnerability in DevOps itself the same way.
