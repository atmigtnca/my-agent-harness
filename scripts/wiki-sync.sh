#!/usr/bin/env bash
# SessionStart(startup) 훅: 이 repo를 원격(origin) 최신 상태로 맞춘다.
# 안전 원칙 — fast-forward만 한다. 로컬 변경·갈라짐(diverge)이 있으면
# 건드리지 않고 알리기만 한다. push는 어떤 경우에도 하지 않는다.
# stdout이 세션 컨텍스트에 주입된다. 이미 최신이고 알릴 것이 없으면 아무것도 출력하지 않는다.
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
git_root=$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel 2>/dev/null) || exit 0
G() { git -C "$git_root" "$@"; }

G remote get-url origin >/dev/null 2>&1 || exit 0
branch=$(G symbolic-ref --short -q HEAD) || exit 0    # detached HEAD면 건드리지 않는다

# 네트워크 문제로 세션 시작을 오래 막지 않도록 fetch에 시간 제한
if ! timeout 15 git -C "$git_root" fetch --quiet origin "$branch" 2>/dev/null; then
    echo "wiki-sync: origin fetch 실패 (네트워크/인증) — repo가 원격 최신인지 확인하지 못했다."
    exit 0
fi

remote_ref="origin/$branch"
G rev-parse --verify -q "$remote_ref" >/dev/null || exit 0

behind=$(G rev-list --count "HEAD..$remote_ref")
ahead=$(G rev-list --count "$remote_ref..HEAD")

if [ "$behind" -eq 0 ]; then
    if [ "$ahead" -gt 0 ]; then
        echo "wiki-sync: 이 repo에 push 대기 커밋 ${ahead}개가 있다 (push는 사람이 한다 — 사용자에게 알려라)."
    fi
    exit 0
fi

if [ "$ahead" -gt 0 ]; then
    echo "wiki-sync: 로컬(${branch})이 원격과 갈라졌다 (원격 ${behind}↓ / 로컬 ${ahead}↑)."
    echo "자동으로 합치지 않았다 — 사용자와 함께 정리하라."
    exit 0
fi

# 추적 파일에 수정·스테이징이 있으면 자동 병합하지 않는다 (untracked 충돌은 ff가 스스로 거부한다)
if [ -n "$(G status --porcelain --untracked-files=no)" ]; then
    echo "wiki-sync: 원격에 새 커밋 ${behind}개가 있지만 로컬 변경이 있어 자동 업데이트하지 않았다."
    echo "변경 정리 후 git pull --ff-only 하라."
    exit 0
fi

if G merge --ff-only --quiet "$remote_ref" 2>/dev/null; then
    echo "wiki-sync: repo를 원격 최신으로 업데이트했다 (${branch}, 커밋 ${behind}개 fast-forward):"
    G log --oneline "HEAD@{1}..HEAD" 2>/dev/null | sed 's/^/  /'
else
    echo "wiki-sync: fast-forward 실패 (untracked 파일 충돌 등) — 수동으로 git pull --ff-only 하라."
fi
