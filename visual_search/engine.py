"""
Visual Search Engine
CLIP 기반 시각적 유사도 검색 및 추천 시스템
"""

import os
import sqlite3
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import faiss

logging.basicConfig(level=logging.INFO)


class VisualSearchEngine:
    """시각적 유사도 기반 사진 검색 엔진"""
    
    def __init__(self, db_path: str, clip_processor=None):
        """
        Args:
            db_path: SQLite DB 경로
            clip_processor: CLIPImageProcessor 인스턴스
        """
        self.db_path = db_path
        self.clip = clip_processor
        
        # FAISS 인덱스
        self.faiss_index = None
        self.id_mapping = []  # FAISS index -> image_id 매핑
        
        # 인덱스 구축
        self._build_index()
    
    def _build_index(self):
        """FAISS 인덱스 구축"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, clip_vector FROM images WHERE clip_vector IS NOT NULL")
                rows = cursor.fetchall()
            
            if not rows:
                logging.warning("인덱싱할 이미지가 없습니다.")
                return
            
            vectors = []
            self.id_mapping = []
            
            for row in rows:
                image_id, vector_blob = row
                vector = np.frombuffer(vector_blob, dtype=np.float32)
                vectors.append(vector)
                self.id_mapping.append(image_id)
            
            vectors_np = np.array(vectors).astype('float32')
            
            # L2 정규화 (코사인 유사도용)
            faiss.normalize_L2(vectors_np)
            
            # Inner Product 인덱스 (정규화 후 = 코사인 유사도)
            dim = vectors_np.shape[1]
            self.faiss_index = faiss.IndexFlatIP(dim)
            self.faiss_index.add(vectors_np)
            
            logging.info(f"✅ Visual Search 인덱스 구축 완료: {len(vectors)}개 벡터")
            
        except Exception as e:
            logging.error(f"인덱스 구축 오류: {e}")
    
    def _get_vector(self, image_id: int) -> Optional[np.ndarray]:
        """이미지 ID로 CLIP 벡터 가져오기"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT clip_vector FROM images WHERE id = ?",
                    (image_id,)
                )
                row = cursor.fetchone()
                
                if row and row[0]:
                    return np.frombuffer(row[0], dtype=np.float32)
                return None
                
        except Exception as e:
            logging.error(f"벡터 조회 오류: {e}")
            return None
    
    def _get_image_info(self, image_id: int) -> Optional[Dict]:
        """이미지 정보 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
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
                return None
                
        except Exception as e:
            logging.error(f"이미지 정보 조회 오류: {e}")
            return None
    
    def find_similar_by_image(self, image_id: int, top_k: int = 10, 
                              exclude_self: bool = True) -> List[Dict]:
        """
        이미지 ID로 유사한 사진 검색
        
        Args:
            image_id: 기준 이미지 ID
            top_k: 반환할 최대 결과 수
            exclude_self: 자기 자신 제외 여부
        
        Returns:
            유사 사진 리스트 (유사도 포함)
        """
        if not self.faiss_index:
            return []
        
        query_vector = self._get_vector(image_id)
        if query_vector is None:
            return []
        
        # L2 정규화
        query_vector = query_vector.reshape(1, -1).astype('float32')
        faiss.normalize_L2(query_vector)
        
        # 검색 (자기 자신 포함해서 +1)
        k = top_k + 1 if exclude_self else top_k
        scores, indices = self.faiss_index.search(query_vector, k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
                
            result_id = self.id_mapping[idx]
            
            # 자기 자신 제외
            if exclude_self and result_id == image_id:
                continue
            
            info = self._get_image_info(result_id)
            if info:
                info["similarity"] = float(score)
                results.append(info)
            
            if len(results) >= top_k:
                break
        
        return results
    
    def find_similar_by_vector(self, query_vector: np.ndarray, 
                               top_k: int = 10) -> List[Dict]:
        """벡터로 유사한 사진 검색 (업로드된 이미지용)"""
        if not self.faiss_index:
            return []
        
        query_vector = query_vector.reshape(1, -1).astype('float32')
        faiss.normalize_L2(query_vector)
        
        scores, indices = self.faiss_index.search(query_vector, top_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            
            result_id = self.id_mapping[idx]
            info = self._get_image_info(result_id)
            if info:
                info["similarity"] = float(score)
                results.append(info)
        
        return results
    
    def find_similar_by_upload(self, image_bytes: bytes, top_k: int = 10) -> List[Dict]:
        """업로드된 이미지로 유사 사진 검색"""
        if not self.clip:
            logging.error("CLIP 프로세서가 없습니다.")
            return []
        
        try:
            # 이미지 인코딩
            from PIL import Image
            import io
            
            img = Image.open(io.BytesIO(image_bytes))
            query_vector = self.clip.encode_image_pil(img)
            
            return self.find_similar_by_vector(query_vector, top_k)
            
        except Exception as e:
            logging.error(f"업로드 이미지 검색 오류: {e}")
            return []
    
    def find_by_same_location(self, image_id: int, top_k: int = 10,
                              radius_km: float = 1.0) -> List[Dict]:
        """같은 장소에서 찍은 사진 검색"""
        base_info = self._get_image_info(image_id)
        if not base_info:
            return []
        
        gps_lat = base_info.get("gps_lat")
        gps_lon = base_info.get("gps_lon")
        location_name = base_info.get("location_name")
        
        results = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if gps_lat and gps_lon:
                # GPS 기반 검색 (Haversine 근사)
                # 1도 ≈ 111km
                lat_range = radius_km / 111.0
                lon_range = radius_km / (111.0 * abs(np.cos(np.radians(gps_lat))))
                
                cursor.execute("""
                    SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                    FROM images
                    WHERE id != ?
                    AND gps_lat BETWEEN ? AND ?
                    AND gps_lon BETWEEN ? AND ?
                    LIMIT ?
                """, (
                    image_id,
                    gps_lat - lat_range, gps_lat + lat_range,
                    gps_lon - lon_range, gps_lon + lon_range,
                    top_k
                ))
                
            elif location_name:
                # 장소명 기반 검색
                # 첫 번째 지역명 추출
                primary_location = location_name.split(",")[0].strip()
                
                cursor.execute("""
                    SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                    FROM images
                    WHERE id != ?
                    AND location_name LIKE ?
                    LIMIT ?
                """, (image_id, f"%{primary_location}%", top_k))
            
            else:
                return []
            
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "file_path": row[1],
                    "taken_date": row[2],
                    "location_name": row[3],
                    "gps_lat": row[4],
                    "gps_lon": row[5],
                    "match_type": "location"
                })
        
        return results
    
    def find_by_same_date(self, image_id: int, top_k: int = 10,
                          date_range_days: int = 0) -> List[Dict]:
        """같은 날(또는 기간) 찍은 사진 검색"""
        base_info = self._get_image_info(image_id)
        if not base_info or not base_info.get("taken_date"):
            return []
        
        taken_date = base_info["taken_date"]
        
        try:
            # 날짜 파싱
            if "T" in taken_date:
                base_date = datetime.fromisoformat(taken_date.replace("Z", ""))
            else:
                base_date = datetime.strptime(taken_date[:10], "%Y-%m-%d")
            
            start_date = base_date - timedelta(days=date_range_days)
            end_date = base_date + timedelta(days=date_range_days + 1)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                    FROM images
                    WHERE id != ?
                    AND taken_date >= ?
                    AND taken_date < ?
                    ORDER BY taken_date
                    LIMIT ?
                """, (
                    image_id,
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                    top_k
                ))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "id": row[0],
                        "file_path": row[1],
                        "taken_date": row[2],
                        "location_name": row[3],
                        "gps_lat": row[4],
                        "gps_lon": row[5],
                        "match_type": "date"
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"날짜 검색 오류: {e}")
            return []
    
    def get_recommendations(self, image_id: int, top_k: int = 5) -> Dict[str, List[Dict]]:
        """
        사진에 대한 종합 추천
        
        Returns:
            {
                "similar_visual": 시각적 유사 사진,
                "same_location": 같은 장소 사진,
                "same_day": 같은 날 사진
            }
        """
        return {
            "similar_visual": self.find_similar_by_image(image_id, top_k),
            "same_location": self.find_by_same_location(image_id, top_k),
            "same_day": self.find_by_same_date(image_id, top_k)
        }
    
    def get_photo_clusters(self, n_clusters: int = 10) -> Dict[int, List[int]]:
        """
        사진들을 시각적 유사도로 클러스터링
        (자동 앨범 생성용)
        """
        if not self.faiss_index or len(self.id_mapping) < n_clusters:
            return {}
        
        try:
            # 모든 벡터 가져오기
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, clip_vector FROM images WHERE clip_vector IS NOT NULL")
                rows = cursor.fetchall()
            
            vectors = []
            ids = []
            for row in rows:
                vectors.append(np.frombuffer(row[1], dtype=np.float32))
                ids.append(row[0])
            
            vectors_np = np.array(vectors).astype('float32')
            
            # K-means 클러스터링
            kmeans = faiss.Kmeans(vectors_np.shape[1], n_clusters, niter=50)
            kmeans.train(vectors_np)
            
            # 각 이미지의 클러스터 할당
            _, labels = kmeans.index.search(vectors_np, 1)
            
            clusters = {}
            for img_id, label in zip(ids, labels.flatten()):
                label = int(label)
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(img_id)
            
            return clusters
            
        except Exception as e:
            logging.error(f"클러스터링 오류: {e}")
            return {}


class VisualRecommender:
    """추천 시스템 (확장용)"""
    
    def __init__(self, visual_search: VisualSearchEngine):
        self.visual_search = visual_search
    
    def get_daily_memories(self, date: str) -> List[Dict]:
        """특정 날짜의 추억 (On this day)"""
        pass
    
    def get_best_of_year(self, year: int, top_k: int = 50) -> List[Dict]:
        """연도별 베스트 사진"""
        pass
    
    def get_location_highlights(self, location: str) -> List[Dict]:
        """장소별 하이라이트"""
        pass
