import anthropic
import json
import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, Optional

load_dotenv()

class QueryParser:
    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.current_year = datetime.now().year
    
    def get_coordinates(self, location_name: str) -> Optional[Dict]:
        """Geocoding: 장소명 → GPS 좌표 변환"""
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': location_name,
            'format': 'json',
            'limit': 1
        }
        headers = {'User-Agent': 'PictaApp/1.0'}
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=3)
            data = response.json()
            
            if data:
                major_cities = ['뉴욕', 'new york', '서울', 'seoul', '부산', 'busan',
                               '도쿄', 'tokyo', '라스베가스', 'las vegas', '파리', 'paris',
                               '런던', 'london', '로스앤젤레스', 'los angeles']
                
                radius = 20 if any(city in location_name.lower() for city in major_cities) else 5
                
                return {
                    'lat': float(data[0]['lat']),
                    'lon': float(data[0]['lon']),
                    'radius_km': radius
                }
        except Exception as e:
            print(f"⚠️ Geocoding 실패 ({location_name}): {e}")
        
        return None
        
    def parse_query(self, user_query: str) -> Dict:
        """Claude로 자연어 쿼리 파싱"""
        today_str = datetime.now().strftime("%Y년 %m월 %d일")
        prompt = f"""
현재 날짜: {today_str}
사용자 질문: "{user_query}"

사진 검색을 위한 파라미터를 추출해서 JSON으로만 응답하세요:
{{
    "intent": "search_photos",
    "time_range": {{
        "start": "YYYY-MM-DD 또는 null",
        "end": "YYYY-MM-DD 또는 null"
    }},
    "location_names": ["장소명1", "장소명2"],
    "indoor_outdoor": "outdoor 또는 indoor 또는 null",
    "keywords": ["한국어 키워드들"],
    "people": ["언급된 사람들"],
    "search_text": "영어로 된 이미지 검색 쿼리"
}}

시간 해석 규칙:
- 작년 = 2024년
- 작년 여름 = 2024-06-01 ~ 2024-08-31
- "몇년 전" = 최근 5년 (2020-01-01 ~ 현재)
- "예전에", "옛날에" = null (필터 없음)
- 올해 = 2025년
- 6월 = 해당 월의 1일~말일

위치 추출 시:
- 언급된 장소명을 모두 배열로 추출
- 원본명 + 영문명 + 상위 지역 모두 포함
- 예: "광안리" → ["광안리", "Gwangalli", "부산", "Busan"]
- 예: "라스베가스" → ["라스베가스", "Las Vegas", "네바다", "Nevada"]
- 예: "클로이스터스" → ["클로이스터스", "Cloisters", "뉴욕", "New York"]

**매우 중요 - search_text 규칙**:
- search_text에는 장소명을 절대 포함하지 말 것!
- 위치는 이미 location_names로 별도 처리됨
- 오직 사물, 행동, 분위기만 포함

예시:
- "작년 여름 파스타" → 
  time_range: {{"start": "2024-06-01", "end": "2024-08-31"}}
  search_text: "pasta italian food"

- "뉴욕에서 먹은 스테이크" → 
  location_names: ["뉴욕", "New York", "맨해튼", "Manhattan"]
  search_text: "steak beef grilled meat restaurant food"  (뉴욕 제외!)

- "광안리 해변 사진" → 
  location_names: ["광안리", "Gwangalli", "부산", "Busan"]
  search_text: "beach ocean sunset waves"  (광안리 제외!)

- "엄마랑 찍은 사진" → 
  people: ["엄마"]
  search_text: "family portrait person together"
"""
        
        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=300,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Claude 응답에서 JSON 추출
            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            result = json.loads(text)
            
            # Claude가 추출한 장소명을 좌표로 변환
            if result.get('location_names'):
                location_data = {
                    'names': result['location_names'],
                    'coordinates': None
                }
                
                # [수정] 영문명 우선 검색 - 좌표 검색용 장소 선택
                location_for_coords = None
                
                # 1순위: 영문 도시명 찾기
                for name in result['location_names']:
                    # 영문명인지 확인 (ASCII 문자로만 구성)
                    if name.isascii() and len(name) > 2:
                        # 주요 도시 영문명 우선
                        if any(city in name.lower() for city in ['new york', 'las vegas', 'los angeles', 'paris', 'london', 'tokyo', 'seoul', 'busan']):
                            location_for_coords = name
                            break
                
                # 2순위: 아무 영문명이나
                if not location_for_coords:
                    for name in result['location_names']:
                        if name.isascii() and len(name) > 2:
                            location_for_coords = name
                            break
                
                # 3순위: 그냥 첫 번째 이름
                if not location_for_coords:
                    location_for_coords = result['location_names'][0]
                
                coords = self.get_coordinates(location_for_coords)

                if coords:
                    location_data['coordinates'] = coords
                    print(f"📍 '{location_for_coords}' → GPS: {coords['lat']:.4f}, {coords['lon']:.4f}")
                
                result['location'] = location_data
                del result['location_names']
            
            return result
            
        except Exception as e:
            print(f"Claude 파싱 실패: {e}")
            return self._fallback_parse(user_query)
    
    def _fallback_parse(self, user_query: str) -> Dict:
        """Claude 실패시 간단한 규칙 기반 파싱"""
        result = {
            'intent': 'search_photos',
            'keywords': [],
            'time_range': {'start': None, 'end': None},
            'people': [],
            'search_text': user_query,
            'location': None
        }
        
        if '작년 여름' in user_query:
            result['time_range'] = {
                'start': '2024-06-01',
                'end': '2024-08-31'
            }
        elif '작년' in user_query:
            result['time_range'] = {
                'start': '2024-01-01',
                'end': '2024-12-31'
            }
        
        if '파스타' in user_query:
            result['search_text'] = 'pasta italian food'
        
        if '엄마' in user_query:
            result['people'].append('엄마')
            
        return result
