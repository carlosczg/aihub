# CLAUDE.md

This file defines the operating instructions for Claude Code and other implementation agents working inside AI Hub.

AI Hub is a personal knowledge platform. Its purpose is to capture, organize, enrich, and reuse professional knowledge from OneDrive documents, proposals, projects, portfolio assets, marketing content, research, and AI-assisted work.

The permanent asset is the knowledge platform.

AI models, agent frameworks, runtimes, and providers are interchangeable components and must never become the owners of the knowledge.

---

## Session bootstrap

At the beginning of every new session, before proposing or making changes:

1. Read `README.md`.
2. Read `CLAUDE.md`.
3. Read `docs/standards/PRINCIPLES.md`.
4. Read `docs/standards/OPERATING_MODEL.md`.
5. Read `docs/architecture/ARCHITECTURE.md`.
6. Read `docs/architecture/KNOWLEDGE_COMPILER.md`.
7. Read every applicable ADR under `docs/adr/`.
8. Read `00-System/Session/CURRENT_STATE.md` if it exists.
9. Inspect the actual repository structure and implementation status.
10. Summarize your understanding and the current state before modifying files.

Never assume that a previous conversation is available or still accurate.

Repository files and the current implementation are the source of truth.

---

## Core architecture

The high-level knowledge flow is:

```text
Official OneDrive sources
        |
        v
Knowledge Sync
        |
        v
01-Ingestion
        |
        v
Knowledge Compiler
        |
        +----------------------+
        |                      |
        v                      v
02-Curated              03-Knowledge
        |                      |
        +----------+-----------+
                   |
                   v
              AI Runtime
           Omnigent and agents