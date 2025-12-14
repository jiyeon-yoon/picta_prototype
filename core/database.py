import sqlite3
import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional

class DatabaseManager:
    def __init__(self, db_path: str = "data/picta.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 이미지 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    thumbnail_path TEXT,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    taken_date TIMESTAMP,
                    gps_lat REAL,
                    gps_lon REAL,
                    location_name TEXT,
                    clip_vector BLOB,
                    metadata JSON
                )
            """)
            
            # 얼굴 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER REFERENCES images(id),
                    bbox JSON,
                    encoding BLOB,
                    person_name TEXT,
                    confidence REAL
                )
            """)
            
            # 검색 히스토리
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    results JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    def save_image(self, file_path: str, clip_vector: np.ndarray, 
                   metadata: Dict) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO images 
                (file_path, clip_vector, taken_date, gps_lat, gps_lon, location_name, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                file_path,
                clip_vector.astype(np.float32).tobytes(),
                metadata.get('taken_date'),
                metadata.get('gps_lat'),
                metadata.get('gps_lon'),
                metadata.get('location_name'),
                json.dumps(metadata)
            ))
            return cursor.lastrowid
    
    def save_face(self, image_id: int, face_data: Dict):
        """얼굴 데이터 저장"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO faces (image_id, bbox, encoding, person_name, confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (
                image_id,
                json.dumps(face_data.get('bbox', [])),
                face_data['encoding'].tobytes() if 'encoding' in face_data else None,
                face_data.get('person_name'),
                face_data.get('confidence', 0)
            ))
