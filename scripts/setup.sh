#!/bin/bash
# my-agent-harness 온보딩 — 기계가 검사할 수 있는 셋업을 한 명령으로.
# 사용: scripts/setup.sh
# 멱등: 몇 번을 다시 실행해도 안전하다. README "빠른 시작" 절이 이 스크립트를 부른다.
#
# 여기서 못 하는 것(사람 몫): claude의 trust 다이얼로그 수락.
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
cd "$ROOT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
WARN=0

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; WARN=1; }

echo "── my-agent-harness 온보딩 검사 ──"

# 1. githooks — 위키 형식 검사·비밀 검출(pre-commit)의 로컬 활성화
if [ "$(git config core.hooksPath || true)" = "scripts/githooks" ]; then
    ok "core.hooksPath 이미 설정됨 (scripts/githooks)"
else
    git config core.hooksPath scripts/githooks
    ok "core.hooksPath 설정 완료 → 위키 lint·비밀 검출 pre-commit 활성화"
fi

# 2. gitleaks — 없으면 pre-commit이 비밀 검출을 건너뛴다 (CI가 최후 방어선이지만 로컬이 빠르다)
if command -v gitleaks >/dev/null 2>&1; then
    ok "gitleaks $(gitleaks version 2>/dev/null)"
else
    warn "gitleaks 미설치 — 비밀 검출이 로컬에서 건너뛰어진다.
      설치: https://github.com/gitleaks/gitleaks/releases 바이너리를 PATH에 (예: ~/.local/bin/)"
fi

# 3. python3 + PyYAML — pre-commit의 wiki-lint 실행 요건
if python3 -c "import yaml" >/dev/null 2>&1; then
    ok "python3 + PyYAML (wiki-lint 실행 가능)"
else
    warn "python3 또는 PyYAML 없음 — wiki-lint가 실패한다. 설치: pip install pyyaml"
fi

# 4. git user.name — 위키 승인 기록(verified_by)에 이 이름이 남는다
NAME="$(git config user.name || true)"
case "$NAME" in
    ""|ubuntu|root|user|admin)
        warn "git user.name이 '${NAME:-비어 있음}' — 팀이 알아볼 본인 이름으로:
      git config user.name \"<실명 또는 통용 핸들>\"" ;;
    *)
        ok "git user.name: $NAME" ;;
esac

echo ""
if grep -q 'sections: \[\]' wiki/SCHEMA.md 2>/dev/null; then
    echo -e "  ${YELLOW}▸${NC} 위키가 아직 시공 전이다 — claude 안에서 /wiki-start 실행 (최초 1회, 상황 인터뷰 → 섹션·규약 설계)"
    echo ""
fi
if [ "$WARN" -eq 0 ]; then
    echo -e "${GREEN}✓ 셋업 완료.${NC} 남은 사람 몫: 이 디렉토리에서 claude 실행 후 trust 수락 — README \"빠른 시작\" 절"
else
    echo -e "${YELLOW}⚠ 위 경고를 해결한 뒤 다시 실행하면 전부 ✓가 되어야 정상.${NC} (경고가 있어도 사용은 가능)"
fi
