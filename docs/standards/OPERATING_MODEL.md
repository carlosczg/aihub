# AI Hub Operating Model

## Purpose

This document defines the operating model for maintaining and evolving AI Hub.

It describes the responsibilities of the platform owner, implementation agents, runtime tools, and deterministic platform components.

---

## Roles

### Platform Owner

The platform owner is responsible for:

- Defining objectives and priorities.
- Approving architectural decisions.
- Authorizing file modifications and command execution.
- Reviewing generated knowledge and deliverables.
- Approving dependencies, integrations, and external services.
- Deciding when components move from experimental to stable.

The current platform owner is Carlos.

### Implementation Agent

Claude Code is currently the primary implementation agent.

Its responsibilities are:

- Read the platform documentation before working.
- Inspect the real repository state.
- Propose implementation plans.
- Implement only approved changes.
- Add and maintain tests.
- Report deviations, risks, and assumptions.
- Never modify source documents.

Claude is not the owner of the architecture or knowledge.

### MetaHarness

Omnigent is the current MetaHarness and execution runtime.

Its responsibilities include:

- Launching configured agents.
- Managing sessions.
- Providing controlled filesystem access.
- Coordinating future multi-agent work.

Omnigent does not store or own the knowledge platform.

### Knowledge Sync

Knowledge Sync is responsible for copying approved documents from official OneDrive sources into `01-Ingestion`.

It must remain:

- incremental;
- filtered by approved formats;
- deterministic;
- logged;
- non-destructive to source files.

### Knowledge Compiler

Knowledge Compiler is responsible for transforming the ingestion inventory into structured and traceable artifacts.

Its current V1 scope is limited to:

- scanning;
- technical metadata;
- SHA-256 hashing;
- document manifest generation;
- execution metadata.

---

## Standard session workflow

### 1. Open the project

Open the complete AI Hub root folder in VS Code.

The working folder must be the directory containing:

- `aihub.json`;
- `README.md`;
- `CLAUDE.md`;
- `00-System/`;
- `01-Ingestion/`;
- `docs/`.

### 2. Start Claude through Omnigent

From the AI Hub root:

```bash
omnigent claude