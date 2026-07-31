---
name: wiki-import
description: Thin wrapper (AGENTS.md runtimes) for the wiki import skill. Use when the user asks to migrate an existing batch of documents written outside the wiki (work logs, runbooks, maps, notes) into the wiki — inventory, placement/distillation interview, distillation mapping, sensitive-info scan, body approval, verified commit. Recording knowledge gained in the current session is wiki-record's job; leftover-draft disposal and audit is wiki-curate's. The canonical instructions live in the repo-root Claude skill and wiki schema files.
---

# 기존 문서 위키 이식

이 래퍼는 본문을 복제하지 않는다. 아래 두 파일을 **원본 규칙**으로 읽고 그대로 따른다.

- `.claude/skills/wiki-import/SKILL.md`
- `wiki/SCHEMA.md`

충돌하거나 빠진 내용이 있으면 위 경로들이 이긴다.
