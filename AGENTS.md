# AGENTS.md — Engineering Agents Guide

This file is the entry point for **human contributors** and **coding agents** (Cursor, etc.).

**Read the full guide in your language:**

| Language | Guide |
| --- | --- |
| **English** | [en/AGENTS.md](en/AGENTS.md) |
| **日本語** | [ja/AGENTS.md](ja/AGENTS.md) |

---

## One-line summary

**The paramount requirement is the mission itself. Design and verification requirements can be revised under One Piece. Design and verification must follow physics and must not violate the mission.**

---

## Quick reference (layers)

```text
tools → scenario → environment → core
integrations/one_piece ← called from scenario
```

Do not import upward across layers. Do not put LLM or Persona logic in `environment/`.

After changes, run `pytest`.
