import os
import io
import tempfile
import logging
from typing import List, Dict, Optional, Generator
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pickle

# Google Drive API 범위
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class GoogleDriveLoader:
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.pickle"):
        """
        Google Drive 로더 초기화
        
        Args:
            credentials_path: Google Cloud Console에서 다운받은 credentials.json 경로
            token_path: 인증 토큰 저장 경로
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        
        # 임시 폴더 (인코딩 후 삭제)
        import tempfile
        self.download_dir = tempfile.mkdtemp(prefix="picta_gdrive_")
        
        logging.info(f"📁 임시 다운로드 폴더: {self.download_dir}")
    
    def authenticate(self) -> bool:
        """Google Drive API 인증"""
        creds = None
        
        # 기존 토큰 확인
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # 토큰이 없거나 만료됐으면 재인증
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logging.warning(f"토큰 갱신 실패: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_path):
                    logging.error(f"❌ {self.credentials_path} 파일이 없습니다!")
                    logging.error("   Google Cloud Console에서 OAuth 2.0 credentials를 다운로드하세요.")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # 토큰 저장
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('drive', 'v3', credentials=creds)
        logging.info("✅ Google Drive 인증 성공!")
        return True
    
    def list_photos(self, folder_id: str = None, limit: int = None) -> List[Dict]:
        """
        Google Drive에서 사진 목록 가져오기
        
        Args:
            folder_id: 특정 폴더 ID (None이면 전체 드라이브)
            limit: 최대 사진 수
        """
        if not self.service:
            logging.error("인증이 필요합니다. authenticate()를 먼저 호출하세요.")
            return []
        
        # 이미지 파일만 필터링
        query = "mimeType contains 'image/' and trashed = false"
        if folder_id:
            query += f" and '{folder_id}' in parents"
        
        photos = []
        page_token = None
        
        while True:
            try:
                results = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, createdTime, imageMediaMetadata)',
                    pageToken=page_token,
                    pageSize=100
                ).execute()
                
                items = results.get('files', [])
                
                for item in items:
                    photo_info = {
                        'id': item['id'],
                        'name': item['name'],
                        'mimeType': item['mimeType'],
                        'createdTime': item.get('createdTime'),
                        'metadata': item.get('imageMediaMetadata', {})
                    }
                    photos.append(photo_info)
                    
                    if limit and len(photos) >= limit:
                        return photos
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
                    
            except Exception as e:
                logging.error(f"사진 목록 조회 실패: {e}")
                break
        
        return photos
    
    def download_photo(self, file_id: str, file_name: str) -> Optional[str]:
        """
        사진 다운로드 (영구 폴더에)
        
        Returns:
            다운로드된 파일 경로 또는 None
        """
        if not self.service:
            return None
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            # 파일 경로 생성
            local_path = os.path.join(self.download_dir, f"{file_id}_{file_name}")
            
            # 이미 다운로드됐으면 스킵
            if os.path.exists(local_path):
                return local_path
            
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            # 파일 저장
            with open(local_path, 'wb') as f:
                f.write(fh.getvalue())
            
            return local_path
            
        except Exception as e:
            logging.error(f"다운로드 실패 ({file_name}): {e}")
            return None
    
    def get_photo_metadata(self, photo_info: Dict) -> Dict:
        """
        Google Drive 사진 메타데이터를 Picta 형식으로 변환
        """
        metadata = {
            'taken_date': None,
            'gps_lat': None,
            'gps_lon': None,
            'location_name': None,
            'source': 'google_drive',
            'gdrive_id': photo_info['id']
        }
        
        # 날짜 추출
        if photo_info.get('createdTime'):
            try:
                dt = datetime.fromisoformat(photo_info['createdTime'].replace('Z', '+00:00'))
                metadata['taken_date'] = dt.isoformat()
            except:
                pass
        
        # GPS 정보 추출 (imageMediaMetadata에 있는 경우)
        img_meta = photo_info.get('metadata', {})
        if img_meta.get('location'):
            loc = img_meta['location']
            metadata['gps_lat'] = loc.get('latitude')
            metadata['gps_lon'] = loc.get('longitude')
        
        return metadata
    
    def iter_photos(self, limit: int = None, folder_id: str = None) -> Generator[Dict, None, None]:
        """
        사진을 하나씩 다운로드하며 반환하는 제너레이터
        (인코딩 후 파일 삭제 - 용량 절약)
        
        Args:
            limit: 최대 사진 수
            folder_id: 특정 폴더 ID (None이면 전체 드라이브)
        
        Yields:
            {'path': 로컬경로, 'metadata': 메타데이터, 'original_name': 원본파일명, 'delete_after': True}
        """
        photos = self.list_photos(folder_id=folder_id, limit=limit)
        logging.info(f"📷 Google Drive에서 {len(photos)}장의 사진 발견")
        
        for photo in photos:
            local_path = self.download_photo(photo['id'], photo['name'])
            
            if local_path:
                yield {
                    'path': local_path,
                    'metadata': self.get_photo_metadata(photo),
                    'original_name': photo['name'],
                    'delete_after': True  # 인코딩 후 삭제 플래그
                }
    
    def delete_file(self, file_path: str):
        """파일 삭제"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logging.warning(f"파일 삭제 실패: {e}")
    
    def cleanup(self):
        """임시 폴더 정리"""
        import shutil
        try:
            if os.path.exists(self.download_dir):
                shutil.rmtree(self.download_dir)
                logging.info(f"🧹 임시 폴더 삭제: {self.download_dir}")
        except Exception as e:
            logging.warning(f"폴더 삭제 실패: {e}")


# 테스트용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    loader = GoogleDriveLoader()
    
    if loader.authenticate():
        photos = loader.list_photos(limit=10)
        print(f"\n발견된 사진 {len(photos)}장:")
        for p in photos[:5]:
            print(f"  - {p['name']}")
