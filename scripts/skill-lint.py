#!/usr/bin/env python3
"""skill-lint — 스킬(정본+래퍼)과 서브에이전트의 규격 검사.

규격 원본은 docs/agents-guide.md("스킬 규약 — 정본 + 래퍼" 절, §1~§7)와
docs/harness-guide.md("공용과 개인")·AGENTS.md(스킬 발동 선언 수칙)다.
이 스크립트는 그중 기계로 강제 가능한 구조만 검사한다 — 절차 내용의 옳고 그름은 보지 않는다.

스킬은 한 벌이 두 파일이다: `.claude/skills/<name>/SKILL.md`가 **정본**이고,
`.agents/skills/<name>/SKILL.md`는 정본 경로를 가리키기만 하는 **얇은 래퍼**다.
래퍼가 본문을 복제하기 시작하면 두 벌이 서로 어긋나므로 줄 수 상한으로 복제를 막는다.

검사 항목:
  1. 정본(.claude/skills/*/SKILL.md) — frontmatter의 name·description 필수,
     name이 디렉토리명과 일치, 본문에 발동 선언 문구('프로토콜 발동') 존재.
  2. 래퍼(.agents/skills/*/SKILL.md) — frontmatter의 name·description 필수,
     name이 디렉토리명과 일치, 본문이 대응 정본 경로를 참조,
     파일 20줄 이하(본문 복제 방지), 발동 선언 절이 **없어야** 함(선언은 정본의 몫).
  3. 쌍 — 정본에는 래퍼가, 래퍼에는 정본이 반드시 짝으로 있어야 한다.
  4. 서브에이전트(.claude/agents/*.md) — frontmatter의 name·description·tools 필수
     (tools는 allowlist이므로 생략 금지, agents-guide §2), name이 파일명과 일치.
     model은 선택 필드이므로 검사하지 않는다.

`my-` 접두사(개인 자산, .gitignore 대상)는 전부 건너뛴다 — 커밋되지 않으므로 규격 밖이다.

사용: scripts/skill-lint.py             # repo 전체 검사
      scripts/skill-lint.py --root DIR  # DIR을 repo 루트로 보고 검사 (픽스처 테스트용)
종료 코드: 위반 있으면 1, 없으면 0 (--root 경로가 없으면 2).
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

CANON_SKILLS = ".claude/skills"
WRAPPER_SKILLS = ".agents/skills"
AGENTS_DIR = ".claude/agents"

SKILL_FILE = "SKILL.md"
ACTIVATION = "프로토콜 발동"
WRAPPER_MAX_LINES = 20
PERSONAL_PREFIX = "my-"


def parse_frontmatter(path):
    """(frontmatter dict 또는 None, 본문 문자열)을 돌려준다. 본문은 frontmatter를 뺀 나머지.

    UTF-8로 못 읽는 파일은 (None, "")로 돌려 위반 한 줄로 처리한다 — 트레이스백 노출 방지.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None, ""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, text[m.end():]
    return fm, text[m.end():]


def check_frontmatter(fm, loc, required):
    """frontmatter 자체와 필수 필드를 검사해 오류 목록을 돌려준다."""
    if fm is None or not isinstance(fm, dict):
        return [f"✗ {loc}: frontmatter가 없거나 YAML이 깨짐"]
    errors = []
    for field in required:
        value = fm.get(field)
        if value is None or (isinstance(value, str) and not value.strip()) or value == []:
            errors.append(f"✗ {loc}: frontmatter에 {field} 없음(또는 비어 있음) — 필수 필드다")
    return errors


def skill_dirs(base):
    """base 바로 아래의 스킬 디렉토리 이름 목록 (my- 접두사 제외, 정렬)."""
    if not base.is_dir():
        return []
    return sorted(
        d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith(PERSONAL_PREFIX)
    )


def check_canonical(path, name, loc):
    """정본 SKILL.md 검사."""
    fm, body = parse_frontmatter(path)
    errors = check_frontmatter(fm, loc, ("name", "description"))
    if errors:
        return errors

    if str(fm.get("name")).strip() != name:
        errors.append(
            f"✗ {loc}: frontmatter name({fm.get('name')!r})이 디렉토리명({name!r})과 다름"
        )
    if f"{name} {ACTIVATION}" not in body:
        errors.append(
            f"✗ {loc}: 발동 선언 절 없음 — 본문에 \"{name} {ACTIVATION}합니다\" 문구가 있어야 한다"
        )
    return errors


def check_wrapper(path, name, loc):
    """래퍼 SKILL.md 검사 — 얇음(줄 수)·정본 참조·발동 선언 부재."""
    fm, body = parse_frontmatter(path)
    errors = check_frontmatter(fm, loc, ("name", "description"))
    if errors:
        return errors

    if str(fm.get("name")).strip() != name:
        errors.append(
            f"✗ {loc}: frontmatter name({fm.get('name')!r})이 디렉토리명({name!r})과 다름"
        )

    canon_ref = f"{CANON_SKILLS}/{name}/{SKILL_FILE}"
    if canon_ref not in body:
        errors.append(f"✗ {loc}: 정본 경로 참조 없음 — 본문에 `{canon_ref}`를 명시해야 한다")

    lines = len(path.read_text(encoding="utf-8").splitlines())
    if lines > WRAPPER_MAX_LINES:
        errors.append(
            f"✗ {loc}: {lines}줄 — 래퍼는 {WRAPPER_MAX_LINES}줄 이하여야 한다"
            " (본문은 정본에만 두고 여기서는 가리키기만 한다)"
        )

    if ACTIVATION in body:
        errors.append(
            f"✗ {loc}: 발동 선언 절이 있음 — 선언은 정본의 몫이고 래퍼에는 없어야 한다"
        )
    return errors


def check_agent(path, loc):
    """서브에이전트 문서 검사 — 필수 3필드와 name↔파일명 일치."""
    fm, _ = parse_frontmatter(path)
    errors = check_frontmatter(fm, loc, ("name", "description", "tools"))
    if errors:
        return errors

    stem = path.stem
    if str(fm.get("name")).strip() != stem:
        errors.append(f"✗ {loc}: frontmatter name({fm.get('name')!r})이 파일명({stem!r})과 다름")
    return errors


def lint(root):
    """루트 하나를 검사해 (오류 목록, 스킬 수, 에이전트 수)를 돌려준다."""
    errors = []
    canon_base = root / CANON_SKILLS
    wrapper_base = root / WRAPPER_SKILLS
    agents_base = root / AGENTS_DIR

    canon_names = skill_dirs(canon_base)
    wrapper_names = skill_dirs(wrapper_base)

    for name in canon_names:
        path = canon_base / name / SKILL_FILE
        loc = f"{CANON_SKILLS}/{name}/{SKILL_FILE}"
        if not path.is_file():
            errors.append(f"✗ {loc}: 파일 없음 — 스킬 디렉토리에는 {SKILL_FILE}이 있어야 한다")
            continue
        errors.extend(check_canonical(path, name, loc))

    for name in wrapper_names:
        path = wrapper_base / name / SKILL_FILE
        loc = f"{WRAPPER_SKILLS}/{name}/{SKILL_FILE}"
        if not path.is_file():
            errors.append(f"✗ {loc}: 파일 없음 — 스킬 디렉토리에는 {SKILL_FILE}이 있어야 한다")
            continue
        errors.extend(check_wrapper(path, name, loc))

    # 쌍 검사 — 한쪽만 있으면 런타임 하나에서 스킬이 사라진다.
    for name in canon_names:
        if name not in wrapper_names:
            errors.append(
                f"✗ {CANON_SKILLS}/{name}/: 짝이 되는 래퍼 없음"
                f" — {WRAPPER_SKILLS}/{name}/{SKILL_FILE}을 만들어야 한다"
            )
    for name in wrapper_names:
        if name not in canon_names:
            errors.append(
                f"✗ {WRAPPER_SKILLS}/{name}/: 짝이 되는 정본 없음"
                f" — 래퍼가 가리킬 {CANON_SKILLS}/{name}/{SKILL_FILE}이 존재해야 한다"
            )

    agent_paths = []
    if agents_base.is_dir():
        agent_paths = sorted(
            p for p in agents_base.glob("*.md") if not p.name.startswith(PERSONAL_PREFIX)
        )
    for path in agent_paths:
        errors.extend(check_agent(path, f"{AGENTS_DIR}/{path.name}"))

    return errors, len(canon_names), len(agent_paths)


def parse_args(argv):
    root_arg = None
    it = iter(argv)
    for a in it:
        if a == "--root":
            root_arg = next(it, None)
            if root_arg is None:
                print("skill-lint: --root 뒤에 디렉토리 경로가 필요합니다", file=sys.stderr)
                sys.exit(2)
        elif a.startswith("--root="):
            root_arg = a[len("--root="):]
    return root_arg


def main():
    root_arg = parse_args(sys.argv[1:])
    root = ROOT if root_arg is None else Path(root_arg)

    if not root.is_dir():
        print(f"skill-lint: 루트 디렉토리 없음: {root}", file=sys.stderr)
        return 2

    errors, skills, agents = lint(root)
    if errors:
        for e in errors:
            print(e)
        print(f"\nskill-lint: 위반 {len(errors)}건")
        return 1

    print(f"skill-lint: OK ({skills}개 스킬, {agents}개 에이전트)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
