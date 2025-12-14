"""
Picta API v2 - 최종 통합 버전
- 기존 검색 기능
- LangChain 대화형 Agent
- Visual Search (유사 사진)
- 추천 시스템
"""

import sys
import os
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from googleapiclient.http import MediaIoBaseDownload

from typing import Optional, List, Dict
import io
import sqlite3
import logging
import numpy as np
import uuid

# 기존 Picta 모듈
from core.image_processor import CLIPImageProcessor
from core.face_detector import FaceDetector
from core.database import DatabaseManager
from core.query_parser import QueryParser
from core.search_engine import SearchEngine
from core.response_generator import ResponseGenerator
from core.google_drive_loader import GoogleDriveLoader

# 새 모듈 (있으면 사용, 없으면 기본 기능만)
try:
    from agent.photo_agent import PhotoAgent, PhotoAgentSession
    AGENT_AVAILABLE = True
    logging.info("✅ LangChain Agent 모듈 로드됨")
except ImportError:
    AGENT_AVAILABLE = False
    logging.warning("⚠️ LangChain Agent 모듈 없음 - 기본 검색만 사용")

try:
    from visual_search.engine import VisualSearchEngine
    VISUAL_SEARCH_AVAILABLE = True
    logging.info("✅ Visual Search 모듈 로드됨")
except ImportError:
    VISUAL_SEARCH_AVAILABLE = False
    logging.warning("⚠️ Visual Search 모듈 없음 - 기본 유사 검색 사용")

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Picta API", version="2.0.0")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB 경로
MAC_DB_PATH = os.path.join(ROOT_DIR, "data", "picta_mac.db")
GDRIVE_DB_PATH = os.path.join(ROOT_DIR, "data", "picta_gdrive.db")

print(f"ROOT_DIR: {ROOT_DIR}")
print(f"MAC_DB exists: {os.path.exists(MAC_DB_PATH)} - {MAC_DB_PATH}")
print(f"GDRIVE_DB exists: {os.path.exists(GDRIVE_DB_PATH)} - {GDRIVE_DB_PATH}")

# 전역 엔진
engines = {}
visual_engines = {}
agent_sessions = {}


# === Request Models ===

class SearchRequest(BaseModel):
    query: str
    source: str = "mac"
    top_k: int = 20


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    source: str = "mac"


class SimilarRequest(BaseModel):
    image_id: int
    similarity_type: str = "visual"  # visual, location, time
    top_k: int = 20


# === Helper Functions ===

def get_db_count(db_path: str) -> int:
    if not os.path.exists(db_path):
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM images")
            return cursor.fetchone()[0]
    except:
        return 0


def get_db_path(source: str) -> str:
    return MAC_DB_PATH if source == "mac" else GDRIVE_DB_PATH


def get_engine(source: str):
    """소스별 엔진 가져오기 (lazy loading)"""
    if source not in engines:
        db_path = get_db_path(source)
        
        if not os.path.exists(db_path):
            return None
        
        logging.info(f"엔진 초기화: {source}")
        clip = CLIPImageProcessor()
        face = FaceDetector()
        db = DatabaseManager(db_path=db_path)
        query_parser = QueryParser()
        search_engine = SearchEngine(db_path, clip, face)
        response_gen = ResponseGenerator()
        
        engines[source] = {
            "clip": clip,
            "face": face,
            "db": db,
            "query_parser": query_parser,
            "search_engine": search_engine,
            "response_gen": response_gen,
            "db_path": db_path
        }
    
    return engines[source]


def get_visual_engine(source: str):
    """Visual Search 엔진 가져오기"""
    if not VISUAL_SEARCH_AVAILABLE:
        return None
    
    if source in visual_engines:
        return visual_engines[source]
    
    engine = get_engine(source)
    if not engine:
        return None
    
    logging.info(f"Visual Search 엔진 초기화: {source}")
    visual_engine = VisualSearchEngine(
        db_path=engine["db_path"],
        clip_processor=engine["clip"]
    )
    visual_engines[source] = visual_engine
    return visual_engine


def get_agent_session(source: str):
    """Agent 세션 매니저 가져오기"""
    if not AGENT_AVAILABLE:
        return None
    
    if source in agent_sessions:
        return agent_sessions[source]
    
    engine = get_engine(source)
    visual_engine = get_visual_engine(source)
    
    if not engine:
        return None
    
    session_manager = PhotoAgentSession(
        search_engine=engine["search_engine"],
        visual_search_engine=visual_engine
    )
    agent_sessions[source] = session_manager
    return session_manager


def get_image_info(db_path: str, image_id: int) -> Optional[Dict]:
    """이미지 정보 조회"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                FROM images WHERE id = ?
            """, (image_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "id": row[0],
                    "file_path": row[1],
                    "taken_date": row[2],
                    "location_name": row[3],
                    "gps_lat": row[4],
                    "gps_lon": row[5]
                }
    except Exception as e:
        logging.error(f"이미지 정보 조회 오류: {e}")
    return None


def get_image_vector(db_path: str, image_id: int) -> Optional[np.ndarray]:
    """이미지 CLIP 벡터 조회"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT clip_vector FROM images WHERE id = ?", (image_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return np.frombuffer(row[0], dtype=np.float32)
    except Exception as e:
        logging.error(f"벡터 조회 오류: {e}")
    return None


# === API Endpoints ===

@app.get("/")
def root():
    return {
        "message": "Picta API",
        "version": "2.0.0",
        "features": {
            "agent": AGENT_AVAILABLE,
            "visual_search": VISUAL_SEARCH_AVAILABLE
        }
    }


@app.get("/status")
def get_status():
    """현재 인덱싱 상태"""
    return {
        "mac": {
            "count": get_db_count(MAC_DB_PATH),
            "available": os.path.exists(MAC_DB_PATH)
        },
        "gdrive": {
            "count": get_db_count(GDRIVE_DB_PATH),
            "available": os.path.exists(GDRIVE_DB_PATH)
        },
        "features": {
            "agent": AGENT_AVAILABLE,
            "visual_search": VISUAL_SEARCH_AVAILABLE
        }
    }


# === 기존 검색 API ===

@app.post("/search")
def search(request: SearchRequest):
    """사진 검색 (기존 방식)"""
    engine = get_engine(request.source)
    
    if not engine:
        raise HTTPException(status_code=404, detail=f"{request.source} DB가 없습니다.")
    
    # 쿼리 파싱
    parsed = engine["query_parser"].parse_query(request.query)
    logging.info(f"파싱 결과: {parsed}")
    
    # 검색
    results = engine["search_engine"].search(parsed, top_k=request.top_k * 5)
    logging.info(f"검색 결과: {len(results)}개")

    # 유효한 파일만 필터링
    valid_results = []
    for r in results:
        file_path = r.get('file_path', '')
        if file_path.startswith('gdrive://'):
            valid_results.append(r)
        elif file_path and os.path.exists(file_path):
            valid_results.append(r)
        
        if len(valid_results) >= request.top_k:
            break
    
    # 응답 생성
    response_text = engine["response_gen"].generate_response(request.query, valid_results)
    
    return {
        "query": request.query,
        "response": response_text,
        "results": valid_results,
        "source": request.source,
        "total": len(valid_results)
    }


# === 대화형 검색 API (LangChain) ===

@app.post("/chat")
def chat(request: ChatRequest):
    """대화형 사진 검색 (LangChain Agent)"""
    
    # Agent 없으면 기본 검색으로 fallback
    if not AGENT_AVAILABLE:
        # 기본 검색으로 처리
        search_req = SearchRequest(query=request.message, source=request.source)
        result = search(search_req)
        return {
            "response": result["response"],
            "results": result["results"],
            "recommendations": None,
            "session_id": request.session_id or str(uuid.uuid4())
        }
    
    session_manager = get_agent_session(request.source)
    
    if not session_manager:
        raise HTTPException(status_code=404, detail=f"{request.source} DB가 없습니다.")
    
    session_id = request.session_id or str(uuid.uuid4())
    agent = session_manager.get_or_create_session(session_id)
    
    result = agent.chat(request.message)
    
    return {
        "response": result["response"],
        "results": result["results"],
        "recommendations": result.get("recommendations"),
        "session_id": session_id
    }


@app.delete("/chat/{session_id}")
def reset_chat(session_id: str, source: str = "mac"):
    """대화 세션 초기화"""
    if AGENT_AVAILABLE:
        session_manager = get_agent_session(source)
        if session_manager:
            session_manager.delete_session(session_id)
    
    return {"message": "세션 초기화 완료"}


# === 유사 사진 검색 API ===

@app.post("/similar")
def find_similar(request: SimilarRequest, source: str = "mac"):
    """유사 사진 검색"""
    db_path = get_db_path(source)
    
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="DB not found")
    
    # Visual Search 엔진 있으면 사용
    if VISUAL_SEARCH_AVAILABLE:
        visual_engine = get_visual_engine(source)
        if visual_engine:
            if request.similarity_type == "visual":
                results = visual_engine.find_similar_by_image(request.image_id, request.top_k)
            elif request.similarity_type == "location":
                results = visual_engine.find_by_same_location(request.image_id, request.top_k)
            elif request.similarity_type == "time":
                results = visual_engine.find_by_same_date(request.image_id, request.top_k)
            else:
                results = visual_engine.find_similar_by_image(request.image_id, request.top_k)
            
            return {
                "image_id": request.image_id,
                "similarity_type": request.similarity_type,
                "results": results,
                "total": len(results)
            }
    
    # 기본 유사 검색 (Visual Search 없을 때)
    engine = get_engine(source)
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")
    
    results = []
    
    if request.similarity_type == "visual":
        # CLIP 벡터 기반 유사도 검색
        query_vector = get_image_vector(db_path, request.image_id)
        if query_vector is None:
            raise HTTPException(status_code=404, detail="Image vector not found")
        
        search_engine = engine["search_engine"]
        if hasattr(search_engine, 'faiss_index') and search_engine.faiss_index is not None:
            import faiss
            
            query_vector = query_vector.reshape(1, -1).astype('float32')
            faiss.normalize_L2(query_vector)
            
            scores, indices = search_engine.faiss_index.search(query_vector, request.top_k + 1)
            
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(search_engine.id_mapping):
                    continue
                
                result_id = search_engine.id_mapping[idx]
                if result_id == request.image_id:
                    continue
                
                info = get_image_info(db_path, result_id)
                if info:
                    info["similarity"] = float(score)
                    results.append(info)
                
                if len(results) >= request.top_k:
                    break
    
    elif request.similarity_type == "location":
        base_info = get_image_info(db_path, request.image_id)
        if not base_info:
            raise HTTPException(status_code=404, detail="Image not found")
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            if base_info.get("gps_lat") and base_info.get("gps_lon"):
                lat, lon = base_info["gps_lat"], base_info["gps_lon"]
                lat_range = 1.0 / 111.0
                lon_range = 1.0 / (111.0 * abs(np.cos(np.radians(lat))))
                
                cursor.execute("""
                    SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                    FROM images
                    WHERE id != ?
                    AND gps_lat BETWEEN ? AND ?
                    AND gps_lon BETWEEN ? AND ?
                    LIMIT ?
                """, (request.image_id, lat - lat_range, lat + lat_range,
                      lon - lon_range, lon + lon_range, request.top_k))
            
            elif base_info.get("location_name"):
                location = base_info["location_name"].split(",")[0].strip()
                cursor.execute("""
                    SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                    FROM images
                    WHERE id != ? AND location_name LIKE ?
                    LIMIT ?
                """, (request.image_id, f"%{location}%", request.top_k))
            
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "file_path": row[1],
                    "taken_date": row[2],
                    "location_name": row[3],
                    "gps_lat": row[4],
                    "gps_lon": row[5],
                    "similarity": 0.9
                })
    
    elif request.similarity_type == "time":
        base_info = get_image_info(db_path, request.image_id)
        if not base_info or not base_info.get("taken_date"):
            raise HTTPException(status_code=404, detail="Date not found")
        
        date_str = base_info["taken_date"][:10]
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                FROM images
                WHERE id != ? AND taken_date LIKE ?
                ORDER BY taken_date
                LIMIT ?
            """, (request.image_id, f"{date_str}%", request.top_k))
            
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "file_path": row[1],
                    "taken_date": row[2],
                    "location_name": row[3],
                    "gps_lat": row[4],
                    "gps_lon": row[5],
                    "similarity": 0.9
                })
    
    return {
        "image_id": request.image_id,
        "similarity_type": request.similarity_type,
        "results": results,
        "total": len(results)
    }


@app.get("/recommendations/{image_id}")
def get_recommendations(image_id: int, source: str = "mac"):
    """사진 추천 (유사 + 같은 장소 + 같은 날)"""
    
    # Visual Search 엔진 있으면 사용
    if VISUAL_SEARCH_AVAILABLE:
        visual_engine = get_visual_engine(source)
        if visual_engine:
            recommendations = visual_engine.get_recommendations(image_id)
            return {
                "image_id": image_id,
                "recommendations": recommendations
            }
    
    # 기본 추천
    similar_visual = []
    same_location = []
    same_day = []
    
    try:
        req = SimilarRequest(image_id=image_id, similarity_type="visual", top_k=6)
        res = find_similar(req, source)
        similar_visual = res["results"]
    except:
        pass
    
    try:
        req = SimilarRequest(image_id=image_id, similarity_type="location", top_k=6)
        res = find_similar(req, source)
        same_location = res["results"]
    except:
        pass
    
    try:
        req = SimilarRequest(image_id=image_id, similarity_type="time", top_k=6)
        res = find_similar(req, source)
        same_day = res["results"]
    except:
        pass
    
    return {
        "image_id": image_id,
        "recommendations": {
            "similar_visual": similar_visual,
            "same_location": same_location,
            "same_day": same_day
        }
    }


# === 이미지 업로드 검색 ===

@app.post("/similar/upload")
async def find_similar_by_upload(
    file: UploadFile = File(...),
    source: str = "mac",
    top_k: int = 10
):
    """업로드된 이미지로 유사 사진 검색"""
    if not VISUAL_SEARCH_AVAILABLE:
        raise HTTPException(status_code=501, detail="Visual Search 기능이 없습니다")
    
    visual_engine = get_visual_engine(source)
    if not visual_engine:
        raise HTTPException(status_code=404, detail="Engine not found")
    
    contents = await file.read()
    results = visual_engine.find_similar_by_upload(contents, top_k)
    
    return {
        "filename": file.filename,
        "results": results,
        "total": len(results)
    }


# === 이미지 반환 API ===

@app.get("/image/{source}/{image_id}")
def get_image(source: str, image_id: int):
    """이미지 파일 반환"""
    db_path = get_db_path(source)
    
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="DB not found")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Image not found")
        
        file_path = row[0]
        
        # Google Drive 처리
        if file_path.startswith("gdrive://"):
            gdrive_id = file_path.replace("gdrive://", "")
            
            try:
                loader = GoogleDriveLoader()
                if loader.authenticate():
                    file_info = loader.service.files().get(fileId=gdrive_id, fields='mimeType').execute()
                    media_type = file_info.get('mimeType', 'image/jpeg')
                    
                    request = loader.service.files().get_media(fileId=gdrive_id)
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    
                    fh.seek(0)
                    content = fh.read()
                    
                    # HEIC 변환
                    if media_type in ['image/heic', 'image/heif']:
                        import pillow_heif
                        from PIL import Image
                        
                        pillow_heif.register_heif_opener()
                        fh.seek(0)
                        img = Image.open(fh)
                        
                        output = io.BytesIO()
                        img.convert('RGB').save(output, format='JPEG', quality=85)
                        output.seek(0)
                        content = output.read()
                        media_type = 'image/jpeg'
                    
                    return Response(content=content, media_type=media_type)
            except Exception as e:
                logging.error(f"Google Drive 이미지 로드 실패: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # 로컬 파일
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Image file not found")
        
        # 🔥 HEIC 파일 → JPEG 변환 (Chrome 지원)
        if file_path.lower().endswith(('.heic', '.heif')):
            try:
                import pillow_heif
                from PIL import Image
                
                pillow_heif.register_heif_opener()
                img = Image.open(file_path)
                
                output = io.BytesIO()
                img.convert('RGB').save(output, format='JPEG', quality=85)
                output.seek(0)
                
                return Response(content=output.read(), media_type='image/jpeg')
            except Exception as e:
                logging.error(f"HEIC 변환 실패: {e}")
                # 변환 실패 시 원본 반환 (Safari에서는 작동)
                return FileResponse(file_path)
        
        return FileResponse(file_path)


@app.get("/photo/{source}/{image_id}")
def get_photo_info(source: str, image_id: int):
    """사진 상세 정보"""
    db_path = get_db_path(source)
    info = get_image_info(db_path, image_id)
    
    if not info:
        raise HTTPException(status_code=404, detail="Image not found")
    
    return info


if __name__ == "__main__":
    import uvicorn
    os.makedirs("data", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)