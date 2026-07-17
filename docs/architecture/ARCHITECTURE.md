# AI Hub Architecture

## Purpose

This document describes the logical architecture of AI Hub.

It explains how information flows through the platform, the responsibility of each layer, and the interaction between the Knowledge Platform, AI Runtime, and future services.

This document should remain implementation-independent whenever possible.

---

# High-Level Architecture

```text
                           OneDrive
                   (Source of Truth)
                              │
                              ▼
                     Knowledge Sync
                              │
                              ▼
                      01-Ingestion
                              │
                              ▼
                  Knowledge Compiler
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
   02-Curated                               03-Knowledge
        │                                           │
        └─────────────────────┬─────────────────────┘
                              ▼
                        AI Hub Platform
                              │
                              ▼
                         Omnigent Runtime
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
     Claude               ChatGPT               Future Agents