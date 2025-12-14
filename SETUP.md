# 🔧 Picta 프로젝트 설정 가이드

다른 사람이 이 프로젝트를 테스트하려면 다음 설정이 필요합니다.

## 📋 필수 설정 항목

### 1. Anthropic API Key (대화형 검색 기능용)

**LangChain Agent 기능을 사용하려면 필수입니다.**

1. [Anthropic Console](https://console.anthropic.com/)에서 API 키 발급
2. 환경 변수로 설정:

```bash
# macOS/Linux
export ANTHROPIC_API_KEY="your-api-key-here"

# 또는 .env 파일 생성 (권장)
echo "ANTHROPIC_API_KEY=your-api-key-here" > backend/.env
```

**참고**: API 키가 없어도 기본 검색 기능은 동작합니다. 다만 대화형 검색(Agent) 기능은 사용할 수 없습니다.

---

### 2. Google Drive 인증 (Google Drive 사용 시)

**Google Drive에서 사진을 불러오려면 필요합니다.**

#### 2-1. Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 (또는 기존 프로젝트 선택)
3. **API 및 서비스 > 라이브러리**에서 "Google Drive API" 활성화
4. **API 및 서비스 > 사용자 인증 정보**로 이동
5. **사용자 인증 정보 만들기 > OAuth 클라이언트 ID** 선택
   - 애플리케이션 유형: **데스크톱 앱**
   - 이름: 원하는 이름 (예: "Picta Desktop")
6. 생성된 `credentials.json` 파일 다운로드

#### 2-2. credentials.json 배치

프로젝트 루트 또는 `backend/` 폴더에 `credentials.json` 파일을 배치:

```bash
# 프로젝트 루트에 배치
cp ~/Downloads/credentials.json .

# 또는 backend 폴더에 배치
cp ~/Downloads/credentials.json backend/
```

#### 2-3. 첫 인증 실행

프로그램을 처음 실행하면 브라우저가 열리고 Google 계정 로그인을 요청합니다.
인증 완료 후 `token.pickle` 파일이 자동 생성됩니다.

**⚠️ 주의사항**:
- `credentials.json`: **공유하지 마세요!** (개인 Google Cloud 프로젝트 정보)
- `token.pickle`: **공유하지 마세요!** (개인 인증 토큰)
- 이 파일들은 `.gitignore`에 추가되어 있어야 합니다.

---

### 3. 데이터베이스 경로

프로젝트는 다음 데이터베이스를 사용합니다:

- `data/picta_mac.db`: Mac Photos Library 인덱싱 결과
- `data/picta_gdrive.db`: Google Drive 인덱싱 결과

**처음 실행 시**: 데이터베이스는 자동으로 생성됩니다. `main.py`를 실행하여 사진을 인덱싱하세요.

---

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt

# LangChain 기능 사용 시 (선택)
pip install langchain langchain-anthropic langchain-core
```

### 2. 환경 변수 설정

```bash
# backend/.env 파일 생성
cd backend
cat > .env << EOF
ANTHROPIC_API_KEY=your-api-key-here
EOF
```

### 3. Google Drive 사용 시

```bash
# credentials.json을 프로젝트 루트 또는 backend/에 배치
cp ~/Downloads/credentials.json .
```

### 4. 실행

```bash
# 백엔드 서버 실행
cd backend
python api.py
# 또는
uvicorn api:app --reload --port 8000

# 프론트엔드 실행 (별도 터미널)
cd frontend
npm install
npm run dev
```

---

## 📝 설정 파일 요약

| 파일/설정 | 위치 | 필수 여부 | 설명 |
|----------|------|----------|------|
| `ANTHROPIC_API_KEY` | 환경 변수 또는 `backend/.env` | 선택 | LangChain Agent 기능용 |
| `credentials.json` | 프로젝트 루트 또는 `backend/` | 선택 | Google Drive 인증용 |
| `token.pickle` | 프로젝트 루트 또는 `backend/` | 자동 생성 | Google Drive 인증 토큰 |
| `data/picta_mac.db` | `data/` | 자동 생성 | Mac Photos 인덱스 |
| `data/picta_gdrive.db` | `data/` | 자동 생성 | Google Drive 인덱스 |

---

## ⚠️ 주의사항

1. **`.env` 파일**: Git에 커밋하지 마세요 (`.gitignore`에 추가되어 있어야 함)
2. **`credentials.json`**: Git에 커밋하지 마세요
3. **`token.pickle`**: Git에 커밋하지 마세요 (개인 인증 정보)
4. **데이터베이스**: `data/*.db` 파일은 인덱싱 결과이므로 공유할 필요 없습니다.

---

## 🔍 문제 해결

### "ANTHROPIC_API_KEY가 설정되지 않았습니다" 경고
- **해결**: 환경 변수 설정 또는 `backend/.env` 파일 생성
- **영향**: 대화형 검색 기능만 사용 불가, 기본 검색은 정상 동작

### "credentials.json 파일이 없습니다" 오류
- **해결**: Google Cloud Console에서 OAuth 클라이언트 ID 생성 후 `credentials.json` 다운로드
- **영향**: Google Drive 인덱싱 불가, Mac Photos는 정상 동작

### "DB가 없습니다" 오류
- **해결**: `main.py` 실행하여 사진 인덱싱 먼저 수행
- **영향**: 검색 기능 사용 불가

---

## 📚 추가 정보

- **기본 검색만 사용**: API 키 없이도 동작합니다
- **대화형 검색 사용**: `ANTHROPIC_API_KEY` 필요
- **Google Drive 사용**: `credentials.json` 필요
- **Mac Photos 사용**: 추가 설정 불필요 (macOS만)

