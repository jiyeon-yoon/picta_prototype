"""
LangChain Agent for Picta - 자연어 쿼리 파싱 및 대화형 검색
"""
import os
import logging
from typing import Dict, Any, Optional

try:
    from langchain_anthropic import ChatAnthropic
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain.tools import Tool
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning("LangChain 패키지가 설치되지 않았습니다.")


class LangChainAgent:
    """LangChain 기반 자연어 쿼리 파서"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.agent = None
        
        if not LANGCHAIN_AVAILABLE:
            logging.warning("LangChain을 사용할 수 없습니다.")
            return
        
        if not self.api_key:
            logging.warning("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
            return
        
        self._setup_agent()
    
    def _setup_agent(self):
        """Agent 설정"""
        try:
            self.llm = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                anthropic_api_key=self.api_key,
                max_tokens=1024
            )
            
            # 시스템 프롬프트
            self.system_prompt = """당신은 사진 검색 AI 어시스턴트입니다.
사용자의 자연어 질문을 분석하여 검색 조건을 추출합니다.

다음 정보를 추출하세요:
- keywords: 검색할 키워드 (영어로 변환)
- location: 위치 정보 (도시명, 장소명)
- time_range: 시간 범위 (start, end)
- people: 사람 이름

예시:
"작년 여름 제주도 여행 사진" → keywords: ["beach", "ocean", "travel"], location: "Jeju", time_range: {start: "2024-06-01", end: "2024-08-31"}
"엄마랑 찍은 사진" → keywords: ["family", "mother"], people: ["엄마"]
"""
            
            logging.info("✅ LangChain Agent 초기화 완료")
            
        except Exception as e:
            logging.error(f"LangChain Agent 초기화 실패: {e}")
            self.llm = None
    
    def parse_query(self, query: str) -> Dict[str, Any]:
        """자연어 쿼리를 검색 조건으로 변환"""
        
        if not self.llm:
            return self._fallback_parse(query)
        
        try:
            prompt = f"""사용자 쿼리: "{query}"

위 쿼리를 분석하여 다음 JSON 형식으로 응답하세요:
{{
    "intent": "search_photos",
    "keywords": ["키워드1", "키워드2"],  // 영어로
    "location": {{"name": "장소명", "names": ["장소명", "도시명"]}},  // 위치 정보가 있으면
    "time_range": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}},  // 시간이 있으면
    "people": ["사람1"],  // 사람이 있으면
    "search_text": "영어로 변환된 검색 텍스트"
}}

JSON만 응답하세요."""

            response = self.llm.invoke(prompt)
            
            # JSON 파싱
            import json
            content = response.content
            
            # JSON 부분 추출
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            logging.info(f"🤖 LangChain 파싱 결과: {result}")
            return result
            
        except Exception as e:
            logging.error(f"LangChain 파싱 실패: {e}")
            return self._fallback_parse(query)
    
    def _fallback_parse(self, query: str) -> Dict[str, Any]:
        """폴백 파싱 (LangChain 없을 때)"""
        return {
            "intent": "search_photos",
            "keywords": [],
            "time_range": {"start": None, "end": None},
            "people": [],
            "search_text": query,
            "location": None
        }
    
    def generate_response(self, query: str, results: list) -> str:
        """검색 결과 기반 응답 생성"""
        
        if not self.llm:
            return self._fallback_response(results)
        
        try:
            if not results:
                return "조건에 맞는 사진을 찾지 못했어요. 다른 키워드로 검색해보세요!"
            
            # 결과 요약
            top_result = results[0]
            date = top_result.get('taken_date', '')[:10] if top_result.get('taken_date') else ''
            location = top_result.get('location_name', '')
            
            prompt = f"""사용자 질문: "{query}"
검색 결과: {len(results)}장의 사진
첫 번째 사진: 날짜 {date}, 장소 {location}

위 정보를 바탕으로 친근하고 자연스러운 한국어 응답을 생성하세요.
이모지를 적절히 사용하고, 2-3문장으로 짧게 답변하세요."""

            response = self.llm.invoke(prompt)
            return response.content
            
        except Exception as e:
            logging.error(f"응답 생성 실패: {e}")
            return self._fallback_response(results)
    
    def _fallback_response(self, results: list) -> str:
        """폴백 응답 생성"""
        if not results:
            return "조건에 맞는 사진을 찾지 못했어요."
        
        top = results[0]
        date = top.get('taken_date', '')[:10] if top.get('taken_date') else '날짜 없음'
        location = top.get('location_name', '위치 없음')
        
        return f"찾았어요! 📸 {date}에 {location}에서 찍은 사진이에요."


# 싱글톤 인스턴스
_agent_instance = None

def get_langchain_agent() -> Optional[LangChainAgent]:
    """LangChain Agent 싱글톤 반환"""
    global _agent_instance
    
    if not LANGCHAIN_AVAILABLE:
        return None
    
    if _agent_instance is None:
        _agent_instance = LangChainAgent()
    
    return _agent_instance
