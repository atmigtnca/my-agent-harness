---
name: handoff
description: Thin wrapper (AGENTS.md runtimes) for the handoff skill. Use when the user wants to hand the current work off to another agent, another session, or another machine — write a handoff prompt that points at portable anchors (repo, symbols, issue URLs, branch, exact error text) instead of local paths, and tells the receiver to independently re-verify before implementing. Not for delegating to a subagent inside this repo (that is the Worker brief). The canonical instructions live in the repo-root Claude skill.
---

# 세션 밖 작업 인계

이 래퍼는 본문을 복제하지 않는다. 아래 파일을 **원본 규칙**으로 읽고 그대로 따른다.

- `.claude/skills/handoff/SKILL.md`

충돌하거나 빠진 내용이 있으면 위 경로가 이긴다.
