import openai
from typing import List, Dict
from datetime import datetime
import os

class ResponseGenerator:
    def __init__(self):
        openai.api_key = os.getenv("OPENAI_API_KEY")
    
    def generate_response(self, 
                         query: str, 
                         search_results: List[Dict],
                         use_simple: bool = True) -> str:
        """검색 결과를 자연스러운 대화로 변환"""
        
        if not search_results:
            return self._no_results_response()
        
        if use_simple:
            # 템플릿 기반 응답 (빠르고 저렴)
            return self._template_response(search_results)
        else:
            # GPT 기반 응답 (자연스럽지만 비용)
            return self._gpt_response(query, search_results)
    
    def _template_response(self, results: List[Dict]) -> str:
        """템플릿 기반 간단한 응답"""
        count = len(results)
        
        if count == 1:
            result = results[0]
            date = self._format_date(result.get('taken_date'))
            location = result.get('location_name')
            
            if date and location:
                return f"찾았어요! 📸 {date}에 {location}에서 찍은 사진이에요."
            elif date:
                return f"찾았어요! 📸 {date}에 찍은 사진이에요."
            elif location:
                return f"찾았어요! 📸 {location}에서 찍은 사진이에요."
            else:
                return "찾았어요! 📸"
        else:
            return f"{count}장의 사진을 찾았어요! 🎉"
    
    def _gpt_response(self, query: str, results: List[Dict]) -> str:
        """GPT를 사용한 자연스러운 응답"""
        # 검색 결과 요약
        results_summary = []
        for r in results[:5]:
            summary = {
                'date': r.get('taken_date'),
                'location': r.get('location_name'),
                'similarity': r.get('similarity', 0)
            }
            results_summary.append(summary)
        
        prompt = f"""
        사용자가 사진을 찾고 있습니다.
        
        사용자 질문: "{query}"
        
        검색 결과:
        {results_summary}
        
        친근하고 도움이 되는 톤으로 응답해주세요.
        이모지를 적절히 사용하고, 구체적인 정보를 포함하세요.
        2-3문장으로 간단하게 응답하세요.
        """
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a friendly photo assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"GPT 응답 생성 실패: {e}")
            return self._template_response(results)
    
    def _no_results_response(self) -> str:
        """검색 결과 없을 때"""
        return """아쉽게도 찾는 사진을 발견하지 못했어요. 😅
다른 키워드로 검색해보시겠어요?"""
    
    def _format_date(self, date_str: str) -> str:
        """날짜 포맷팅"""
        try:
            date = datetime.fromisoformat(date_str)
            return date.strftime('%Y년 %m월 %d일')
        except:
            return date_str