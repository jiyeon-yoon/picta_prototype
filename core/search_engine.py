import numpy as np
import sqlite3
import faiss
from typing import List, Dict, Optional
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
import json
import logging

class SearchEngine:
    def __init__(self, db_path: str, clip_processor, face_detector):
        self.db_path = db_path
        self.clip_processor = clip_processor
        self.face_detector = face_detector
        
        # FAISS 인덱스
        self.faiss_index = None
        self.id_mapping = []  # FAISS 인덱스 위치 -> image_id 매핑
        
        # 벡터 차원 (clip_processor에서 가져옴)
        self.vector_dim = getattr(clip_processor, 'vector_dim', 768)
        
        # [추가] 쿼리 유형별 동적 임계값
        self.thresholds = {
            'default': 0.26,
            'food': 0.24,        # 음식은 조금 더 관대하게
            'person': 0.28,     # 사람은 좀 더 엄격하게
            'place': 0.25,      # 장소
            'activity': 0.25,   # 활동
        }
        
        # 초기 FAISS 인덱스 빌드
        self._build_faiss_index()
    
    def _build_faiss_index(self):
        """FAISS 인덱스 구축"""
        logging.info("🔨 FAISS 인덱스 구축 중...")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, clip_vector FROM images WHERE clip_vector IS NOT NULL
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                logging.warning("인덱싱할 이미지가 없습니다.")
                return
            
            # 벡터 수집
            vectors = []
            self.id_mapping = []
            
            for image_id, vector_bytes in rows:
                vector = np.frombuffer(vector_bytes, dtype=np.float32)
                
                # 벡터 차원 검증
                if len(vector) != self.vector_dim:
                    logging.warning(f"이미지 {image_id}: 벡터 차원 불일치 ({len(vector)} != {self.vector_dim})")
                    continue
                
                vectors.append(vector)
                self.id_mapping.append(image_id)
            
            if not vectors:
                logging.warning("유효한 벡터가 없습니다.")
                return
            
            # numpy 배열로 변환
            vectors_array = np.array(vectors, dtype=np.float32)
            
            # FAISS 인덱스 생성 (Inner Product = Cosine Similarity for normalized vectors)
            self.faiss_index = faiss.IndexFlatIP(self.vector_dim)
            self.faiss_index.add(vectors_array)
            
            logging.info(f"✅ FAISS 인덱스 구축 완료: {len(self.id_mapping)}개 벡터")
    
    def rebuild_index(self):
        """인덱스 재구축 (새 이미지 추가 후 호출)"""
        self._build_faiss_index()
    
    def _get_dynamic_threshold(self, search_text: str) -> float:
        """[추가] 검색 텍스트 기반 동적 임계값 결정"""
        search_lower = search_text.lower()
        
        # 음식 관련 키워드
        food_keywords = ['food', 'meal', 'eat', 'restaurant', 'pasta', 'pizza', 
                        'steak', 'sushi', 'coffee', 'cake', 'dessert', 'lunch', 
                        'dinner', 'breakfast', 'burger', 'hamburger', 'ramen', 'noodle']
        if any(kw in search_lower for kw in food_keywords):
            return self.thresholds['food']
        
        # 사람 관련 키워드
        person_keywords = ['person', 'people', 'family', 'friend', 'portrait', 
                          'selfie', 'group', 'face', 'man', 'woman', 'child']
        if any(kw in search_lower for kw in person_keywords):
            return self.thresholds['person']
        
        # 장소 관련 키워드
        place_keywords = ['beach', 'mountain', 'city', 'park', 'building', 
                         'street', 'ocean', 'lake', 'forest', 'bridge', 'casino']
        if any(kw in search_lower for kw in place_keywords):
            return self.thresholds['place']
        
        # 활동 관련 키워드
        activity_keywords = ['walking', 'running', 'swimming', 'playing', 
                            'dancing', 'singing', 'cooking', 'reading', 'travel']
        if any(kw in search_lower for kw in activity_keywords):
            return self.thresholds['activity']
        
        return self.thresholds['default']
    
    def search(self, parsed_query: Dict, top_k: int = 10) -> List[Dict]:
        """통합 검색 실행"""
        results = []
        
        # 1. 날짜 필터링
        date_filtered = self._filter_by_date(
            parsed_query.get('time_range', {})
        )
        
        # 2. 위치 필터링 (하이브리드: GPS + 문자열)
        location_filtered = None
        if parsed_query.get('location'):
            location_filtered = self._filter_by_location_hybrid(
                date_filtered,
                parsed_query['location']
            )
        
        # 🔥 위치만 검색인지 판단 (키워드 없음)
        has_location = parsed_query.get('location') is not None
        
        # 🔥 위치 관련 키워드는 제외하고 판단
        keywords = parsed_query.get('keywords', [])
        location_names = []
        if has_location and parsed_query.get('location'):
            location_names = parsed_query['location'].get('names', [])
        
        # 위치/여행 관련 일반 키워드 (이런 건 CLIP 검색 안 해도 됨)
        generic_keywords = ['여행', 'travel', '풍경', 'landscape', 'scenic', '관광', 'tour', 
                           'trip', 'vacation', '사진', 'photo', 'picture', 'image',
                           'nature', '자연', 'view', '뷰', '경치', 'island', '섬']
        
        # 실제 의미있는 키워드만 필터링
        meaningful_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            # 위치명이 포함된 키워드 제외 (예: "제주 여행")
            is_location_related = any(loc.lower() in kw_lower for loc in location_names)
            # 일반 여행/풍경 키워드 제외
            is_generic = any(g in kw_lower for g in generic_keywords)
            
            if not is_location_related and not is_generic:
                meaningful_keywords.append(kw)
        
        has_keywords = len(meaningful_keywords) > 0
        
        logging.info(f"🔍 has_location: {has_location}, has_keywords: {has_keywords}")
        logging.info(f"🔍 원본 keywords: {keywords}")
        logging.info(f"🔍 의미있는 keywords: {meaningful_keywords}")
        
        # 3. 검색 분기
        if has_location and not has_keywords:
            # 🔥 위치만 검색 → CLIP 스킵, GPS 결과 바로 반환
            logging.info(f"📍 위치만 검색 - CLIP 스킵, {len(location_filtered)}장 중 {top_k}장 반환")
            
            if location_filtered:
                # 최신순 정렬
                sorted_ids = self._sort_by_date_desc(location_filtered, top_k)
                results = [{'id': id, 'similarity': 1.0} for id in sorted_ids]
            else:
                results = []
        
        elif parsed_query.get('search_text'):
            # 위치+키워드 또는 키워드만 검색 → CLIP 사용
            candidate_ids = location_filtered if location_filtered else date_filtered
            
            clip_results = self._search_by_clip_faiss(
                parsed_query['search_text'],
                candidate_ids=candidate_ids
            )
            
            # 동적 임계값 적용
            threshold = self._get_dynamic_threshold(parsed_query['search_text'])
            logging.info(f"📊 적용된 유사도 임계값: {threshold}")
            
            filtered_results = [r for r in clip_results if r['similarity'] > threshold]
            
            # 임계값 통과하는 결과 없으면
            if not filtered_results and clip_results:
                # 최소 0.20 이상일 때만 1등 반환
                if clip_results[0]['similarity'] >= 0.20:
                    results = clip_results[:1]
                else:
                    results = []  # 너무 낮으면 결과 없음
            else:
                results = filtered_results[:top_k]
        else:
            results = [{'id': id, 'similarity': 0} for id in date_filtered[:top_k]]
        
        # 4. 사람 필터링
        if parsed_query.get('people'):
            results = self._filter_by_people(
                results,
                parsed_query['people']
            )
        
        # 5. 결과 정보 보강
        return self._enrich_results(results)
    
    def _sort_by_date_desc(self, ids: List[int], limit: int) -> List[int]:
        """🔥 날짜 내림차순 정렬 (최신순)"""
        if not ids:
            return []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(ids))
            cursor.execute(f"""
                SELECT id FROM images 
                WHERE id IN ({placeholders})
                ORDER BY taken_date DESC
                LIMIT ?
            """, ids + [limit])
            return [row[0] for row in cursor.fetchall()]
    
    def _filter_by_date(self, time_range: Dict) -> List[int]:
        """날짜로 필터링"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = "SELECT id FROM images WHERE 1=1"
            params = []
            
            if time_range.get('start'):
                query += " AND taken_date >= ?"
                params.append(time_range['start'])
            
            if time_range.get('end'):
                query += " AND taken_date <= ?"
                params.append(f"{time_range['end']} 23:59:59")
            
            cursor.execute(query, params)
            return [row[0] for row in cursor.fetchall()]
    
    def _filter_by_location_hybrid(self, candidate_ids: List[int], location_data: Dict) -> List[int]:
        """GPS + 문자열 매칭 하이브리드 위치 필터링"""
        if not candidate_ids:
            return []
        
        gps_filtered = self._filter_by_gps(candidate_ids, location_data)
        string_filtered = self._filter_by_location_name(candidate_ids, location_data)
        
        combined = list(set(gps_filtered + string_filtered))
        
        print(f"📍 위치 필터링 결과:")
        print(f"   GPS 반경: {len(gps_filtered)}장")
        print(f"   문자열 매칭: {len(string_filtered)}장")
        print(f"   합계: {len(combined)}장")
        
        return combined
    
    def _filter_by_gps(self, candidate_ids: List[int], location_data: Dict) -> List[int]:
        """GPS 좌표 반경 내 사진만"""
        if not candidate_ids or not location_data.get('coordinates'):
            return []
        
        coords = location_data['coordinates']
        target_lat = coords['lat']
        target_lon = coords['lon']
        radius_km = coords.get('radius_km', 5)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            placeholders = ','.join('?' * len(candidate_ids))
            
            query = f"""
                SELECT id, gps_lat, gps_lon 
                FROM images 
                WHERE id IN ({placeholders})
                AND gps_lat IS NOT NULL 
                AND gps_lon IS NOT NULL
            """
            
            cursor.execute(query, candidate_ids)
            
            filtered_ids = []
            for row in cursor.fetchall():
                image_id, lat, lon = row
                distance = self._haversine_distance(target_lat, target_lon, lat, lon)
                
                if distance <= radius_km:
                    filtered_ids.append(image_id)
            
            return filtered_ids
    
    def _normalize_korean_location(self, name: str) -> List[str]:
        """🔥 한국 지역명 정규화 - 여러 변형 생성
        제주 = 제주도 = 제주시
        부산 = 부산시 = 부산광역시
        서울 = 서울시 = 서울특별시
        """
        variants = [name]
        
        # 접미사 목록 (긴 것부터)
        suffixes = ['특별자치도', '특별자치시', '광역시', '특별시', '자치도', '자치시', '도', '시', '군', '구']
        
        # 접미사 제거한 버전 추가
        base_name = name
        for suffix in suffixes:
            if name.endswith(suffix) and len(name) > len(suffix):
                base_name = name[:-len(suffix)]
                variants.append(base_name)
                break
        
        # 기본 이름에 접미사 붙인 버전들 추가
        if base_name != name:
            # "제주" → "제주시", "제주도" 등
            for suffix in ['시', '도']:
                variant = base_name + suffix
                if variant not in variants:
                    variants.append(variant)
        
        return list(set(variants))
    
    def _filter_by_location_name(self, candidate_ids: List[int], location_data: Dict) -> List[int]:
        """문자열 매칭 (GPS 없는 사진 대비)"""
        if not candidate_ids:
            return []
            
        location_names = location_data.get('names', [])
        if not location_names:
            return []
        
        # 🔥 한국 지역명 정규화 적용
        all_variants = []
        for name in location_names[:2]:  # 상위 2개만
            variants = self._normalize_korean_location(name)
            all_variants.extend(variants)
        
        # 중복 제거
        all_variants = list(set(all_variants))
        logging.info(f"📍 위치 검색어 변형: {all_variants}")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            placeholders = ','.join('?' * len(candidate_ids))
            location_conditions = ' OR '.join(['location_name LIKE ?' for _ in all_variants])
            
            query = f"""
                SELECT id FROM images 
                WHERE id IN ({placeholders})
                AND location_name IS NOT NULL
                AND gps_lat IS NULL
                AND gps_lon IS NULL
                AND ({location_conditions})
            """
            
            params = candidate_ids + [f'%{name}%' for name in all_variants]
            cursor.execute(query, params)
            
            return [row[0] for row in cursor.fetchall()]
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """두 GPS 좌표 간 거리 계산 (km)"""
        R = 6371
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    def _search_by_clip_faiss(self, search_text: str, 
                              candidate_ids: Optional[List[int]] = None) -> List[Dict]:
        """[추가] FAISS를 사용한 고속 벡터 검색"""
        
        if self.faiss_index is None or len(self.id_mapping) == 0:
            logging.warning("FAISS 인덱스가 비어있습니다. 기존 방식으로 검색합니다.")
            return self._search_by_clip_legacy(search_text, candidate_ids)
        
        # 텍스트를 벡터로 변환
        text_vector = self.clip_processor.encode_text(search_text)
        text_vector = text_vector.reshape(1, -1).astype(np.float32)
        
        # FAISS 검색 (전체에서 top-k 가져옴)
        k = min(100, self.faiss_index.ntotal)
        similarities, indices = self.faiss_index.search(text_vector, k)
        
        results = []
        for sim, idx in zip(similarities[0], indices[0]):
            if idx < 0:
                continue
                
            image_id = self.id_mapping[idx]
            
            # candidate_ids 필터링
            if candidate_ids is not None and image_id not in candidate_ids:
                continue
            
            results.append({
                'id': image_id,
                'file_path': None,
                'similarity': float(sim)
            })
        
        results.sort(key=lambda x: x['similarity'], reverse=True)
        
        return results
    
    def _search_by_clip_legacy(self, search_text: str, 
                               candidate_ids: Optional[List[int]] = None) -> List[Dict]:
        """기존 SQLite 기반 검색 (fallback)"""
        text_vector = self.clip_processor.encode_text(search_text)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if candidate_ids:
                placeholders = ','.join('?' * len(candidate_ids))
                query = f"""
                    SELECT id, file_path, clip_vector 
                    FROM images 
                    WHERE id IN ({placeholders})
                """
                cursor.execute(query, candidate_ids)
            else:
                cursor.execute("""
                    SELECT id, file_path, clip_vector 
                    FROM images 
                    WHERE clip_vector IS NOT NULL
                """)
            
            results = []
            for row in cursor.fetchall():
                image_id, file_path, clip_vector_bytes = row
                
                image_vector = np.frombuffer(clip_vector_bytes, dtype=np.float32)
                similarity = np.dot(text_vector, image_vector)
                
                results.append({
                    'id': image_id,
                    'file_path': file_path,
                    'similarity': float(similarity)
                })
            
            results.sort(key=lambda x: x['similarity'], reverse=True)
            
            return results
    
    def _filter_by_people(self, results: List[Dict], people: List[str]) -> List[Dict]:
        """사람으로 필터링"""
        if not results:
            return []
            
        filtered = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for result in results:
                placeholders = ','.join(['?'] * len(people))
                cursor.execute(f"""
                    SELECT person_name 
                    FROM faces 
                    WHERE image_id = ? AND person_name IN ({placeholders})
                """, [result['id']] + people)
                
                if cursor.fetchone():
                    filtered.append(result)
        
        return filtered
    
    def _enrich_results(self, results: List[Dict]) -> List[Dict]:
        """검색 결과에 메타데이터 추가"""
        if not results:
            return []
            
        enriched = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for result in results:
                cursor.execute("""
                    SELECT file_path, thumbnail_path, taken_date, 
                           location_name, metadata
                    FROM images 
                    WHERE id = ?
                """, (result['id'],))
                
                row = cursor.fetchone()
                if row:
                    enriched.append({
                        'id': result['id'],
                        'file_path': row[0],
                        'thumbnail_path': row[1],
                        'taken_date': row[2],
                        'location_name': row[3],
                        'metadata': json.loads(row[4]) if row[4] else {},
                        'similarity': result.get('similarity', 0)
                    })
        
        return enriched