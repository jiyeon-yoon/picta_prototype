import os
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
# 한글 폰트 설정 (macOS)
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False
from PIL import Image
import numpy as np
import osxphotos
import sqlite3
from core.image_processor import CLIPImageProcessor
from core.face_detector import FaceDetector
from core.database import DatabaseManager
from core.query_parser import QueryParser
from core.search_engine import SearchEngine
from core.response_generator import ResponseGenerator
import logging


logging.basicConfig(level=logging.INFO)


class SimpleMetadataExtractor:
    def extract_metadata(self, photo_obj):
        """osxphotos 객체에서 메타데이터를 추출합니다."""
        
        taken_date = photo_obj.date.isoformat() if photo_obj.date else None
        
        gps_lat = photo_obj.location[0] if photo_obj.location else None
        gps_lon = photo_obj.location[1] if photo_obj.location else None
        
        location_name = photo_obj.place.name if photo_obj.place else None
        
        return {
            'taken_date': taken_date,
            'gps_lat': gps_lat,
            'gps_lon': gps_lon,
            'location_name': location_name,
            'source': 'mac_photos'
        }


def get_best_photo_path(photo):
    """사진의 최적 경로 반환: 원본 > derivatives 중 최대 파일"""
    
    # 1. 원본이 있으면 원본 사용
    if photo.path:
        return photo.path
    
    # 2. 원본 없으면 derivatives에서 가장 큰 파일 선택
    derivatives = photo.path_derivatives
    if not derivatives:
        return None
    
    best_path = None
    max_size = 0
    
    for deriv_path in derivatives:
        try:
            size = os.path.getsize(deriv_path)
            if size > max_size:
                max_size = size
                best_path = deriv_path
        except:
            continue
    
    return best_path


class PictaEngine:
    def __init__(self, image_folder: str = "data/images", db_path: str = "data/picta.db"):
        self.image_folder = image_folder
        self.db_path = db_path
        
        # 초기화
        logging.info(f"Picta 엔진 초기화 중... (DB: {db_path})")
        self.db = DatabaseManager(db_path=db_path)
        self.clip = CLIPImageProcessor()
        self.face = FaceDetector()
        self.metadata_extractor = SimpleMetadataExtractor()
        self.query_parser = QueryParser()
        self.search_engine = SearchEngine(
            db_path, 
            self.clip, 
            self.face
        )
        self.response_gen = ResponseGenerator()
        
        logging.info("초기화 완료!")
    
    def index_mac_photos(self, limit=1000):
        """Mac Photos Library에서 인덱싱"""
        
        try:
            photosdb = osxphotos.PhotosDB()
            photos = photosdb.photos()
        except Exception as e:
            logging.error(f"⚠️ Mac Photos Library 로드 실패: {e}")
            logging.info("일반 파일 시스템 인덱싱으로 전환합니다...")
            return self._fallback_index_images()

        logging.info(f"🚀 Mac Photos Library에서 {len(photos)}개 사진 발견. 인덱싱 시작.")
        
        processed_count = 0
        skipped_count = 0
        
        for photo in photos:
            if limit and processed_count >= limit:
                break
            
            # 동영상 제외
            if not photo.isphoto:
                continue
            
            # 스크린샷 제외
            filename = (photo.original_filename or '').lower()
            if 'screenshot' in filename or '스크린샷' in filename or 'screen shot' in filename:
                continue

            # 원본 또는 derivatives에서 최적 경로 가져오기
            path_str = get_best_photo_path(photo)
            
            if not path_str or not os.path.exists(path_str):
                skipped_count += 1
                if skipped_count <= 5:
                    logging.warning(f"사진 ID {photo.uuid}: 사용 가능한 파일이 없어 건너뜁니다.")
                continue

            try:
                # 메타데이터 추출
                metadata = self.metadata_extractor.extract_metadata(photo)
                
                # CLIP 벡터 생성
                clip_vector = self.clip.encode_image(path_str)
                
                # DB 저장
                image_id = self.db.save_image(path_str, clip_vector, metadata)
                
                processed_count += 1
                
                if processed_count % 50 == 0:
                    logging.info(f"처리 중 ({processed_count}/{limit}): {photo.original_filename}")
                
            except Exception as e:
                logging.error(f"이미지 처리 실패 {path_str}: {e}")
        
        if skipped_count > 5:
            logging.warning(f"총 {skipped_count}장의 사진을 건너뛰었습니다 (파일 없음)")
        
        # FAISS 인덱스 재구축
        self.search_engine.rebuild_index()
                
        logging.info(f"🎉 Mac Photos 인덱싱 완료! 총 {processed_count}장 처리")
        return processed_count

    def index_google_drive(self, limit=1000, folder_id=None):
        """Google Drive에서 인덱싱 (용량 절약 - 파일 삭제)"""
        try:
            from core.google_drive_loader import GoogleDriveLoader
        except ImportError:
            logging.error("❌ Google Drive 모듈을 불러올 수 없습니다.")
            logging.error("   pip install google-api-python-client google-auth-oauthlib")
            return 0
        
        loader = GoogleDriveLoader()
        
        # 인증
        if not loader.authenticate():
            logging.error("❌ Google Drive 인증 실패")
            return 0
        
        if folder_id:
            logging.info(f"🚀 Google Drive 폴더({folder_id}) 인덱싱 시작...")
        else:
            logging.info("🚀 Google Drive 전체 인덱싱 시작...")
        
        processed_count = 0
        
        try:
            for photo_data in loader.iter_photos(limit=limit, folder_id=folder_id):
                try:
                    path_str = photo_data['path']
                    metadata = photo_data['metadata']
                    
                    # CLIP 벡터 생성
                    clip_vector = self.clip.encode_image(path_str)
                    
                    # 파일 경로 대신 gdrive URL 저장
                    gdrive_id = metadata.get('gdrive_id')
                    gdrive_url = f"gdrive://{gdrive_id}"
                    
                    # DB 저장 (경로에 gdrive:// 프로토콜 사용)
                    self.db.save_image(gdrive_url, clip_vector, metadata)
                    
                    # 인코딩 후 파일 삭제 (용량 절약)
                    if photo_data.get('delete_after'):
                        loader.delete_file(path_str)
                    
                    processed_count += 1
                    
                    if processed_count % 50 == 0:
                        logging.info(f"처리 중 ({processed_count}/{limit}): {photo_data['original_name']}")
                    
                except Exception as e:
                    logging.error(f"이미지 처리 실패: {e}")
            
            # FAISS 인덱스 재구축
            self.search_engine.rebuild_index()
            
        finally:
            # 임시 폴더 정리
            loader.cleanup()
        
        logging.info(f"🎉 Google Drive 인덱싱 완료! 총 {processed_count}장 처리")
        return processed_count

    def _fallback_index_images(self):
        """파일 시스템 기반 fallback 인덱싱"""
        limit = 100
        batch_size = 32

        logging.info("🚨 폴백 모드: 기존 파일 시스템 인덱싱 실행 중...")
        
        raw_paths = list(Path(self.image_folder).glob("**/*.jpg")) + \
                    list(Path(self.image_folder).glob("**/*.jpeg")) + \
                    list(Path(self.image_folder).glob("**/*.png")) + \
                    list(Path(self.image_folder).glob("**/*.heic"))
        
        valid_paths = []
        for p in raw_paths:
            if os.path.getsize(p) < 100 * 1024:
                continue
            if 'thumb' in str(p).lower() or 'preview' in str(p).lower():
                continue
                
            valid_paths.append(str(p))
            
            if limit and len(valid_paths) >= limit:
                break
        
        total_images = len(valid_paths)
        logging.info(f"💾 폴백 모드: {total_images}개 원본 사진 인덱싱 시작.")
        
        for i in range(0, total_images, batch_size):
            batch_paths = valid_paths[i:i+batch_size]
            
            logging.info(f"⚡️ 처리 중... ({i}/{total_images})")
            
            try:
                vectors = self.clip.batch_encode_images(batch_paths, batch_size=batch_size)
                
                for path_str, vector in zip(batch_paths, vectors):
                    try:
                        metadata = {
                            'taken_date': None,
                            'gps_lat': None,
                            'gps_lon': None,
                            'location_name': None,
                            'source': 'local_folder'
                        }
                        self.db.save_image(path_str, vector, metadata)
                    except Exception as e:
                        logging.error(f"저장 실패: {e}")
                        
            except Exception as e:
                logging.error(f"배치 에러: {e}")

        # FAISS 인덱스 재구축
        self.search_engine.rebuild_index()
        
        logging.info("✅ 폴백 파일 시스템 인덱싱 완료!")
        return total_images


    def search(self, query: str) -> str:
        """자연어 검색 실행"""
        parsed = self.query_parser.parse_query(query)
        logging.info(f"파싱 결과: {parsed}")
        
        results = self.search_engine.search(parsed)
        response = self.response_gen.generate_response(query, results)
        
        return response, results


def select_data_source():
    """데이터 소스 선택 메뉴"""
    print("\n" + "="*50)
    print("📸 Picta AI 갤러리 - 데이터 소스 선택")
    print("="*50)
    print("\n어디서 사진을 불러올까요?\n")
    print("  1. 🍎 맥북 사진첩 (Mac Photos Library)")
    print("  2. ☁️  구글 드라이브 (Google Drive)")
    print("  3. ⏭️  건너뛰기 (이미 인덱싱된 데이터 사용)")
    print()
    
    while True:
        choice = input("선택하세요 (1-3): ").strip()
        if choice in ['1', '2', '3']:
            return int(choice)
        print("1, 2, 3 중 하나를 입력해주세요.")


def get_indexing_limit():
    """인덱싱할 사진 수 입력"""
    print("\n몇 장의 사진을 인덱싱할까요?")
    print("  - 숫자 입력: 해당 수만큼 (예: 1000)")
    print("  - 'all' 입력: 전체 사진")
    print("  - Enter: 기본값 1000장")
    
    while True:
        limit_input = input("\n사진 수 (기본 1000): ").strip().lower()
        
        if limit_input == '':
            return 1000
        elif limit_input == 'all':
            return None
        else:
            try:
                return int(limit_input)
            except ValueError:
                print("숫자 또는 'all'을 입력해주세요.")


if __name__ == "__main__":
    
    mac_photos_path = os.path.expanduser("~/Pictures/Photos Library.photoslibrary/originals")
    
    if os.path.exists(mac_photos_path):
        target_folder = mac_photos_path
    else:
        target_folder = "data/images"
    
    # DB 경로 정의
    MAC_DB_PATH = "data/picta_mac.db"
    GDRIVE_DB_PATH = "data/picta_gdrive.db"
    
    # data 폴더 생성
    os.makedirs("data", exist_ok=True)
    
    # 각 DB 상태 확인
    def get_db_count(db_path):
        if not os.path.exists(db_path):
            return 0
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT COUNT(*) FROM images")
                return cursor.fetchone()[0]
            except:
                return 0
    
    mac_count = get_db_count(MAC_DB_PATH)
    gdrive_count = get_db_count(GDRIVE_DB_PATH)
    
    # 현재 인덱싱 상태 표시
    print("\n" + "="*50)
    print("📊 현재 인덱싱 상태")
    print("="*50)
    print(f"  🍎 맥북 사진첩: {mac_count}장")
    print(f"  ☁️  구글 드라이브: {gdrive_count}장")
    
    # 데이터 소스 선택
    source_choice = select_data_source()
    
    # 인덱싱 또는 검색 모드 결정
    if source_choice == 1:
        # 맥북 사진첩
        db_path = MAC_DB_PATH
        engine = PictaEngine(image_folder=target_folder, db_path=db_path)
        
        if mac_count > 0:
            print(f"\n✅ 맥북 DB에 이미 {mac_count}장이 인덱싱되어 있습니다.")
            reindex = input("재인덱싱하시겠습니까? (y/N): ").strip().lower()
            if reindex == 'y':
                limit = get_indexing_limit()
                print(f"\n🍎 맥북 사진첩 인덱싱 시작...")
                engine.index_mac_photos(limit=limit)
        else:
            limit = get_indexing_limit()
            print(f"\n🍎 맥북 사진첩 인덱싱 시작...")
            engine.index_mac_photos(limit=limit)
            
    elif source_choice == 2:
        # 구글 드라이브
        db_path = GDRIVE_DB_PATH
        engine = PictaEngine(image_folder=target_folder, db_path=db_path)
        
        # 폴더 선택
        print("\n☁️ 구글 드라이브 폴더 선택:")
        print("  1. 전체 드라이브")
        print("  2. 특정 폴더 지정")
        
        while True:
            folder_choice = input("선택하세요 (1-2): ").strip()
            if folder_choice in ['1', '2']:
                break
            print("1 또는 2를 입력해주세요.")
        
        folder_id = None
        if folder_choice == '2':
            print("\n📋 Google Drive 폴더 URL에서 폴더 ID를 복사해주세요.")
            print("   예: https://drive.google.com/drive/folders/ABC123xxxxx")
            print("                                          ↑ 이 부분")
            folder_id = input("\n폴더 ID 입력: ").strip()
            if not folder_id:
                print("폴더 ID가 비어있어 전체 드라이브에서 검색합니다.")
                folder_id = None
        
        if gdrive_count > 0:
            print(f"\n✅ 구글 드라이브 DB에 이미 {gdrive_count}장이 인덱싱되어 있습니다.")
            reindex = input("재인덱싱하시겠습니까? (y/N): ").strip().lower()
            if reindex == 'y':
                limit = get_indexing_limit()
                print(f"\n☁️ 구글 드라이브 인덱싱 시작...")
                engine.index_google_drive(limit=limit, folder_id=folder_id)
        else:
            limit = get_indexing_limit()
            print(f"\n☁️ 구글 드라이브 인덱싱 시작...")
            engine.index_google_drive(limit=limit, folder_id=folder_id)
            
    else:
        # 건너뛰기 - 검색할 DB 선택
        print("\n어느 데이터에서 검색할까요?")
        print(f"  1. 🍎 맥북 사진첩 ({mac_count}장)")
        print(f"  2. ☁️  구글 드라이브 ({gdrive_count}장)")
        
        while True:
            search_choice = input("선택하세요 (1-2): ").strip()
            if search_choice == '1':
                db_path = MAC_DB_PATH
                break
            elif search_choice == '2':
                db_path = GDRIVE_DB_PATH
                break
            print("1 또는 2를 입력해주세요.")
        
        engine = PictaEngine(image_folder=target_folder, db_path=db_path)
    
    # 검색 루프
    while True:
        source_name = "🍎 맥북 사진첩" if db_path == MAC_DB_PATH else "☁️ 구글 드라이브"
        current_count = get_db_count(db_path)
        
        print("\n" + "="*50)
        print(f"📸 Picta AI 갤러리")
        print(f"   현재 소스: {source_name} ({current_count}장)")
        print("="*50)

        try:
            query = input(f"\n💬 찾고 싶은 사진을 묘사해주세요.\n   메뉴로 가고 싶으면 '메뉴' 또는 'm'을 입력해주세요: ").strip()
            
            if query.lower() in ['q', 'quit', 'exit', '그만', '종료']:
                print("안녕히 가세요! 👋")
                break
            
            if query.lower() in ['m', 'menu', '메뉴']:
                # 소스 전환 메뉴
                mac_count = get_db_count(MAC_DB_PATH)
                gdrive_count = get_db_count(GDRIVE_DB_PATH)
                
                print("\n어느 데이터에서 검색할까요?")
                print(f"  1. 🍎 맥북 사진첩 ({mac_count}장){' ⚠️ 인덱싱 필요' if mac_count == 0 else ''}")
                print(f"  2. ☁️  구글 드라이브 ({gdrive_count}장){' ⚠️ 인덱싱 필요' if gdrive_count == 0 else ''}")
                print(f"  3. ⏭️  취소 (현재 소스 유지)")
                
                while True:
                    menu_choice = input("선택하세요 (1-3): ").strip()
                    if menu_choice == '1':
                        db_path = MAC_DB_PATH
                        engine = PictaEngine(image_folder=target_folder, db_path=db_path)
                        
                        if mac_count == 0:
                            print("\n⚠️ 맥북 사진첩에 인덱싱된 사진이 없습니다.")
                            do_index = input("지금 인덱싱하시겠습니까? (Y/n): ").strip().lower()
                            if do_index != 'n':
                                limit = get_indexing_limit()
                                print(f"\n🍎 맥북 사진첩 인덱싱 시작...")
                                engine.index_mac_photos(limit=limit)
                        else:
                            reindex = input(f"\n현재 {mac_count}장 인덱싱됨. 재인덱싱하시겠습니까? (y/N): ").strip().lower()
                            if reindex == 'y':
                                limit = get_indexing_limit()
                                print(f"\n🍎 맥북 사진첩 인덱싱 시작...")
                                engine.index_mac_photos(limit=limit)
                        
                        print("\n✅ 🍎 맥북 사진첩으로 전환했습니다!")
                        break
                    elif menu_choice == '2':
                        db_path = GDRIVE_DB_PATH
                        engine = PictaEngine(image_folder=target_folder, db_path=db_path)
                        
                        if gdrive_count == 0:
                            print("\n⚠️ 구글 드라이브에 인덱싱된 사진이 없습니다.")
                            do_index = input("지금 인덱싱하시겠습니까? (Y/n): ").strip().lower()
                            if do_index != 'n':
                                # 폴더 선택
                                print("\n☁️ 구글 드라이브 폴더 선택:")
                                print("  1. 전체 드라이브")
                                print("  2. 특정 폴더 지정")
                                
                                folder_id = None
                                while True:
                                    folder_choice = input("선택하세요 (1-2): ").strip()
                                    if folder_choice == '1':
                                        break
                                    elif folder_choice == '2':
                                        print("\n📋 Google Drive 폴더 URL에서 폴더 ID를 복사해주세요.")
                                        print("   예: https://drive.google.com/drive/folders/ABC123xxxxx")
                                        folder_id = input("\n폴더 ID 입력: ").strip() or None
                                        break
                                    print("1 또는 2를 입력해주세요.")
                                
                                limit = get_indexing_limit()
                                print(f"\n☁️ 구글 드라이브 인덱싱 시작...")
                                engine.index_google_drive(limit=limit, folder_id=folder_id)
                        else:
                            reindex = input(f"\n현재 {gdrive_count}장 인덱싱됨. 재인덱싱하시겠습니까? (y/N): ").strip().lower()
                            if reindex == 'y':
                                # 폴더 선택
                                print("\n☁️ 구글 드라이브 폴더 선택:")
                                print("  1. 전체 드라이브")
                                print("  2. 특정 폴더 지정")
                                
                                folder_id = None
                                while True:
                                    folder_choice = input("선택하세요 (1-2): ").strip()
                                    if folder_choice == '1':
                                        break
                                    elif folder_choice == '2':
                                        print("\n📋 Google Drive 폴더 URL에서 폴더 ID를 복사해주세요.")
                                        print("   예: https://drive.google.com/drive/folders/ABC123xxxxx")
                                        folder_id = input("\n폴더 ID 입력: ").strip() or None
                                        break
                                    print("1 또는 2를 입력해주세요.")
                                
                                limit = get_indexing_limit()
                                print(f"\n☁️ 구글 드라이브 인덱싱 시작...")
                                engine.index_google_drive(limit=limit, folder_id=folder_id)
                        
                        print("\n✅ ☁️ 구글 드라이브로 전환했습니다!")
                        break
                    elif menu_choice == '3':
                        print("\n취소했습니다.")
                        break
                    print("1, 2, 3 중 하나를 입력해주세요.")
                continue
            
            if not query:
                continue

            response, results = engine.search(query)
            print(f"\n🤖 Picta: {response}")
            
            if results:
                print(f"\n🔍 검색 결과 상세 (상위 {min(10, len(results))}개):")
                for i, r in enumerate(results[:10], 1):
                    source_icon = "🍎" if r.get('metadata', {}).get('source') == 'mac_photos' else "☁️"
                    print(f"{i}. {source_icon} 유사도: {r.get('similarity', 0):.3f} | "
                          f"날짜: {r.get('taken_date', '없음')[:10] if r.get('taken_date') else '없음'} | "
                          f"위치: {r.get('location_name', '없음')}")
            
            # 팝업으로 사진 띄우기
            if results:
                top_results = results[:5]
                
                plt.figure(figsize=(15, 5))
                plt.suptitle(f"Search Result: '{query}'", fontsize=16)
                
                for i, result in enumerate(top_results):
                    try:
                        path = result['file_path']
                        score = result['similarity']
                        location = result.get('location_name') or ''
                        
                        img = Image.open(path)
                        
                        plt.subplot(1, len(top_results), i + 1)
                        plt.imshow(img)
                        plt.axis('off')
                        
                        if location:
                            plt.title(f"#{i+1} ({score:.3f})\n{location}", fontsize=9)
                        else:
                            plt.title(f"#{i+1} ({score:.3f})", fontsize=9)
                        
                    except Exception as e:
                        print(f"이미지 로드 실패: {e}")
                
                print("✨ 사진 창을 띄웠습니다! (다음 검색을 하려면 창을 닫아주세요)")
                plt.show()

        except KeyboardInterrupt:
            print("\n종료합니다.")
            break
        except Exception as e:
            print(f"❌ 에러 발생: {e}")
