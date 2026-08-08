# ADR 0001: Public vs Private

## Context

Agent OS is designed as a generalized orchestration backbone. It needs to serve as a robust, open-source framework while also functioning as the foundation for highly specialized, private workflows, client deployments, and domain-specific knowledge bases.

If we mix private constraints, proprietary prompts, or client-specific logic into the public repository, we compromise the framework's general utility and risk exposing sensitive context.

## Decision

We strictly enforce a boundary between the public core and private extensions:

- **Public Repository:** Contains generic primitives, protocol definitions, reference implementations, and security boundaries. It serves as a "technical sales asset" and an open-source backbone.
- **Private Deployments:** Contain client-specific logic, domain specialization, private memory (vaults), proprietary prompts, and credentials.

### The 5-Question Decision Test

When evaluating whether code or documentation belongs in the public repo, we ask:
1. Is this a generic primitive applicable to any agent system?
2. Does this expose any private infrastructure or internal codenames?
3. Is it a reference implementation necessary to demonstrate the core protocols?
4. Does this contain domain-specific heuristics?
5. Would this be useful to a community user deploying their own instance?

If it relies on private context or domain heuristics, it stays out.

### Dependency Rule

Private extensions and client implementations may depend on the public core, but they **must not monkey-patch** core functionality. All customizations must be achieved through the provided `ConnectorRegistry`, `BackendRegistry`, and explicit extension points.

## Consequences

- The public repository remains clean, focused, and legally safe.
- We must maintain stable extension APIs (connectors, tools, backends) to ensure private deployments can operate without modifying core framework code.
- Test fixtures in the public repository must use synthetic data, avoiding any accidental inclusion of real private memory.
