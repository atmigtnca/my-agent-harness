#!/usr/bin/env bash
# wiki-e2e.sh — 위키 lint 게이트의 E2E 회귀 스위트 (위키는 하나, repo 하나에 위키 하나).
#
# 흐름: 시공 전 → 시공(섹션 채움) → 문서 기록 → lint 통과 → index 재생성·멱등·신뢰 순 정렬
#       → 위반 케이스 거부(필수 필드 누락·미허용 태그·섹션 밖 위치·섹션 안 meta·섹션 이름 규칙 2종
#         ·300줄 상한, 단 SCHEMA.md는 예외) → 만료 표시 삽입·제거 → ~50문서 상한 경고.
# 단계마다 PASS/FAIL을 찍고 하나라도 FAIL이면 exit 1.
#
# **원본 워킹트리는 절대 건드리지 않는다.** 검사는 임시 디렉토리의 사본에서만 이뤄진다:
# wiki/SCHEMA.md와 scripts/wiki-lint.py만 복사해 최소 픽스처를 만들고, lint는 그 사본을
# 자기 루트로 인식한다(ROOT = 스크립트의 상위의 상위). git·커밋·훅은 호출하지 않는다.
#
# 규약 원본: wiki/SCHEMA.md. 게이트 구현: scripts/wiki-lint.py.
set -uo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd -P; })"
cd "$ROOT" || { echo "FAIL: repo 루트 진입 불가: $ROOT"; exit 1; }

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }

# 시작 시점의 워킹트리 상태 — 마지막 단계에서 불변을 확인한다.
START_STATUS="$(git status --porcelain 2>/dev/null)"

# ── 임시 사본 준비 ──
TMP="$(mktemp -d "${TMPDIR:-/tmp}/wiki-e2e.XXXXXX")" || { echo "FAIL: 임시 디렉토리 생성 실패"; exit 1; }
trap 'rm -rf "$TMP"' EXIT INT TERM

mkdir -p "$TMP/scripts" "$TMP/wiki"
cp "$ROOT/scripts/wiki-lint.py" "$TMP/scripts/wiki-lint.py"
cp "$ROOT/wiki/SCHEMA.md" "$TMP/wiki/SCHEMA.md"

LINT="$TMP/scripts/wiki-lint.py"
SCHEMA="$TMP/wiki/SCHEMA.md"
INDEX="$TMP/wiki/index.md"
DOC="$TMP/wiki/knowledge/e2e-doc.md"
VDOC="$TMP/wiki/knowledge/z-verified.md"   # 제목·파일명이 DOC보다 뒤 — 신뢰 순 정렬에서만 위에 온다

# lint 실행 (mutating 모드 — index 재생성·만료 배너 갱신). 출력을 LINT_OUT에 캡처한다:
# 거부 단계가 "기대한 사유의 exit 1"인지까지 확인해 무관한 실패의 오탐 PASS를 막는다.
LINT_OUT=""
run_lint() { LINT_OUT="$(python3 "$LINT" 2>&1)"; }

# SCHEMA frontmatter config 설정 — 사본에만 적용한다. $1=섹션 YAML 목록, $2=태그 YAML 목록.
set_cfg() {
  python3 - "$SCHEMA" "$1" "$2" <<'PY'
import re, sys
path, secs, tags = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
text = re.sub(r"^(\s*)sections:.*$", lambda m: f"{m.group(1)}sections: {secs}", text, count=1, flags=re.M)
text = re.sub(r"^(\s*)tags:.*$", lambda m: f"{m.group(1)}tags: {tags}", text, count=1, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
PY
}

# 정합 문서 한 편을 쓴다. $1=경로, $2=review_by, $3=태그 줄(빈 문자열이면 생략)
write_doc() {
  mkdir -p "$(dirname "$1")"
  {
    echo "---"
    echo "type: knowledge"
    echo "title: E2E 임시 문서"
    echo "summary: wiki-e2e.sh가 lint 게이트 검증용으로 만든 임시 문서"
    echo "status: draft"
    echo "updated: $(date +%F)"
    echo "review_by: $2"
    [ -n "${3:-}" ] && echo "$3"
    echo "sources:"
    echo "  - scripts/wiki-e2e.sh"
    echo "---"
    echo ""
    echo "# E2E 임시 문서"
    echo ""
    echo "이 문서는 임시 사본에만 존재하며 스위트 종료 시 사본과 함께 사라진다."
  } > "$1"
}

# 검증됨 문서 한 편. $1=경로, $2=review_by. 제목("Z …")과 파일명을 초안 문서보다 뒤로 지어,
# index에서 이 문서가 위에 오는 것은 "신뢰 순 정렬"일 때뿐이게 만든다 (파일명·제목 순이면 아래).
write_verified_doc() {
  mkdir -p "$(dirname "$1")"
  {
    echo "---"
    echo "type: knowledge"
    echo "title: Z 검증 문서"
    echo "summary: 신뢰 순 정렬 확인용 검증됨 문서"
    echo "status: verified"
    echo "verified_by: 홍길동"
    echo "updated: $(date +%F)"
    echo "review_by: $2"
    echo "sources:"
    echo "  - scripts/wiki-e2e.sh"
    echo "---"
    echo ""
    echo "# Z 검증 문서"
  } > "$1"
}

# 루트 meta 개요 한 편. $1=경로 (섹션 안에 쓰면 거부되어야 한다)
write_meta() {
  mkdir -p "$(dirname "$1")"
  printf -- '---\ntype: meta\ntitle: E2E 임시 개요\n---\n\n# E2E 임시 개요\n' > "$1"
}

FUTURE="$(date -d '+1 year' +%F 2>/dev/null || date -v+1y +%F 2>/dev/null || date +%F)"
PAST="$(date -d '-1 day' +%F 2>/dev/null || date -v-1d +%F 2>/dev/null || echo 2000-01-01)"

# ── 단계 1: 시공 전 — 문서가 없으면 lint 통과 + index 생성, 안내 문구 노출 ──
set_cfg "[]" "[]"
if run_lint && [ -f "$INDEX" ] && echo "$LINT_OUT" | grep -q "시공 전"; then
  pass "step1 시공 전 — lint exit 0, index.md 생성, '시공 전' 안내 출력"
else
  fail "step1 시공 전 — lint exit 0 / index.md 생성 / 안내 출력 중 하나 이상 불충족: $LINT_OUT"
fi

# ── 단계 2: 시공 전 기록 거부 — 방이 없으면 문서를 받지 않는다 ──
write_doc "$DOC" "$FUTURE"
if run_lint; then
  fail "step2 시공 전 기록 거부 — 섹션이 비었는데 lint가 통과(exit 0)함"
elif echo "$LINT_OUT" | grep -q "문서를 기록할 수 없다"; then
  # 사유 문자열은 위반 항목의 것이어야 한다 — main()의 "시공 전 상태" 안내 한 줄로는 PASS되지 않는다.
  pass "step2 시공 전 기록 거부 — lint exit 1 + 시공 전 기록 불가 사유 적중"
else
  fail "step2 시공 전 기록 거부 — exit 1이지만 사유가 시공 전 거부가 아님: $LINT_OUT"
fi

# ── 단계 3: 시공 → 문서가 통과하고 index에 실린다 (집계 신호 + 신뢰 순 정렬) ──
set_cfg "[knowledge, troubleshooting, decisions]" "[]"
write_verified_doc "$VDOC" "$FUTURE"
if run_lint && grep -q "^## knowledge/$" "$INDEX" && grep -q "e2e-doc.md" "$INDEX" &&
   grep -q "^> 문서 2 · 검증됨 1 · 초안 1" "$INDEX"; then
  FIRST_ENTRY="$(grep -m1 '^- \[' "$INDEX")"
  case "$FIRST_ENTRY" in
    *"Z 검증 문서"*)
      pass "step3 시공 후 기록 — lint exit 0, index에 섹션·문서 링크·집계 반영 + 검증됨이 초안보다 위" ;;
    *)
      fail "step3 신뢰 순 정렬 — index의 첫 문서 줄이 검증됨이 아니다 (파일명·제목 순으로 밀림): $FIRST_ENTRY" ;;
  esac
else
  fail "step3 시공 후 기록 — lint exit 0 / index 섹션 / 문서 링크 / 집계 한 줄 중 하나 이상 불충족: $LINT_OUT"
fi

# ── 단계 4: index 재생성 멱등 — 두 번 돌려도 내용이 같아야 한다 ──
BEFORE="$(cat "$INDEX")"
run_lint
if [ "$BEFORE" = "$(cat "$INDEX")" ]; then
  pass "step4 index 멱등 — 재실행해도 index.md 내용 동일"
else
  fail "step4 index 멱등 — 재실행이 index.md를 바꿈 (자동화가 잡음 커밋을 만든다)"
fi

# ── 단계 5: 위반 거부 A — frontmatter 필수 필드(summary) 누락 ──
sed -i.bak '/^summary: /d' "$DOC" && rm -f "$DOC.bak"
if run_lint; then
  fail "step5 필수 필드 누락 거부 — summary가 없는데 lint 통과(exit 0)함"
elif echo "$LINT_OUT" | grep -q "summary 누락"; then
  pass "step5 필수 필드 누락 거부 — lint exit 1 + 'summary 누락' 사유 적중"
else
  fail "step5 필수 필드 누락 거부 — exit 1이지만 사유가 summary 누락이 아님: $LINT_OUT"
fi
write_doc "$DOC" "$FUTURE"

# ── 단계 6: 위반 거부 B — config.tags 밖의 태그 ──
set_cfg "[knowledge, troubleshooting, decisions]" "[infra]"
write_doc "$DOC" "$FUTURE" "tags: [nope]"
if run_lint; then
  fail "step6 미허용 태그 거부 — 허용 목록 밖 태그인데 lint 통과(exit 0)함"
elif echo "$LINT_OUT" | grep -q "tags 누락 또는 불허 값"; then
  pass "step6 미허용 태그 거부 — lint exit 1 + 'tags 누락 또는 불허 값' 사유 적중"
else
  fail "step6 미허용 태그 거부 — exit 1이지만 사유가 태그 위반이 아님: $LINT_OUT"
fi
set_cfg "[knowledge, troubleshooting, decisions]" "[]"
write_doc "$DOC" "$FUTURE"

# ── 단계 7: 위반 거부 C — 섹션 밖 위치 ──
STRAY="$TMP/wiki/nowhere/e2e-stray.md"
write_doc "$STRAY" "$FUTURE"
if run_lint; then
  fail "step7 섹션 밖 위치 거부 — 허용 섹션 밖 문서인데 lint 통과(exit 0)함"
elif echo "$LINT_OUT" | grep -q "섹션 밖 위치"; then
  pass "step7 섹션 밖 위치 거부 — lint exit 1 + '섹션 밖 위치' 사유 적중"
else
  fail "step7 섹션 밖 위치 거부 — exit 1이지만 사유가 위치 위반이 아님: $LINT_OUT"
fi
rm -rf "$TMP/wiki/nowhere"

# ── 단계 8: meta의 자리 — 루트 개요는 색인 머리에 실리고, 섹션 안 meta는 거부된다 ──
write_meta "$TMP/wiki/overview.md"
if run_lint && grep -q "^개요: \[" "$INDEX"; then
  write_meta "$TMP/wiki/knowledge/overview.md"
  if run_lint; then
    fail "step8 meta 자리 — 섹션 안 meta인데 lint 통과(exit 0)함"
  elif echo "$LINT_OUT" | grep -q "meta 문서는 wiki/ 루트에만"; then
    pass "step8 meta 자리 — 루트 개요는 색인 머리에 링크, 섹션 안 meta는 lint exit 1로 거부"
  else
    fail "step8 meta 자리 — exit 1이지만 사유가 meta 위치 위반이 아님: $LINT_OUT"
  fi
else
  fail "step8 meta 자리 — 루트 meta 개요가 통과하지 않거나 색인 머리에 링크되지 않음: $LINT_OUT"
fi
rm -f "$TMP/wiki/knowledge/overview.md" "$TMP/wiki/overview.md"

# ── 단계 9: 설정 위반 거부 A — config.sections에 슬래시(방은 wiki/ 바로 아래 한 조각) ──
# 슬래시와 중복은 사유가 다르므로 단계를 나눈다 — 한 픽스처에 둘을 섞으면 한쪽 검사를
# 무력화해도 다른 쪽 사유로 PASS해버려 검출력이 사라진다.
set_cfg "[knowledge, \"knowledge/sub\"]" "[]"
if run_lint; then
  fail "step9 섹션 이름 슬래시 거부 — 슬래시 섹션인데 lint 통과(exit 0)함"
elif echo "$LINT_OUT" | grep -q "불가 — wiki/ 바로 아래"; then
  pass "step9 섹션 이름 슬래시 거부 — lint exit 1 + 한 조각 규칙 위반 사유 적중"
else
  fail "step9 섹션 이름 슬래시 거부 — exit 1이지만 사유가 이름 규칙이 아님: $LINT_OUT"
fi

# ── 단계 10: 설정 위반 거부 B — config.sections 중복(방 하나에 이름 하나) ──
set_cfg "[knowledge, knowledge]" "[]"
if run_lint; then
  fail "step10 섹션 이름 중복 거부 — 중복 섹션인데 lint 통과(exit 0)함"
elif echo "$LINT_OUT" | grep -q "중복"; then
  pass "step10 섹션 이름 중복 거부 — lint exit 1 + 중복 사유 적중"
else
  fail "step10 섹션 이름 중복 거부 — exit 1이지만 사유가 중복이 아님: $LINT_OUT"
fi
set_cfg "[knowledge, troubleshooting, decisions]" "[]"

# ── 단계 11: 크기 상한 — 지식 문서는 300줄에서 막고, SCHEMA.md는 예외(시공 분량을 막으면 안 된다) ──
BIG="$TMP/wiki/knowledge/e2e-big.md"
write_doc "$BIG" "$FUTURE"
for _ in $(seq 1 320); do echo "채움 줄" >> "$BIG"; done
if run_lint; then
  fail "step11 크기 상한 — 300줄을 넘는 지식 문서인데 lint 통과(exit 0)함"
elif echo "$LINT_OUT" | grep -q "300줄 상한 초과"; then
  rm -f "$BIG"
  # 시공 시뮬레이션: 규약 절이 채워져 SCHEMA가 300줄을 넘어도 첫 시공이 막히면 안 된다.
  for _ in $(seq 1 60); do echo "- 시공이 채우는 규약 한 줄" >> "$SCHEMA"; done
  if run_lint; then
    pass "step11 크기 상한 — 지식 문서 300줄 초과는 거부, SCHEMA.md는 초과해도 통과(시공 여지)"
  else
    fail "step11 크기 상한 — SCHEMA.md가 300줄을 넘자 lint가 막았다 (첫 시공 커밋이 불가능해진다): $LINT_OUT"
  fi
  cp "$ROOT/wiki/SCHEMA.md" "$SCHEMA"
  set_cfg "[knowledge, troubleshooting, decisions]" "[]"
else
  rm -f "$BIG"
  fail "step11 크기 상한 — exit 1이지만 사유가 300줄 초과가 아님: $LINT_OUT"
fi

# ── 단계 12: 만료 — review_by 경과 시 배너 삽입·색인의 문서 줄에 표시, 갱신 시 둘 다 제거 ──
# 색인 확인은 '^- [' 문서 줄로 한정한다 — 집계 줄("⚠️ 만료 1")에 적중하면
# 문서별 표시를 없애도 PASS해버린다.
write_doc "$DOC" "$PAST"
run_lint
BANNER_RC=$?
if [ $BANNER_RC -eq 0 ] && grep -q "^> ⚠️ 만료(review_by" "$DOC" && grep -q "^- \[.*⚠️ 만료" "$INDEX"; then
  sed -i.bak "s/^review_by: .*/review_by: $FUTURE/" "$DOC" && rm -f "$DOC.bak"
  if run_lint && ! grep -q "^> ⚠️ 만료(review_by" "$DOC" && ! grep -q "^- \[.*⚠️ 만료" "$INDEX"; then
    pass "step12 만료 — 경과 문서에 배너 삽입·색인 문서 줄에 만료 표시, review_by 갱신 후 둘 다 제거"
  else
    fail "step12 만료 — review_by를 갱신했는데 배너 또는 색인의 만료 표시가 남음: $LINT_OUT"
  fi
else
  fail "step12 만료 — 배너가 삽입되지 않거나 색인 문서 줄에 만료가 표시되지 않음: $LINT_OUT"
fi

# ── 단계 13: ~50문서 상한 경고 — 색인 머리가 초과를 신고한다 (표시일 뿐 exit 0) ──
for i in $(seq 1 50); do write_doc "$TMP/wiki/knowledge/e2e-bulk-$i.md" "$FUTURE"; done
if run_lint && grep -q "^> ⚠️ ~50문서 상한 초과" "$INDEX"; then
  pass "step13 상한 경고 — 51문서 이상에서 색인 머리에 초과 경고, lint는 통과(게이트 아님)"
else
  fail "step13 상한 경고 — 색인 머리에 초과 경고가 없거나 lint가 실패함: $LINT_OUT"
fi
rm -f "$TMP"/wiki/knowledge/e2e-bulk-*.md
run_lint

# ── 단계 14: 원본 워킹트리 불변 — 스위트는 사본 밖을 건드리지 않는다 ──
END_STATUS="$(git status --porcelain 2>/dev/null)"
if [ "$END_STATUS" = "$START_STATUS" ]; then
  pass "step14 원본 불변 — 워킹트리 상태가 시작 시점과 동일"
else
  fail "step14 원본 불변 — 워킹트리가 변경됨 (시작: [$START_STATUS] / 종료: [$END_STATUS])"
fi

echo "----"
if [ "$FAILS" -eq 0 ]; then
  echo "RESULT: 전 단계 PASS"
  exit 0
else
  echo "RESULT: $FAILS 단계 FAIL"
  exit 1
fi
