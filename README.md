# 📸 Picta 최종 통합 패키지

기존 프로젝트에 새 기능을 추가하는 파일들입니다.

## 📦 포함된 파일

```
picta/
├── agent/                   # LangChain 대화형 Agent
│   ├── __init__.py
│   ├── photo_agent.py
│   ├── tools.py
│   └── prompts.py
│
├── visual_search/           # 유사 사진 검색 (신규)
│   ├── __init__.py
│   └── engine.py
│
├── backend/
│   └── api.py               # 통합 API (교체)
│
└── frontend/
    └── Search.jsx           # 대화형 UI (교체)
```

## 🔧 설정 가이드

**다른 사람이 테스트하려면 설정이 필요합니다!**

자세한 설정 방법은 **[SETUP.md](./SETUP.md)** 파일을 참고하세요.

1. **Anthropic API Key** (선택): 대화형 검색 기능용
   - 환경 변수: `ANTHROPIC_API_KEY` 또는 `backend/.env` 파일
2. **Google Drive 인증** (선택): Google Drive 사용 시
   - `credentials.json` 파일 필요 (Google Cloud Console에서 발급)
3. **데이터베이스**: `main.py` 실행하여 사진 인덱싱

---

## 🚀 설치 방법

### 1. 새 모듈 복사

```bash
# agent 폴더 복사
cp -r picta_final/agent ~/picta_prototype_5/

# visual_search 폴더 복사
cp -r picta_final/visual_search ~/picta_prototype_5/
```

### 2. 기존 파일 교체

```bash
# api.py 교체
cp picta_final/backend/api.py ~/picta_prototype_5/backend/

# Search.jsx 교체
cp picta_final/frontend/Search.jsx ~/picta_prototype_5/frontend/src/pages/
```

### 3. LangChain 설치 (선택)

```bash
pip install langchain langchain-anthropic langchain-core
```

> LangChain 없어도 기본 기능은 동작합니다!

## 추가 기능

| 기능 | 설명 | 필요 모듈 |
|------|------|----------|
| 대화형 검색 | 멀티턴 자연어 검색 | agent/ (선택) |
| 유사 사진 | CLIP 기반 시각 유사도 | visual_search/ (선택) |
| 같은 장소 | GPS/지명 기반 검색 | 내장 |
| 같은 날 | 날짜 기반 검색 | 내장 |
| 추천 패널 | 사진 클릭 시 추천 | 내장 |

## 🔌 API 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /search` | 기존 검색 |
| `POST /chat` | 대화형 검색 |
| `POST /similar` | 유사 사진 검색 |
| `GET /recommendations/{id}` | 사진 추천 |
| `POST /similar/upload` | 이미지 업로드 검색 |

## 🎨 UI 레이아웃

```
┌──────────────────────────────────────────────────────┐
│ 📸 Picta AI              [🍎 맥북] [☁️ 구글드라이브] │
├──────────┬──────────────────────────┬────────────────┤
│ 💬 대화  │      📷 검색 결과        │ 📷 추천       │
│          │                          │ (클릭 시)     │
│ [예시]   │  [사진] [사진] [사진]    │ 🎨 비슷한    │
│ [예시]   │  [사진] [사진] [사진]    │ 📍 같은장소  │
│          │                          │ 📅 같은날    │
│ [입력창] │                          │               │
└──────────┴──────────────────────────┴────────────────┘
```

## ⚠️ 주의사항

- `agent/`, `visual_search/` 없어도 **기본 기능은 동작**합니다
- LangChain 설치 안 하면 대화형 검색이 기본 검색으로 fallback됩니다
- 기존 DB(`data/`)는 그대로 사용됩니다
