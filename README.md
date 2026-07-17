# AI Hub

## Vision

AI Hub is a personal knowledge platform designed to capture, organize, enrich, and reuse professional knowledge accumulated across services, proposals, projects, research, marketing content, and AI-assisted work.

The platform is designed so that knowledge remains independent from any specific AI model, provider, agent framework, or runtime.

Knowledge is the primary asset. Models and tools are replaceable components.

## Mission

Transform distributed documents and conversations into structured, traceable, reusable knowledge.

AI Hub is not intended to be only:

- A document repository.
- A chatbot.
- A vector database.
- An Omnigent project.
- A collection of prompts.

Its purpose is to become a durable knowledge platform that can be consumed by Claude, ChatGPT, Codex, GitHub Copilot, Databricks, and future AI agents.

## Objectives

AI Hub aims to:

1. Preserve original documents without modifying them.
2. Synchronize selected knowledge sources from OneDrive.
3. Create a controlled ingestion layer for documents.
4. Convert useful documents into normalized and searchable formats.
5. Generate technical metadata and maintain traceability.
6. Organize reusable knowledge by business domain and working context.
7. Enable multiple AI agents to consume the same knowledge base.
8. Reduce dependence on a single AI provider.
9. Support local execution first and future migration to Azure.
10. Continuously incorporate new knowledge generated through daily work.

## Knowledge Sources

The initial sources are:

- Portfolio of services.
- Commercial proposals.
- Customer projects.
- Marketing content.
- ChatGPT conversations and exports.
- Claude conversations and exports.
- GitHub Copilot outputs.
- Manually added documents.

The original files remain in their official locations.

OneDrive is currently the source of truth for professional documents.

## High-Level Architecture

```text
OneDrive and AI exports
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
              Omnigent
                   |
        +----------+----------+
        |          |          |
        v          v          v
      Claude     Codex     Future agents