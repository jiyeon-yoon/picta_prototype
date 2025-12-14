"""
Picta Conversational Photo Agent
LangChain 기반 대화형 사진 검색 에이전트
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor
from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from .tools import PhotoSearchTools
from .prompts import SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO)


class PhotoAgent:
    """대화형 사진 검색 에이전트"""
    
    def __init__(self, search_engine, visual_search_engine=None):
        """
        Args:
            search_engine: 기존 Picta SearchEngine 인스턴스
            visual_search_engine: VisualSearchEngine 인스턴스 (유사 사진 검색용)
        """
        self.search_engine = search_engine
        self.visual_search_engine = visual_search_engine
        
        # LLM 초기화
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            temperature=0.3,
            max_tokens=2048
        )
        
        # 대화 메모리 (최근 10턴 유지)
        self.memory = ConversationBufferWindowMemory(
            k=10,
            memory_key="chat_history",
            return_messages=True
        )
        
        # 현재 검색 상태
        self.current_results = []
        self.selected_photo = None
        
        # Tools 초기화
        self.tools_handler = PhotoSearchTools(
            search_engine=search_engine,
            visual_search_engine=visual_search_engine,
            agent=self
        )
        self.tools = self.tools_handler.get_tools()
        
        # Agent 생성
        self.agent = self._create_agent()
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5
        )
    
    def _create_agent(self):
        """LangChain Agent 생성"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        return create_tool_calling_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
    
    def chat(self, user_message: str) -> Dict[str, Any]:
        """
        사용자 메시지 처리
        
        Args:
            user_message: 사용자 입력
            
        Returns:
            {
                "response": AI 응답 텍스트,
                "results": 검색 결과 리스트,
                "recommendations": 추천 사진 (선택된 사진 있을 때),
                "action": 수행된 액션 타입
            }
        """
        try:
            # Agent 실행
            result = self.agent_executor.invoke({
                "input": user_message
            })
            
            response = result.get("output", "")
            
            return {
                "response": response,
                "results": self.current_results,
                "selected_photo": self.selected_photo,
                "recommendations": self._get_recommendations() if self.selected_photo else None,
                "action": self._detect_action(user_message)
            }
            
        except Exception as e:
            logging.error(f"Agent 오류: {e}")
            return {
                "response": f"죄송해요, 처리 중 오류가 발생했어요: {str(e)}",
                "results": [],
                "recommendations": None,
                "action": "error"
            }
    
    def _detect_action(self, message: str) -> str:
        """사용자 메시지에서 액션 타입 감지"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["비슷한", "유사한", "이런", "같은 느낌"]):
            return "find_similar"
        elif any(word in message_lower for word in ["좁혀", "필터", "그 중에", "만"]):
            return "filter"
        elif any(word in message_lower for word in ["찾아", "검색", "보여줘", "있어"]):
            return "search"
        elif any(word in message_lower for word in ["정보", "언제", "어디서"]):
            return "info"
        else:
            return "chat"
    
    def _get_recommendations(self) -> Optional[Dict]:
        """선택된 사진에 대한 추천 가져오기"""
        if not self.selected_photo or not self.visual_search_engine:
            return None
        
        try:
            return self.visual_search_engine.get_recommendations(
                self.selected_photo.get("id")
            )
        except Exception as e:
            logging.error(f"추천 생성 오류: {e}")
            return None
    
    def select_photo(self, photo_id: int) -> Dict[str, Any]:
        """사진 선택 (클릭)"""
        # 현재 결과에서 해당 사진 찾기
        for result in self.current_results:
            if result.get("id") == photo_id:
                self.selected_photo = result
                break
        
        recommendations = self._get_recommendations()
        
        return {
            "selected_photo": self.selected_photo,
            "recommendations": recommendations
        }
    
    def clear_selection(self):
        """선택 해제"""
        self.selected_photo = None
    
    def reset(self):
        """대화 초기화"""
        self.memory.clear()
        self.current_results = []
        self.selected_photo = None
    
    def get_conversation_history(self) -> List[Dict]:
        """대화 히스토리 반환"""
        messages = self.memory.chat_memory.messages
        history = []
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": msg.content})
        
        return history


class PhotoAgentSession:
    """세션 관리 (여러 사용자 지원)"""
    
    def __init__(self, search_engine, visual_search_engine=None):
        self.search_engine = search_engine
        self.visual_search_engine = visual_search_engine
        self.sessions: Dict[str, PhotoAgent] = {}
    
    def get_or_create_session(self, session_id: str) -> PhotoAgent:
        """세션 ID로 Agent 가져오기 (없으면 생성)"""
        if session_id not in self.sessions:
            self.sessions[session_id] = PhotoAgent(
                search_engine=self.search_engine,
                visual_search_engine=self.visual_search_engine
            )
        return self.sessions[session_id]
    
    def delete_session(self, session_id: str):
        """세션 삭제"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """오래된 세션 정리"""
        now = datetime.now()
        to_delete = []
        
        for session_id, agent in self.sessions.items():
            if hasattr(agent, 'last_active'):
                age = (now - agent.last_active).total_seconds() / 3600
                if age > max_age_hours:
                    to_delete.append(session_id)
        
        for session_id in to_delete:
            del self.sessions[session_id]
        
        return len(to_delete)