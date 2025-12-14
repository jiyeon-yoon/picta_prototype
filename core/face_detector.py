import torch
import numpy as np
from facenet_pytorch import MTCNN, InceptionResnetV1
from PIL import Image
import cv2
from typing import List, Dict, Optional

class FaceDetector:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        # 얼굴 검출
        self.mtcnn = MTCNN(
            image_size=160,
            margin=20,
            device=self.device,
            keep_all=True
        )
        # 얼굴 인코딩
        self.resnet = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
        self.known_faces = {}  # {person_name: [encodings]}
    
    def detect_faces(self, image_path: str) -> Dict:
        """이미지에서 얼굴 검출 및 인코딩"""
        img = Image.open(image_path).convert('RGB')
        
        # 얼굴 검출
        boxes, probs = self.mtcnn.detect(img)
        
        if boxes is None:
            return {'faces': [], 'count': 0}
        
        # 얼굴 추출 및 인코딩
        faces = self.mtcnn(img)
        
        face_data = []
        for i, (box, prob, face) in enumerate(zip(boxes, probs, faces)):
            if face is not None:
                # 얼굴 인코딩 생성
                with torch.no_grad():
                    encoding = self.resnet(face.unsqueeze(0).to(self.device))
                    encoding = encoding.cpu().numpy().squeeze()
                
                face_data.append({
                    'bbox': box.tolist(),
                    'confidence': float(prob),
                    'encoding': encoding,
                    'person_name': self.identify_person(encoding)
                })
        
        return {
            'faces': face_data,
            'count': len(face_data)
        }
    
    def identify_person(self, encoding: np.ndarray, threshold: float = 0.6) -> Optional[str]:
        """얼굴 인코딩으로 사람 식별"""
        min_distance = float('inf')
        identified_person = None
        
        for person_name, known_encodings in self.known_faces.items():
            for known_encoding in known_encodings:
                # 유클리디안 거리 계산
                distance = np.linalg.norm(encoding - known_encoding)
                if distance < min_distance and distance < threshold:
                    min_distance = distance
                    identified_person = person_name
        
        return identified_person
    
    def add_known_face(self, person_name: str, encoding: np.ndarray):
        """새로운 얼굴 등록"""
        if person_name not in self.known_faces:
            self.known_faces[person_name] = []
        self.known_faces[person_name].append(encoding)