#!/usr/bin/env python3
"""wiki-stale-check — 이벤트형 무효화 감지: 문서 updated 이후 sources 경로가 바뀌었는가.

유효기한(review_by)은 시간 경과형 만료만 잡는다. 실제 무효화는 근거 코드가 바뀌는 순간
일어나므로, 이 스크립트는 각 문서 frontmatter `sources`의 경로형 항목을 소속 repo의
git log와 대조해 "문서가 마지막으로 고쳐진 뒤 근거가 변경된 문서" 목록을 만든다.

판정은 사람이 한다 — 여기서는 재검토 대상 목록만 출력한다 (에이전트의 자율 stale 판정은
믿을 수 없다는 것이 도입 근거이므로, 자동 강등은 하지 않는다).

sources 분류:
- 경로형: repo 내 실존 경로, 또는 SUBREPOS 접두어(하위 repo가 있는 프로젝트) → git log 대조
- 소멸 경로: 경로처럼 보이고 git 이력은 있으나 현재 실존하지 않음 → 변경보다 강한 신호
- 자유 문자열: 공백·URL 포함("PR #142", "외부: arXiv …") → 대조 불가, 스킵 (불변 참조)

updated **당일** 커밋은 제외한다 — 그날의 코드 상태는 문서 작성자가 본 것으로 간주하고,
다음 날 00:00 이후 커밋만 센다.

사용: scripts/wiki-stale-check.py    # 보고서 출력 (분기 큐레이션·수동 실행)
종료 코드: 재검토 대상 있으면 1, 없으면 0.
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parent.parent
WIKI = HARNESS / "wiki"
# 이 repo 안에 clone된 독립 하위 repo가 있으면 디렉토리명을 추가한다 (예: "my-backend").
# 하위 repo가 없으면 빈 튜플로 둔다 — sources는 이 repo 내 경로로만 대조된다.
SUBREPOS = ()


def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1))
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


def classify(source):
    """(repo 루트, repo 내 상대경로) 또는 None(자유 문자열 — 대조 대상 아님)."""
    if not isinstance(source, str) or not source:
        return None
    if " " in source or "://" in source:
        return None
    for sub in SUBREPOS:
        if source == sub or source.startswith(sub + "/"):
            return HARNESS / sub, source[len(sub) + 1:] or "."
    return HARNESS, source


def git_log(repo, rel, since=None, limit=None):
    """해당 경로의 커밋 oneline 목록. repo가 git이 아니면 None."""
    cmd = ["git", "-C", str(repo), "log", "--oneline"]
    if since:
        cmd.append(f"--since={since.isoformat()}")
    if limit:
        cmd.append(f"-{limit}")
    cmd += ["--", rel]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [line for line in r.stdout.splitlines() if line.strip()]


def main():
    findings = []  # (문서 상대경로, updated, [설명 줄])
    warnings = []
    n_docs = n_paths = n_skipped = 0

    for path in sorted(WIKI.rglob("*.md")):
        fm = parse_frontmatter(path)
        if not fm or fm.get("type") in {"meta", "redirect", None}:
            continue
        loc = str(path.relative_to(HARNESS))
        updated = fm.get("updated")
        if isinstance(updated, datetime.datetime):
            updated = updated.date()
        if not isinstance(updated, datetime.date):
            warnings.append(f"{loc}: updated가 날짜가 아님 — 대조 불가")
            continue
        n_docs += 1
        cutoff = updated + datetime.timedelta(days=1)

        lines = []
        for source in fm.get("sources") or []:
            c = classify(source)
            if c is None:
                n_skipped += 1
                continue
            repo, rel = c
            if not repo.exists():
                warnings.append(f"{loc}: {source} — repo가 로컬에 없음, 스킵")
                continue
            n_paths += 1
            if not (repo / rel).exists():
                history = git_log(repo, rel, limit=1)
                if history:
                    lines.append(f"  ✗ 소멸: {source} (마지막 이력: {history[0]})")
                else:
                    warnings.append(f"{loc}: {source} — 실존하지 않고 git 이력도 없음 (오타?)")
                continue
            commits = git_log(repo, rel, since=cutoff)
            if commits is None:
                warnings.append(f"{loc}: {source} — git 조회 실패, 스킵")
            elif commits:
                lines.append(f"  ~ 변경: {source} — updated 이후 커밋 {len(commits)}건, 최신: {commits[0]}")

        if lines:
            findings.append((loc, updated, lines))

    print(f"wiki-stale-check: 문서 {n_docs}개 대조 (경로 {n_paths}·자유문자열 스킵 {n_skipped})")
    for w in warnings:
        print(f"! {w}")
    if not findings:
        print("wiki-stale-check: OK — 재검토 대상 없음")
        return 0
    print(f"\n재검토 대상 {len(findings)}건 — 판정(내용 유효 → updated 갱신 / 무효 → 수정·격리)은 사람이 한다:\n")
    for loc, updated, lines in findings:
        print(f"{loc} (updated {updated.isoformat()})")
        print("\n".join(lines))
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
