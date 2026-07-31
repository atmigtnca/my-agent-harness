# loop 상태 파일 스키마 (state-files)

> `docs/projects/<slug>/`에 놓이는 파일들의 규격 원본. 무엇을 어떤 형식으로 두는가만 다룬다.
> 사이클 루틴·브리프 템플릿·검증 사다리·함정 목록은 여기서 다루지 않는다 — `docs/loop/loop-guide.md`가 원본이다.
> `/loop-plan` 스킬이 이 스키마대로 새 프로젝트의 파일을 시공한다. 그래서 §5에 각 파일의 필수 헤딩을 못박는다.

## 0. `docs/projects/<slug>/` 배치 규칙

- 한 프로젝트의 모든 상태는 이 디렉토리 하나에 모은다. 프로젝트가 늘어도 서로 섞이지 않는다.
- **slug 명명**: 소문자 영문·숫자·하이픈만. 동사+대상 또는 대상 한 단어(예: `docs-site`). 디렉토리명이 곧 slug이고 상태 파일·커밋이 이 이름을 참조하므로 시공 후 변경 금지.
- 디렉토리 안의 파일은 세 범주다:
  1. **스펙 SSOT** — `requirements.md` 1개. 무엇을 만드는가의 단일 원천. loop 시작 시 확정되면 이후 원칙적으로 고정.
  2. **상태 파일 2종** — `features.json`·`progress.md`. loop가 읽고 갱신하는 운영 상태.
  3. **재료 파일** (선택) — 조사 노트 등 프로젝트 한정 원자료. 파일명은 `research-*.md`처럼 용도를 드러낸다. 상태 파일도 스펙도 아니므로 §1·§2의 규칙을 적용하지 않는다(진행 일지·스펙에 섞지 말고 별도 파일로 영속화).

## 1. 문서 목록과 범주

| 파일 | 범주 | 형식 | 시공 주체 | 사이클 중 갱신 주체 |
|---|---|---|---|---|
| `requirements.md` | 스펙 SSOT | Markdown | loop-plan | (원칙 고정 — 스펙 변경 시에만 Advisor) |
| `features.json` | 상태 | JSON | loop-plan(구조) | Advisor(`passes`·`blocked`·`verified_at_commit`만) |
| `progress.md` | 상태 | Markdown | loop-plan(뼈대) | Advisor(매 사이클 — 상단 절 누적 + 사이클 항목 추가) |

- AGENTS.md·loop-guide가 부르는 "상태 파일 2종"은 이 표의 상태 2개다. `requirements.md`는 스펙 SSOT(loop의 입력)라 2종과 별개로 센다. 재료 파일도 밖이다.
- JSON은 features.json 하나뿐이다. 모델이 함부로 형식을 깨지 않게 완료 기준만 기계가 읽는 형식으로 둔다(loop-guide §3).

## 2. 파일별 수정 권한

- **Worker는 이 디렉토리의 어느 파일도 수정하지 않는다.** Worker는 산출물(코드·문서)만 만들고, 상태 반영은 Advisor가 한다. 이 분리가 "작성자≠채점자"의 파일 층 구현이다(loop-guide §0).
- **Advisor 전용, 매 사이클 갱신**: `features.json`의 `passes`·`blocked`·`verified_at_commit` 필드, `progress.md`.
- **`passes`는 특히 Advisor 전용**: diff를 직접 읽고 `verify` 절차를 직접 재실행해 관찰한 뒤에만 `true`로 바꾼다(loop-guide §11). Worker 보고나 desc를 근거로 바꾸지 않는다. `blocked`도 같다 — 3사이클 연속 검증 실패를 직접 관찰한 뒤에만 기록하고, 사유에 `resolvable:` 또는 `human_blocked:` 접두사를 붙인다(§3).
- **verify는 사이클 중 강화만 가능하다**: Advisor는 verify를 더 어렵게 만드는 수정(케이스 추가·판정값 구체화)만 재량으로 할 수 있다. 완화·삭제는 완료 정의를 바꾸는 스펙 수정이므로 기준 관리 경로(loop-guide §12)를 따른다 — 최적화하는 쪽이 자기 채점 기준을 낮추는 문을 여기서 막는다.
- **loop-plan 시공 시 1회 작성, 이후 Advisor만**: `features.json`의 구조(feature 배열·필드), `requirements.md`. `progress.md`의 상단 고정 절(함정 목록·검증 인프라)은 사이클마다 Advisor가 누적한다.
- 위 권한은 각 프로젝트 `features.json` 최상위 `rule` 필드에도 요약해 못박는다(§3).

## 3. features.json 스키마

최상위는 객체 하나. 키 3개.

| 키 | 형식 | 정의 |
|---|---|---|
| `project` | 문자열 | 프로젝트 slug. 디렉토리명과 일치. |
| `rule` | 문자열 | `passes` 갱신 규칙 등 이 파일의 거버넌스 한 문단. 모델이 규칙을 매번 재유도하지 않게 파일 안에 둔다. |
| `features` | 배열 | feature 객체 목록. |

feature 객체의 필수 필드 5개 + 선택 필드 2개:

| 필드 | 형식 | 정의 |
|---|---|---|
| `id` | 문자열 | `F` + 3자리 일련번호(`F001`). 브리프·커밋·progress가 이 id로 feature를 가리킨다. 부여 후 불변. |
| `phase` | 정수 | 실행 페이즈. 의존관계·병렬 가능 여부의 판단 근거(같은 phase라도 파일 영역이 겹치면 병렬 불가 — loop-guide §6). 페이즈 간 의존은 phase 순서가 담고, 부연이 필요하면 requirements.md 제약 절에 적는다. |
| `desc` | 문자열 | 무엇을 만드는가. 산출물 경로 + 핵심 요건. **desc는 방향 제시일 뿐, 완료 판정 근거가 아니다.** |
| `verify` | 문자열 | 완료를 기계로 판정하는 절차. 이 필드가 검증 절차 그 자체가 된다(§4). |
| `passes` | 불리언 | Advisor가 verify를 직접 재실행해 통과를 관찰했는가. 정지 조건은 전 feature 판정 완료(`passes: true` 또는 `blocked` 존재). `passes: true` 이후 해당 feature의 스펙이나 대상 파일이 변경되면 그 passes는 재검토 대상이며, verify를 재실행하기 전까지 신뢰하지 않는다. |
| `verified_at_commit` | 문자열(조건부) | **감사 앵커.** `passes: true`면 필수, 아니면 금지. Advisor가 verify 재실행을 관찰하고 `passes`를 `true`로 바꿀 때, 그 검증이 관찰한 코드가 들어간 커밋의 해시(소문자 hex 7~40자 — 보통 그 사이클 통과분 커밋, 새 변경이 없었다면 현재 HEAD. 상태 파일 갱신 커밋이 아니다)를 함께 기록한다. 이후 이 해시 뒤에 feature의 대상 파일이 변경된 것이 관찰되면 Advisor가 `passes`를 `false`로 강등하고 이 필드를 지운다 — 감지 절차는 loop-guide §4-1 선행 감사. |
| `blocked` | 문자열(선택) | **서킷브레이커.** 같은 feature가 3사이클 연속 검증 실패하면 Advisor가 사유를 기록하고 재위임을 멈춘다. 사유 문자열은 `resolvable:` 또는 `human_blocked:` 접두사로 시작한다 — `resolvable:` = 에이전트가 원리상 풀 수 있으나 3사이클을 소진했다(다음 loop나 사람 힌트로 재개 가능), `human_blocked:` = 크리덴셜·외부 승인·수동 단계 등 사람만 풀 수 있다. 있는 동안 태스크 선택에서 제외하고, 정지 판정에서는 "판정 완료"로 센다. 해소(사용자 개입·선행 조건 충족)를 관찰하면 Advisor가 필드를 지우고 재개한다. 단 `human_blocked:`는 3사이클을 기다리지 않고 즉시 격상할 수 있다(loop-guide §4-5). 시공 시에는 만들지 않는다. |

실물 예 — 설정 로더 feature 하나:

```json
{ "id": "F001", "phase": 1,
  "desc": "src/config/loader.py — YAML 설정 파일을 읽어 필수 키를 검증하고 기본값을 병합하는 로더.",
  "verify": "python3 -m pytest tests/test_loader.py 통과(정상 로드·기본값 병합·필수 키 누락 3케이스). 잘못된 YAML 입력 시 ConfigError raise 확인. grep -c 'def test_' tests/test_loader.py 결과 3 이상",
  "passes": true, "verified_at_commit": "a1b2c3d" }
```

## 4. verify 작성 기준 — desc보다 verify를 공들여라

완료 기준은 desc가 아니라 verify가 진다(loop-guide §2). desc는 Worker를 향하고, verify는 Advisor의 채점표이자 정지 판정의 근거다. verify 하나가 다음 3요건을 모두 만족해야 한다.

1. **기계 판정 가능** — 사람의 인상("자연스러운지", "잘 되는지")이 아니라 참·거짓이 갈리는 관찰. "느낌"이 들어가면 실패다.
2. **실행 명령 포함** — 무엇을 실행해 무엇을 보는지 명령을 적는다(`grep -in ...`, `curl ...`, `python3 -m json.tool ...`). Advisor가 그대로 재실행할 수 있어야 한다.
3. **성공 판정값 명시** — 통과선을 숫자·문자열로 못박는다(HTTP `201`, `grep 0건`, `python3 -m json.tool 통과`). 실패 경로(잘못된 입력 → `401`/`404`)도 하나 이상 포함하면 스텁·보안 결함을 잡는다(loop-guide §7).

좋은 예 — 명령·상태 코드·실패 경로·정리까지 명시:

```
POST /items 201 → GET /items/{id}(생성 필드 존재) → PATCH 200 → DELETE 204 → GET 404
+ 잘못된 토큰 401 + 파일 업로드 201·url 반환. 전체 출력 캡처에서 토큰 문자열 grep 0건. 종료 후 dev 서버 정리
```

나쁜 예(회피 대상) — "CLI가 정상 동작하는지 확인한다": 실행 명령 없음, 성공 판정값 없음, 기계 판정 불가. 이런 verify로는 `passes`를 관찰로 찍을 수 없다.

3요건 중 **기계 판정 가능한 표면**(추상어 잔존·실행 명령 부재·판정값 부재)은 `scripts/loop-lint.py`가 휴리스틱으로 검사한다 — 시공 직후 lint가 이 세 가지를 잡아 시공 중인 에이전트가 스스로 고친다. 다만 **lint 통과는 필요조건일 뿐이다**: 명령과 숫자가 박혀 있어도 그 verify가 desc의 완료를 실제로 증명하는지(의미 충족)는 문자열로 알 수 없다. 그 판정은 loop-plan §5의 리뷰 게이트가 본다. 명령 토큰 오탐(목록 밖 도구 — `sqlite3`·`ruff` 등)이면 **verify에 무관한 토큰을 끼워 넣지 말고** loop-lint의 `_CMD_TOKENS`를 넓힌 뒤 그 결정을 progress.md 결정 소절에 기록한다 — 통과용 토큰 삽입은 자기 채점 기준 조작이다.

## 5. 각 상태 파일의 필수 구조 (loop-plan 시공용)

시공 시 아래 헤딩·형식을 그대로 만든다. 사이클 루틴이 각 파일의 어느 절을 언제 갱신하는지는 loop-guide §4를 따른다.

- **`requirements.md`** — 최상단 1줄: 이 문서가 스펙 SSOT이며 충돌 시 이긴다 + "문서에 없는 것은 재량, progress.md 결정 기록" 원칙. 절: `## 목표` / `## 제약` / `## 완료 정의` / `## 제외 범위`. 완료 정의는 features.json 전 항목 판정 완료(passes ∨ blocked)를 정지 조건으로 명시. `## 제외 범위`는 이번에 **안 하는 것**(out of scope) 목록 — 최소 1항목을 적고, 정말 없으면 `없음 — <사유>` 한 줄로 명시한다(빈 절 금지). 재량 선언도 관찰 가능한 경계로 쓴다(예: "색상은 재량 — 기존 tokens.css 값만 사용". "적절히 판단" 류는 재량 선언이어도 추상어 lint에 걸린다).
- **`progress.md`** — 최상단 1줄: "최신이 위, 각 사이클 항목 끝에 **다음 할 일**" + 모델 지정 한 줄(Advisor 한 티어 아래 Worker). 두 부분으로 구성:
  - **상단 고정 절 2개** — `## 함정 목록`(프로젝트 고유 함정, 사이클마다 누적, 브리프에 해당분 주입) / `## 검증 인프라`(도구·경로·실행법 — 브리프 [검증 인프라] 절의 원천). 범용 절차(사이클 루틴·브리프 템플릿)는 넣지 말고 loop-guide §4·§5를 참조로 가리킨다(중복 금지).
  - **사이클 일지** — 항목 = `## 사이클 N — 날짜 — 요지`. 소절 순서: 한 일 / **결정**(형식 = 결정·이유·고려한 대안. 재량 결정은 코드 1줄이라도 기록, 없으면 소절 생략) / **토큰**(사이클 소비 요약 한 줄 — 캘리브레이션 근거) / **다음 할 일**(필수, 항목의 끝 — 다음 wakeup 인계).

시공 직후 features.json은 `python3 -m json.tool docs/projects/<slug>/features.json`을 통과해야 하고, 전 feature에 `verify` 필드가 있어야 한다.
