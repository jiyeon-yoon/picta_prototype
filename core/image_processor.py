import torch
import numpy as np
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from typing import List
import logging

from pillow_heif import register_heif_opener
register_heif_opener()

class CLIPImageProcessor:
    def __init__(self, model_name: str = "openai/clip-vit-large-patch14"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_name = model_name
        
        # [수정] 모델별 벡터 차원 설정
        self.vector_dim = 768 if "large" in model_name else 512
        
        try:
            self.model = CLIPModel.from_pretrained(model_name).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(model_name)
        except Exception as e:
            logging.error(f"모델 로드 실패: {e}")
            raise e
            
        self.model.eval()
        logging.info(f"✅ CLIP 모델 로드 완료: {model_name} (차원: {self.vector_dim})")
    
    def encode_image(self, image_path: str) -> np.ndarray:
        try:
            image = Image.open(image_path).convert("RGB")
            inputs = self.processor(images=image, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                image_features = self.model.get_image_features(**inputs)
                image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
            
            return image_features.cpu().numpy().squeeze()
        except Exception as e:
            logging.error(f"이미지 처리 실패 ({image_path}): {e}")
            # [수정] 모델에 맞는 차원의 zero 벡터 반환
            return np.zeros(self.vector_dim, dtype=np.float32)
    
    def encode_text(self, text: str) -> np.ndarray:
        inputs = self.processor(
            text=[text], 
            return_tensors="pt", 
            padding=True, 
            truncation=True
        ).to(self.device)
        
        with torch.no_grad():
            text_features = self.model.get_text_features(**inputs)
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
        
        return text_features.cpu().numpy().squeeze()
    
    def batch_encode_images(self, image_paths: List[str], batch_size: int = 32) -> List[np.ndarray]:
        vectors = []
        
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i+batch_size]
            batch_images = []
            valid_indices = []
            
            for idx, path in enumerate(batch_paths):
                try:
                    batch_images.append(Image.open(path).convert("RGB"))
                    valid_indices.append(idx)
                except Exception as e:
                    logging.warning(f"이미지 로드 실패: {path}")
            
            if not batch_images:
                continue

            inputs = self.processor(
                images=batch_images, 
                return_tensors="pt", 
                padding=True
            ).to(self.device)
            
            with torch.no_grad():
                image_features = self.model.get_image_features(**inputs)
                image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
            
            vectors.extend(image_features.cpu().numpy())
        
        return vectors
