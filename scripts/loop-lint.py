#!/usr/bin/env python3
"""loop-lint — loop 상태 파일 3종의 구조 검사 + 문구 휴리스틱.

규격 원본은 docs/loop/state-files.md. 이 스크립트는 그중 **기계로 강제 가능한 구조**와
**verify 문구의 기계 판정 가능한 표면**(추상어 잔존·실행 명령 부재·판정값 부재)을 검사한다.
문구 검사는 휴리스틱이라 표면만 본다 — 의미 충족(verify가 desc의 완료를 실제로 증명하는가)은
여전히 reviewer 게이트(loop-plan §5)의 몫이고, lint 통과는 그 게이트의 필요조건일 뿐이다.

`--root DIR`(기본 docs/projects) 바로 아래의 각 디렉토리를 프로젝트로 보고,
프로젝트마다 다음을 검사한다:
  1. 파일 3종 실존: requirements.md·features.json·progress.md
     (그 외 재료 파일 research-*.md 등은 무시한다).
  2. features.json — JSON 파싱, 최상위 키 정확히 {project, rule, features},
     project==디렉토리명, rule 비지 않은 문자열, features 비지 않은 배열,
     각 feature의 필수 5필드 {id, phase, desc, verify, passes}+선택 {blocked, verified_at_commit},
     id ^F\\d{3}$ 유일, phase 정수(bool 불가), desc·verify 비지 않은 문자열,
     passes bool, blocked 존재 시 resolvable:/human_blocked: 접두사,
     verified_at_commit은 hex 7~40자 커밋 해시이며 passes true면 필수·false면 금지.
     더해 비지 않은 verify는 state-files §4 3요건의 표면을 휴리스틱으로 본다 —
     추상 표현 잔존(요건 1) / 실행 명령 부재(요건 2) / 성공 판정값 부재(요건 3).
  3. requirements.md 헤딩: ## 목표 / ## 제약 / ## 완료 정의 / ## 제외 범위.
     더해 본문에 추상 표현이 잔존하는지 줄 단위로 본다(loop-plan §1 모호성 검출).
  4. progress.md 헤딩: ## 함정 목록 / ## 검증 인프라.

프로젝트가 하나도 없으면(디렉토리 부재 또는 빈 디렉토리) 통과로 본다 —
아직 loop 프로젝트를 시공하지 않은 새 repo의 정상 상태다.

사용: scripts/loop-lint.py               # docs/projects 전체 검사
      scripts/loop-lint.py --root DIR    # DIR 바로 아래를 프로젝트로 검사
종료 코드: 위반 있으면 1, 없으면 0.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = "docs/projects"

STATE_FILES = ("requirements.md", "features.json", "progress.md")

TOP_KEYS = {"project", "rule", "features"}
FEATURE_REQUIRED = {"id", "phase", "desc", "verify", "passes"}
FEATURE_OPTIONAL = {"blocked", "verified_at_commit"}
ID_RE = re.compile(r"^F\d{3}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
BLOCKED_PREFIXES = ("resolvable:", "human_blocked:")

REQUIREMENTS_HEADINGS = ("## 목표", "## 제약", "## 완료 정의", "## 제외 범위")
PROGRESS_HEADINGS = ("## 함정 목록", "## 검증 인프라")

# --- 문구 휴리스틱 (state-files §4 3요건의 표면) -------------------------------
# 아래 3개는 전부 휴리스틱 — 오탐이면 여기서 조정한다. 의미 판정은 loop-plan §5 리뷰 게이트의 몫.

# 휴리스틱 — 오탐이면 여기서 조정. 판정 기준 없는 추상 표현(부분 문자열 매치).
ABSTRACT_PATTERNS = (
    "정상 동작", "정상적으로", "잘 되는", "잘 동작", "깔끔하", "적당히",
    "적절히", "자연스럽", "안정적으로", "제대로", "문제없",
)

# 휴리스틱 — 오탐이면 여기서 조정. 실행 명령 토큰의 존재만 본다(명령의 옳고 그름은 안 본다).
# 좌우 경계로 한국어·식별자 안에 묻힌 토큰을 거른다: 좌측은 단어 문자·'.'·'/'·'-'가
# 앞서면 불일치(`pytest`의 test, `script.sh`의 sh 배제), 우측은 단어 문자·'-'가 뒤따르면 불일치.
# 한국어 음절도 \w라 "그grep다" 같은 문장 내 매몰은 경계에서 걸러진다.
_CMD_TOKENS = (
    "python3", "python", "pytest", "curl", "grep", "npm", "npx", "node",
    "cargo", "make", "bash", "sh", "git", "jq", "diff", "wc", "ls", "cat",
    "test", "docker", "kubectl",
)
CMD_RE = re.compile(
    r"(?<![\w./-])(?:" + "|".join(_CMD_TOKENS) + r")(?![\w-])"
    r"|(?<![\w./-])go\s+(?:test|run|build)(?![\w-])"  # `go test` 류는 두 토큰이라 별도
    r"|(?<![\w-])\./\S"  # ./scripts/foo.sh 같은 직접 실행
)

# 휴리스틱 — 오탐이면 여기서 조정. 성공 판정값(숫자 또는 판정어)의 존재만 본다.
PASS_VALUE_RE = re.compile(r"\d|통과|일치|없음|없어야|성공|실패|반환")


def nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def check_features_json(path, slug, disp):
    """features.json 구조 검사. 위반 사유 문자열 목록을 반환한다(disp는 표시 경로)."""
    errs = []
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        return [f"loop-lint: {disp} — JSON 파싱 실패: {e}"]

    if not isinstance(data, dict):
        return [f"loop-lint: {disp} — 최상위가 객체가 아님 (형식: {type(data).__name__})"]

    keys = set(data)
    for k in sorted(TOP_KEYS - keys):
        errs.append(f"loop-lint: {disp} — 최상위 필수 키 '{k}' 누락")
    for k in sorted(keys - TOP_KEYS):
        errs.append(f"loop-lint: {disp} — 최상위 미지 키 '{k}' (허용: {sorted(TOP_KEYS)})")

    if "project" in data and data["project"] != slug:
        errs.append(
            f"loop-lint: {disp} — project '{data['project']}'가 디렉토리명 '{slug}'와 불일치"
        )
    if "rule" in data and not nonempty_str(data["rule"]):
        errs.append(f"loop-lint: {disp} — rule은 비지 않은 문자열이어야 함")

    if "features" in data:
        features = data["features"]
        if not isinstance(features, list) or not features:
            errs.append(f"loop-lint: {disp} — features는 비지 않은 배열이어야 함")
        else:
            seen_ids = {}
            for i, feat in enumerate(features):
                errs.extend(check_feature(feat, i, disp, seen_ids))
    return errs


def check_feature(feat, index, disp, seen_ids):
    errs = []
    if not isinstance(feat, dict):
        return [f"loop-lint: {disp} — feature #{index}가 객체가 아님 (형식: {type(feat).__name__})"]

    fid = feat.get("id")
    label = fid if isinstance(fid, str) and fid else f"#{index}"

    fkeys = set(feat)
    for k in sorted(FEATURE_REQUIRED - fkeys):
        errs.append(f"loop-lint: {disp} — feature {label}: 필수 필드 '{k}' 누락")
    for k in sorted(fkeys - FEATURE_REQUIRED - FEATURE_OPTIONAL):
        errs.append(
            f"loop-lint: {disp} — feature {label}: 미지 필드 '{k}' "
            f"(허용: {sorted(FEATURE_REQUIRED | FEATURE_OPTIONAL)})"
        )

    if "id" in fkeys:
        if not isinstance(fid, str) or not ID_RE.match(fid):
            errs.append(f"loop-lint: {disp} — feature {label}: id는 ^F\\d{{3}}$ 형식이어야 함 (값: {fid!r})")
        else:
            if fid in seen_ids:
                errs.append(f"loop-lint: {disp} — feature {label}: id '{fid}' 중복")
            seen_ids[fid] = True

    if "phase" in fkeys:
        # bool은 int의 서브클래스라 별도로 거른다.
        if isinstance(feat["phase"], bool) or not isinstance(feat["phase"], int):
            errs.append(f"loop-lint: {disp} — feature {label}: phase는 정수여야 함 (값: {feat['phase']!r})")

    if "desc" in fkeys and not nonempty_str(feat["desc"]):
        errs.append(f"loop-lint: {disp} — feature {label}: desc는 비지 않은 문자열이어야 함")
    if "verify" in fkeys:
        # 빈 verify는 여기서 한 번만 보고하고, 문구 휴리스틱은 비지 않은 경우에만 돌린다.
        if not nonempty_str(feat["verify"]):
            errs.append(f"loop-lint: {disp} — feature {label}: verify는 비지 않은 문자열이어야 함")
        else:
            errs.extend(check_verify_text(feat["verify"], label, disp))

    if "passes" in fkeys and not isinstance(feat["passes"], bool):
        errs.append(f"loop-lint: {disp} — feature {label}: passes는 bool이어야 함 (값: {feat['passes']!r})")

    if "verified_at_commit" in fkeys:
        vac = feat["verified_at_commit"]
        if not isinstance(vac, str) or not COMMIT_RE.match(vac):
            errs.append(
                f"loop-lint: {disp} — feature {label}: verified_at_commit은 "
                f"커밋 해시(소문자 hex 7~40자)여야 함 (값: {vac!r})"
            )
    # passes ↔ verified_at_commit 동존 규칙 (state-files §3: 감사 앵커)
    if isinstance(feat.get("passes"), bool):
        has_vac = "verified_at_commit" in fkeys
        if feat["passes"] and not has_vac:
            errs.append(f"loop-lint: {disp} — feature {label}: passes가 true면 verified_at_commit 필수")
        if not feat["passes"] and has_vac:
            errs.append(
                f"loop-lint: {disp} — feature {label}: passes가 false면 verified_at_commit 금지 "
                f"(강등 시 함께 지운다)"
            )

    if "blocked" in fkeys:
        blocked = feat["blocked"]
        if not nonempty_str(blocked):
            errs.append(f"loop-lint: {disp} — feature {label}: blocked는 비지 않은 문자열이어야 함")
        elif not blocked.startswith(BLOCKED_PREFIXES):
            errs.append(
                f"loop-lint: {disp} — feature {label}: blocked는 'resolvable:' 또는 "
                f"'human_blocked:'로 시작해야 함 (값: {blocked!r})"
            )
    return errs


def check_verify_text(verify, label, disp):
    """verify 문구가 state-files §4 3요건의 표면을 만족하는지 휴리스틱으로 검사한다.

    표면만 본다 — verify가 desc의 완료를 실제로 증명하는가(의미 충족)는 보지 않는다.
    """
    errs = []
    for pat in ABSTRACT_PATTERNS:
        if pat in verify:
            errs.append(
                f"loop-lint: {disp} — feature {label}: verify에 추상 표현 '{pat}' — "
                f"관찰 가능한 판정으로 바꿔라 (state-files §4 요건 1)"
            )
    if not CMD_RE.search(verify):
        errs.append(
            f"loop-lint: {disp} — feature {label}: verify에 실행 명령이 없음 (state-files §4 요건 2)"
        )
    # 명령 토큰을 지운 뒤 판정값을 찾는다 — 'python3'의 3 같은 명령 속 숫자가 판정값으로 오인되지 않게.
    if not PASS_VALUE_RE.search(CMD_RE.sub(" ", verify)):
        errs.append(
            f"loop-lint: {disp} — feature {label}: verify에 성공 판정값(숫자·판정어)이 없음 "
            f"(state-files §4 요건 3)"
        )
    return errs


def check_abstract_lines(path, disp):
    """requirements.md 본문에서 판정 기준 없는 추상 표현을 줄 단위로 찾는다 (loop-plan §1)."""
    errs = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return [f"loop-lint: {disp} — 읽기 실패: {e}"]
    for lineno, line in enumerate(lines, 1):
        for pat in ABSTRACT_PATTERNS:
            if pat in line:
                errs.append(
                    f"loop-lint: {disp}:{lineno} — 추상 표현 '{pat}' 잔존 — "
                    f"확정 답변 또는 명시적 재량 선언으로 바꿔라 (loop-plan §1 모호성 검출)"
                )
    return errs


def check_headings(path, disp, required_headings):
    """행 시작 기준으로 필수 헤딩 라인이 각각 존재하는지 검사한다."""
    errs = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return [f"loop-lint: {disp} — 읽기 실패: {e}"]
    present = {ln.rstrip() for ln in lines}
    for heading in required_headings:
        if heading not in present:
            errs.append(f"loop-lint: {disp} — 필수 헤딩 '{heading}' 누락")
    return errs


def check_project(proj_dir, slug, prefix):
    """프로젝트 하나를 검사해 위반 사유 목록을 반환한다."""
    errs = []

    def disp(filename):
        return f"{prefix}{slug}/{filename}"

    missing = [f for f in STATE_FILES if not (proj_dir / f).is_file()]
    for f in missing:
        errs.append(f"loop-lint: {disp(f)} — 필수 파일 없음")

    if "features.json" not in missing:
        errs.extend(check_features_json(proj_dir / "features.json", slug, disp("features.json")))
    if "requirements.md" not in missing:
        errs.extend(check_headings(proj_dir / "requirements.md", disp("requirements.md"), REQUIREMENTS_HEADINGS))
        errs.extend(check_abstract_lines(proj_dir / "requirements.md", disp("requirements.md")))
    if "progress.md" not in missing:
        errs.extend(check_headings(proj_dir / "progress.md", disp("progress.md"), PROGRESS_HEADINGS))
    return errs


def parse_args(argv):
    root_arg = None
    it = iter(argv)
    for a in it:
        if a == "--root":
            root_arg = next(it, None)
            if root_arg is None:
                print("loop-lint: --root 뒤에 디렉토리 경로가 필요합니다", file=sys.stderr)
                sys.exit(2)
        elif a.startswith("--root="):
            root_arg = a[len("--root="):]
    return root_arg


def main():
    root_arg = parse_args(sys.argv[1:])
    if root_arg is None:
        root = ROOT / DEFAULT_ROOT
        # 기본 실행: 경로는 repo 루트 기준으로 표기한다.
        prefix = DEFAULT_ROOT + "/"
    else:
        root = Path(root_arg)
        # --root 사용 시 경로는 그 root 기준 상대로 표기한다.
        prefix = ""

    if not root.is_dir():
        # 기본 루트가 없는 건 아직 프로젝트를 시공하지 않은 정상 상태 — 통과로 본다.
        # --root를 명시했는데 없으면 사용자 오류이므로 종료 코드 2.
        if root_arg is None:
            print("loop-lint: 검사할 loop 프로젝트가 없습니다 (docs/projects 부재)")
            return 0
        print(f"loop-lint: 루트 디렉토리 없음: {root}", file=sys.stderr)
        return 2

    errors = []
    checked = 0
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        slug = child.name
        checked += 1
        errors.extend(check_project(child, slug, prefix))

    if errors:
        for e in errors:
            print(e)
        return 1

    if checked == 0:
        print("loop-lint: 검사할 loop 프로젝트가 없습니다")
        return 0
    print(f"loop-lint: {checked}개 프로젝트 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
