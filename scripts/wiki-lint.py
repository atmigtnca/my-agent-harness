#!/usr/bin/env python3
"""wiki-lint — 위키 형식 검사 + index.md 재생성.

규칙 원본은 wiki/SCHEMA.md. 이 스크립트는 그중 기계로 강제 가능한 것만 검사한다:
frontmatter 필수 필드(summary 포함), type/status 조합, sources/tags,
troubleshooting의 symptoms, status↔verified_by 정합, 300줄 상한, redirect 링크 유효성,
문서 위치(지식 문서는 섹션 안, meta는 루트에만), config.sections 이름 규칙.
검사 통과 시 index.md를 frontmatter에서 재생성하고, review_by가 지난 문서의
본문 최상단에 만료 배너를 삽입한다(갱신되면 제거) — 배너는 review_by에서
결정론적으로 유도되는 기계 산출물이므로 손으로 편집하지 않는다.

재생성되는 index.md는 목록이자 운영 신호판이다 — 전체·방별 집계(검증됨/초안/만료),
~50문서 상한 경고, 만료 표시, 신뢰 순 정렬(SCHEMA "색인" 절).

이 위키는 하나다 — repo 하나에 위키 하나. 설정(섹션 목록·허용 태그)은
wiki/SCHEMA.md frontmatter의 `config`에서 읽는다:
    config:
      sections: []      # 비어 있으면 "시공 전" — 문서 기록 불가, /wiki-start로 시공
      tags: []          # 비어 있으면 태그 검사를 하지 않는다 (태그 자율)

사용: scripts/wiki-lint.py            # 검사 + index 재생성 + 만료 배너 갱신
      scripts/wiki-lint.py --check    # 검사만 (파일을 건드리지 않음)
종료 코드: 위반 있으면 1, 없으면 0.
"""
import datetime
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
INDEX = WIKI / "index.md"
SCHEMA = WIKI / "SCHEMA.md"

TYPES = {"knowledge", "troubleshooting", "decision", "redirect", "meta"}
STATUS = {
    "knowledge": {"draft", "verified"},
    "troubleshooting": {"draft", "verified"},
    "decision": {"proposed", "accepted", "superseded"},
}


def load_config():
    """SCHEMA.md frontmatter의 config에서 (허용 태그 집합, 섹션 목록, 설정 위반)을 읽는다.

    섹션이 빈 목록이면 "시공 전" 상태다 — 문서를 놓을 방이 없으므로 기록이 막힌다.
    섹션 이름은 곧 wiki/ 바로 아래 디렉토리 이름이므로 한 조각이어야 한다:
    슬래시·공백·빈 값·중복은 조용히 "실리지 않는 방"을 만들기 때문에 여기서 잡는다.
    """
    fm, _ = parse_frontmatter(SCHEMA)
    cfg = (fm or {}).get("config") or {}
    tags = {str(t) for t in (cfg.get("tags") or [])}
    sections = [str(s) for s in (cfg.get("sections") or [])]

    errors = []
    for s in sections:
        if not s.strip() or s != s.strip() or "/" in s or any(c.isspace() for c in s) or s.startswith("."):
            errors.append(
                f"SCHEMA config.sections: 섹션 이름 {s!r} 불가 — wiki/ 바로 아래 디렉토리 한 조각이어야 한다"
                " (슬래시·공백·빈 값·점 시작 금지)"
            )
    dups = sorted({s for s in sections if sections.count(s) > 1})
    if dups:
        errors.append(f"SCHEMA config.sections: 섹션 이름 중복 {dups} — 방 하나에 이름 하나")
    return tags, sections, errors


def expired_banner(fm):
    """review_by가 지난 문서에 있어야 할 배너 한 줄. 만료 아니면 None.

    에이전트는 만료 문서를 읽고도 전제를 의심하지 못하므로(STALE, arXiv 2605.06527)
    frontmatter 해석에 기대지 않고 본문 첫 줄에서 경고가 보이게 한다.
    """
    rb = fm.get("review_by")
    if isinstance(rb, datetime.datetime):
        rb = rb.date()
    if not isinstance(rb, datetime.date) or rb >= datetime.date.today():
        return None
    return (
        f"> ⚠️ 만료(review_by {rb.isoformat()} 경과): sources 대조 전까지 근거로 사용 금지"
        ' — 내용 확인 후 updated·review_by 갱신 (SCHEMA "유효기한" 절)'
    )


def banner_fix(fm, text):
    """만료 배너의 삽입/제거/갱신이 필요하면 (동작, 새 본문) 반환, 아니면 None."""
    want = expired_banner(fm)
    m = re.match(r"^(---\n.*?\n---\n)(.*)$", text, re.S)
    fm_text, body = m.group(1), m.group(2)
    bm = re.match(r"\n*(> ⚠️ 만료\([^\n]*)\n", body)
    have = bm.group(1) if bm else None
    if want == have:
        return None
    rest = (body[bm.end():] if bm else body).lstrip("\n")
    action = "삽입" if have is None else "제거" if want is None else "갱신"
    new_body = f"\n{want}\n\n{rest}" if want else f"\n{rest}"
    return action, fm_text + new_body


def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None, text
    try:
        return yaml.safe_load(m.group(1)), text
    except yaml.YAMLError:
        return None, text


def lint(allowed_tags, sections):
    errors = []
    docs = []  # (상대경로, frontmatter) — index 생성용
    metas = []  # (상대경로, frontmatter) — 루트 meta 개요 (SCHEMA·index 제외)
    banner_fixes = []  # (경로, 상대경로, 동작, 새 본문) — 만료 배너 삽입/제거/갱신

    for path in sorted(WIKI.rglob("*.md")):
        rel = path.relative_to(WIKI)
        loc = str(rel)
        fm, text = parse_frontmatter(path)

        if fm is None or not isinstance(fm, dict):
            errors.append(f"{loc}: frontmatter가 없거나 YAML이 깨짐")
            continue

        doc_type = fm.get("type")
        if doc_type not in TYPES:
            errors.append(f"{loc}: type '{doc_type}' 불허 (허용: {sorted(TYPES)})")
            continue
        if not fm.get("title"):
            errors.append(f"{loc}: title 누락")

        if doc_type == "meta":
            # meta는 루트에만 — 섹션 안 meta는 index에 실리지 않는 사각지대다 (SCHEMA "디렉토리 구조").
            if len(rel.parts) > 1:
                errors.append(
                    f"{loc}: meta 문서는 wiki/ 루트에만 둔다 — 섹션 안 meta는 index에 실리지 않아 아무도 열지 않는다"
                )
            elif path.name not in {"SCHEMA.md", "index.md"}:
                metas.append((rel, fm))  # 루트 개요 — 어느 방에도 없으니 index 머리에 링크를 싣는다
        else:
            if not sections:
                errors.append(
                    f"{loc}: 시공 전(config.sections 비어 있음)에는 문서를 기록할 수 없다 — /wiki-start로 시공하라"
                )
            elif rel.parts[0] not in sections:
                errors.append(
                    f"{loc}: 섹션 밖 위치 — index에 실리지 않는다 (허용 섹션: {sections}, 원본: SCHEMA config)"
                )

        if doc_type in STATUS:
            if fm.get("status") not in STATUS[doc_type]:
                errors.append(f"{loc}: status '{fm.get('status')}' 불허 (type={doc_type}, 허용: {sorted(STATUS[doc_type])})")
            if not fm.get("updated"):
                errors.append(f"{loc}: updated 누락")
            if not fm.get("sources"):
                errors.append(f"{loc}: sources 필수 (원본 포인터 없는 지식은 받지 않음)")
            if not fm.get("summary"):
                errors.append(f"{loc}: summary 누락 (index.md에 실리는 발견용 한 줄)")
            if doc_type == "troubleshooting" and not fm.get("symptoms"):
                errors.append(f"{loc}: symptoms 필수 (에러 메시지 원문·증상 키워드 목록 — grep 적중용)")
            if allowed_tags:
                tags = fm.get("tags") or []
                if not tags or not set(map(str, tags)) <= allowed_tags:
                    errors.append(f"{loc}: tags 누락 또는 불허 값 {tags} (허용: {sorted(allowed_tags)})")
            if doc_type != "decision" and not fm.get("review_by"):
                errors.append(f"{loc}: review_by 필수 (유효기한 — SCHEMA의 유형별 기본값)")
            rb = fm.get("review_by")
            if rb is not None and not isinstance(rb, (datetime.date, datetime.datetime)):
                errors.append(f"{loc}: review_by가 날짜가 아님: {rb!r} (YYYY-MM-DD, 따옴표 없이)")
            fix = banner_fix(fm, text)
            if fix:
                banner_fixes.append((path, loc, *fix))
            status = fm.get("status")
            if status in {"verified", "accepted"} and not fm.get("verified_by"):
                errors.append(f"{loc}: {status}인데 verified_by 누락 (승인자 없는 검증은 없다)")
            if status in {"draft", "proposed"} and fm.get("verified_by"):
                errors.append(f"{loc}: {status}인데 verified_by 존재 (미검증 문서에 승인자 표기 불가)")

        # 300줄 상한은 지식 문서의 예산이다. SCHEMA.md만 예외 — 코어 규칙 문서이고,
        # 시공이 채우는 규약 분량을 상한이 막으면 첫 시공 커밋 자체가 불가능해진다.
        n_lines = text.count("\n") + 1
        if path != SCHEMA and n_lines > 300:
            errors.append(f"{loc}: {n_lines}줄 — 300줄 상한 초과 (분할보다 삭제·압축 먼저)")

        # 내부 링크 전수 검사 — 삭제가 다른 문서의 참조를 부수면 pre-commit에서 잡힌다.
        # index.md는 제외: 기계 생성이라 삭제 직후 stale 링크가 정상이며,
        # 검사하면 "삭제 → lint 실패 → index 재생성 불가" 데드락이 된다.
        body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
        # 코드 블록·인라인 코드 안의 링크 예시는 검사 대상이 아니다
        body = re.sub(r"```.*?```", "", body, flags=re.S)
        body = re.sub(r"`[^`\n]*`", "", body)
        links = re.findall(r"\]\(([^)]+)\)", body)
        if path != INDEX:
            for target in links:
                bare = target.split("#")[0]
                if not bare or target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                if not (path.parent / bare).resolve().exists() and not (WIKI / bare).resolve().exists():
                    errors.append(f"{loc}: 깨진 링크: {target}")
        if doc_type == "redirect" and not links:
            errors.append(f"{loc}: redirect인데 대상 링크가 없음")

        if doc_type != "meta":
            docs.append((rel, fm))

    return errors, docs, metas, banner_fixes


# index는 사람이 훑는 표면이므로 status를 한국어로 표시한다 (frontmatter 값 자체는 영문 유지)
STATUS_LABEL = {
    "draft": "초안(미검증)",
    "verified": "검증됨",
    "proposed": "제안됨",
    "accepted": "채택됨",
    "superseded": "대체됨",
}

TRUSTED = {"verified", "accepted"}
UNTRUSTED = {"draft", "proposed"}
# 방 안 정렬은 신뢰 순 → 제목 순이다: 먼저 읽어야 할 것은 믿을 수 있는 문서고,
# 바닥에 몰린 초안 덩어리가 그대로 큐레이션 대기열로 보여야 한다 (SCHEMA "색인" 절).
STATUS_RANK = {"verified": 0, "accepted": 0, "draft": 1, "proposed": 1, "superseded": 2}
DOC_LIMIT = 50  # SCHEMA "크기 상한" — 넘으면 경고만 단다 (커밋을 막지는 않는다)


def entry_key(entry):
    rel, fm = entry
    return (STATUS_RANK.get(fm.get("status"), 3), str(fm.get("title") or rel.name), rel.as_posix())


def tally_line(entries):
    """운영 신호 한 줄 — 문서 수와 검증됨·초안·만료 건수."""
    ok = sum(1 for _, fm in entries if fm.get("status") in TRUSTED)
    todo = sum(1 for _, fm in entries if fm.get("status") in UNTRUSTED)
    expired = sum(1 for _, fm in entries if expired_banner(fm))
    line = f"> 문서 {len(entries)} · 검증됨 {ok} · 초안 {todo}"
    if expired:
        line += f" · ⚠️ 만료 {expired}"
    return line


def build_index(docs, metas, sections):
    # updated 스탬프는 넣지 않는다 — 날짜만 바뀌어도 index가 dirty가 되어
    # 자동화가 잡음 커밋을 만든다. 재생성은 내용에 대해 멱등이어야 한다.
    lines = [
        "---",
        "type: meta",
        "title: 위키 색인",
        "---",
        "",
        "# 색인",
        "",
        "> ⚠️ 이 파일은 wiki-lint가 frontmatter에서 재생성한다. 손으로 편집하지 말 것.",
    ]
    if not sections:
        lines += ["", "> 이 위키는 아직 **시공 전**이다 — `/wiki-start`가 상황을 인터뷰해 섹션·규약을 설계한다."]
    else:
        lines += ["", tally_line(docs)]
        if len(docs) > DOC_LIMIT:
            lines.append(f"> ⚠️ ~{DOC_LIMIT}문서 상한 초과 — 늘어나기만 하는 위키는 실패한 위키다 (SCHEMA \"크기 상한\")")
    for rel, fm in sorted(metas, key=entry_key):
        # 루트 meta 개요는 어느 방에도 없다 — 여기서 링크하지 않으면 색인에서 아예 빠진다.
        lines += ["", f"개요: [{fm.get('title', rel.name)}]({rel.as_posix()})"]
    for section in sections:
        lines += ["", f"## {section}/"]
        entries = [d for d in docs if d[0].parts[0] == section]
        if not entries:
            lines += ["", "(비어 있음)"]
            continue
        lines += ["", tally_line(entries), ""]
        for rel, fm in sorted(entries, key=entry_key):
            status = fm.get("status")
            suffix = f" — {STATUS_LABEL.get(status, status)}" if status else ""
            if expired_banner(fm):
                suffix += " · ⚠️ 만료"
            if fm.get("summary"):
                suffix += f" · {fm['summary']}"
            lines.append(f"- [{fm.get('title', rel.name)}]({rel.as_posix()}){suffix}")
    return "\n".join(lines) + "\n"


def sync_index(path, new_text, check_only):
    """index 파일을 재생성 결과와 일치시킨다. check_only면 불일치를 위반으로 보고(True 반환)."""
    rel = path.relative_to(WIKI).as_posix()
    if not path.exists():
        if check_only:
            print(f"✗ {rel}가 없음 (scripts/wiki-lint.py 실행으로 생성)")
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
        print(f"wiki-lint: {rel} 생성")
        return False
    if path.read_text(encoding="utf-8") != new_text:
        if check_only:
            print(f"✗ {rel}가 최신이 아님 (scripts/wiki-lint.py 실행으로 재생성)")
            return True
        path.write_text(new_text, encoding="utf-8")
        print(f"wiki-lint: {rel} 재생성")
    return False


def main():
    check_only = "--check" in sys.argv
    allowed_tags, sections, cfg_errors = load_config()
    if not sections:
        print("wiki-lint: 시공 전 상태 (config.sections 비어 있음) — /wiki-start로 설계·시공하라")
    errors, docs, metas, banner_fixes = lint(allowed_tags, sections)
    errors = cfg_errors + errors

    for e in errors:
        print(f"✗ {e}")
    if errors:
        print(f"\nwiki-lint: 위반 {len(errors)}건")
        return 1

    if banner_fixes:
        if check_only:
            for _, loc, action, _ in banner_fixes:
                print(f"✗ {loc}: 만료 배너 {action} 필요 (scripts/wiki-lint.py 실행으로 갱신)")
            return 1
        for path, loc, action, new_text in banner_fixes:
            path.write_text(new_text, encoding="utf-8")
            print(f"wiki-lint: 만료 배너 {action} — {loc}")

    if sync_index(INDEX, build_index(docs, metas, sections), check_only):
        return 1

    print(f"wiki-lint: OK ({len(docs)}개 문서)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
