"""
Picta Agent Tools
LangChain Agent가 사용하는 도구들
"""

import json
import logging
from typing import List, Dict, Any, Optional
from langchain.tools import Tool, StructuredTool
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class SearchPhotosInput(BaseModel):
    """사진 검색 입력"""
    query: str = Field(description="검색 쿼리 (자연어)")
    top_k: int = Field(default=20, description="반환할 최대 결과 수")


class FilterResultsInput(BaseModel):
    """결과 필터링 입력"""
    filter_type: str = Field(description="필터 타입: location, time, keyword")
    filter_value: str = Field(description="필터 값")


class FindSimilarInput(BaseModel):
    """유사 사진 검색 입력"""
    image_id: int = Field(description="기준 사진 ID")
    similarity_type: str = Field(
        default="visual",
        description="유사도 타입: visual(시각적), location(장소), time(시간)"
    )
    top_k: int = Field(default=10, description="반환할 최대 결과 수")


class GetPhotoInfoInput(BaseModel):
    """사진 정보 조회 입력"""
    image_id: int = Field(description="사진 ID")


class PhotoSearchTools:
    """Agent Tools 관리 클래스"""
    
    def __init__(self, search_engine, visual_search_engine, agent):
        """
        Args:
            search_engine: Picta SearchEngine 인스턴스
            visual_search_engine: VisualSearchEngine 인스턴스
            agent: PhotoAgent 인스턴스 (상태 업데이트용)
        """
        self.search_engine = search_engine
        self.visual_search_engine = visual_search_engine
        self.agent = agent
    
    def get_tools(self) -> List[Tool]:
        """Agent에서 사용할 Tool 리스트 반환"""
        return [
            StructuredTool.from_function(
                func=self.search_photos,
                name="search_photos",
                description="""사진을 검색합니다. 
                자연어 쿼리로 사진을 찾을 수 있습니다.
                예: "작년 여름 바다 사진", "뉴욕에서 먹은 스테이크", "파리 여행"
                """,
                args_schema=SearchPhotosInput
            ),
            StructuredTool.from_function(
                func=self.filter_results,
                name="filter_results",
                description="""이전 검색 결과를 추가 조건으로 필터링합니다.
                - location: 장소로 필터 (예: "서울", "강남")
                - time: 시간으로 필터 (예: "2023년", "작년")
                - keyword: 키워드로 필터 (예: "삼겹살", "케이크")
                """,
                args_schema=FilterResultsInput
            ),
            StructuredTool.from_function(
                func=self.find_similar,
                name="find_similar",
                description="""특정 사진과 유사한 사진을 찾습니다.
                - visual: 시각적으로 비슷한 사진 (분위기, 색감)
                - location: 같은 장소에서 찍은 사진
                - time: 같은 날/시기에 찍은 사진
                """,
                args_schema=FindSimilarInput
            ),
            StructuredTool.from_function(
                func=self.get_photo_info,
                name="get_photo_info",
                description="""사진의 상세 정보를 조회합니다.
                촬영 날짜, 장소, 메타데이터 등을 반환합니다.
                """,
                args_schema=GetPhotoInfoInput
            ),
        ]
    
    def search_photos(self, query: str, top_k: int = 20) -> str:
        """사진 검색 Tool"""
        try:
            # 쿼리 파싱
            from core.query_parser import QueryParser
            parser = QueryParser()
            parsed = parser.parse_query(query)
            
            logging.info(f"[Tool:search_photos] 쿼리: {query}")
            logging.info(f"[Tool:search_photos] 파싱 결과: {parsed}")
            
            # 검색 실행
            results = self.search_engine.search(parsed, top_k=top_k)
            
            # Agent 상태 업데이트
            self.agent.current_results = results
            
            if not results:
                return "검색 결과가 없습니다. 다른 키워드로 시도해보세요."
            
            # 결과 요약 생성
            summary = self._summarize_results(results)
            
            return f"""
{len(results)}장의 사진을 찾았습니다.

{summary}

사용자에게 결과를 자연스럽게 안내해주세요.
더 좁히고 싶다면 장소, 시간, 키워드로 필터링할 수 있습니다.
"""
            
        except Exception as e:
            logging.error(f"[Tool:search_photos] 오류: {e}")
            return f"검색 중 오류가 발생했습니다: {str(e)}"
    
    def filter_results(self, filter_type: str, filter_value: str) -> str:
        """결과 필터링 Tool"""
        try:
            if not self.agent.current_results:
                return "먼저 검색을 실행해주세요. 필터링할 결과가 없습니다."
            
            logging.info(f"[Tool:filter_results] 타입: {filter_type}, 값: {filter_value}")
            
            filtered = []
            filter_value_lower = filter_value.lower()
            
            for result in self.agent.current_results:
                if filter_type == "location":
                    location = (result.get("location_name") or "").lower()
                    if filter_value_lower in location:
                        filtered.append(result)
                        
                elif filter_type == "time":
                    date = result.get("taken_date") or ""
                    if filter_value in date:
                        filtered.append(result)
                        
                elif filter_type == "keyword":
                    # 이미 CLIP 유사도로 필터링
                    # 추가적인 키워드 필터링은 re-ranking으로 처리
                    filtered.append(result)
            
            if filter_type == "keyword" and filtered:
                # 키워드 기반 re-ranking
                filtered = self._rerank_by_keyword(filtered, filter_value)
            
            # 상태 업데이트
            self.agent.current_results = filtered
            
            if not filtered:
                return f"'{filter_value}' 조건에 맞는 사진이 없습니다."
            
            summary = self._summarize_results(filtered)
            
            return f"""
{len(filtered)}장으로 좁혀졌습니다.

{summary}
"""
            
        except Exception as e:
            logging.error(f"[Tool:filter_results] 오류: {e}")
            return f"필터링 중 오류가 발생했습니다: {str(e)}"
    
    def find_similar(self, image_id: int, similarity_type: str = "visual", top_k: int = 10) -> str:
        """유사 사진 검색 Tool"""
        try:
            logging.info(f"[Tool:find_similar] ID: {image_id}, 타입: {similarity_type}")
            
            if not self.visual_search_engine:
                return "유사 사진 검색 기능이 활성화되지 않았습니다."
            
            if similarity_type == "visual":
                results = self.visual_search_engine.find_similar_by_image(image_id, top_k)
            elif similarity_type == "location":
                results = self.visual_search_engine.find_by_same_location(image_id, top_k)
            elif similarity_type == "time":
                results = self.visual_search_engine.find_by_same_date(image_id, top_k)
            else:
                results = self.visual_search_engine.find_similar_by_image(image_id, top_k)
            
            # 상태 업데이트
            self.agent.current_results = results
            
            if not results:
                return "유사한 사진을 찾지 못했습니다."
            
            summary = self._summarize_results(results)
            type_desc = {
                "visual": "비슷한 분위기의",
                "location": "같은 장소에서 찍은",
                "time": "같은 날 찍은"
            }.get(similarity_type, "유사한")
            
            return f"""
{type_desc} 사진 {len(results)}장을 찾았습니다.

{summary}
"""
            
        except Exception as e:
            logging.error(f"[Tool:find_similar] 오류: {e}")
            return f"유사 사진 검색 중 오류가 발생했습니다: {str(e)}"
    
    def get_photo_info(self, image_id: int) -> str:
        """사진 정보 조회 Tool"""
        try:
            logging.info(f"[Tool:get_photo_info] ID: {image_id}")
            
            # DB에서 사진 정보 조회
            import sqlite3
            
            # DB 경로 (search_engine에서 가져오기)
            db_path = self.search_engine.db_path
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, file_path, taken_date, location_name, gps_lat, gps_lon
                    FROM images WHERE id = ?
                """, (image_id,))
                row = cursor.fetchone()
            
            if not row:
                return f"ID {image_id}인 사진을 찾을 수 없습니다."
            
            id, file_path, taken_date, location_name, gps_lat, gps_lon = row
            
            # Agent 상태 업데이트
            self.agent.selected_photo = {
                "id": id,
                "file_path": file_path,
                "taken_date": taken_date,
                "location_name": location_name,
                "gps_lat": gps_lat,
                "gps_lon": gps_lon
            }
            
            info_parts = [f"📷 사진 정보 (ID: {id})"]
            
            if taken_date:
                info_parts.append(f"📅 촬영일: {taken_date}")
            if location_name:
                info_parts.append(f"📍 장소: {location_name}")
            if gps_lat and gps_lon:
                info_parts.append(f"🌍 좌표: {gps_lat:.4f}, {gps_lon:.4f}")
            
            return "\n".join(info_parts)
            
        except Exception as e:
            logging.error(f"[Tool:get_photo_info] 오류: {e}")
            return f"사진 정보 조회 중 오류가 발생했습니다: {str(e)}"
    
    def _summarize_results(self, results: List[Dict]) -> str:
        """검색 결과 요약 생성"""
        if not results:
            return ""
        
        # 날짜 범위
        dates = [r.get("taken_date") for r in results if r.get("taken_date")]
        date_info = ""
        if dates:
            dates_sorted = sorted(dates)
            if len(dates) == 1:
                date_info = f"📅 {dates_sorted[0]}"
            else:
                date_info = f"📅 {dates_sorted[0]} ~ {dates_sorted[-1]}"
        
        # 장소들
        locations = set()
        for r in results:
            loc = r.get("location_name")
            if loc:
                # 첫 번째 지역명만 추출
                first_loc = loc.split(",")[0].strip()
                locations.add(first_loc)
        
        location_info = ""
        if locations:
            loc_list = list(locations)[:5]  # 최대 5개
            location_info = f"📍 {', '.join(loc_list)}"
            if len(locations) > 5:
                location_info += f" 외 {len(locations)-5}곳"
        
        # 유사도 범위
        similarities = [r.get("similarity", 0) for r in results]
        if similarities:
            avg_sim = sum(similarities) / len(similarities)
            sim_info = f"🎯 평균 유사도: {avg_sim:.1%}"
        else:
            sim_info = ""
        
        parts = [p for p in [date_info, location_info, sim_info] if p]
        return "\n".join(parts)
    
    def _rerank_by_keyword(self, results: List[Dict], keyword: str) -> List[Dict]:
        """키워드 기반 re-ranking (CLIP 유사도 재계산)"""
        try:
            if not hasattr(self.search_engine, 'clip'):
                return results
            
            # 키워드로 텍스트 벡터 생성
            text_vector = self.search_engine.clip.encode_text(keyword)
            
            # 각 결과의 유사도 재계산
            reranked = []
            for r in results:
                image_id = r.get("id")
                # 이미지 벡터 가져오기
                image_vector = self.search_engine._get_image_vector(image_id)
                if image_vector is not None:
                    import numpy as np
                    similarity = np.dot(text_vector, image_vector)
                    r["rerank_similarity"] = float(similarity)
                else:
                    r["rerank_similarity"] = r.get("similarity", 0)
                reranked.append(r)
            
            # 재정렬
            reranked.sort(key=lambda x: x["rerank_similarity"], reverse=True)
            
            return reranked
            
        except Exception as e:
            logging.error(f"Re-ranking 오류: {e}")
            return results
