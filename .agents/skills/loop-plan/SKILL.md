---
name: loop-plan
description: Thin wrapper (AGENTS.md runtimes) for the loop planning skill. Use when the user wants to plan a task for the loop — run a spec interview (exhaust user-only blockers, pre-check the environment, predict risks) to lock requirements, then build the spec SSOT (requirements.md) and two state files (features.json/progress.md) under docs/projects/<slug>/. Also use before firing the harness's recurring re-run feature when the state files are missing. In unattended sessions (loop/headless, no user present) skip the interview and build only from the given spec text. Cycle execution itself is the harness's recurring re-run feature; individual knowledge recording is wiki-record's job. The canonical instructions live in the repo-root Claude skill and loop docs.
---

# loop 프로젝트 시공

이 래퍼는 본문을 복제하지 않는다. 아래 파일들을 **원본 규칙**으로 읽고 그대로 따른다.

- `.claude/skills/loop-plan/SKILL.md`
- `docs/loop/loop-guide.md`
- `docs/loop/state-files.md`

충돌하거나 빠진 내용이 있으면 위 경로들이 이긴다.
