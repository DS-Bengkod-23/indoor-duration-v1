# indoor/registry.py
import os
import sys
import numpy as np
from typing import Dict, List, Optional

# Import Qdrant client
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
    import uuid
except ImportError:
    print("[REGISTRY] Warning: qdrant-client not installed")


class UserRegistry:
    """
    Registry untuk manage user face embedding menggunakan Qdrant.
    - No more .npy files!
    - 1 user = 1 or more vectors in Qdrant face_embeddings collection
    - Dipakai bareng FaceRecognizer + pipeline ID Lock
    """

    def __init__(self, qdrant_host="localhost", qdrant_port=6333):
        self.qdrant_host = os.environ.get("QDRANT_HOST", qdrant_host)
        self.qdrant_port = int(os.environ.get("QDRANT_PORT", qdrant_port))
        self.collection_name = "face_embeddings"
        
        # In-memory cache for fast access
        self._cache: Dict[str, np.ndarray] = {}
        
        # Initialize Qdrant client
        try:
            self.client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
            self._ensure_collection()
            self._load_all()
        except Exception as e:
            print(f"[REGISTRY] ERROR connecting to Qdrant: {e}")
            self.client = None


    def _ensure_collection(self):
        """Create Qdrant collection if not exists"""
        try:
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=512,  # InsightFace embedding dimension
                        distance=Distance.COSINE
                    )
                )
                print(f"[REGISTRY] Created Qdrant collection: {self.collection_name}")
        except Exception as e:
            print(f"[REGISTRY] Error ensuring collection: {e}")

    # ---------------------------------------------------------
    # INTERNAL: LOAD SEMUA EMBEDDING KE MEMORY CACHE
    # ---------------------------------------------------------
    def _load_all(self):
        self._cache.clear()
        
        if self.client is None:
            print("[REGISTRY] No Qdrant client, cache empty")
            return
        
        try:
            # Scroll all face embeddings
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
                ),
                limit=10000,
                with_vectors=True
            )
            
            # Take first embedding for each person (for backward compatibility)
            loaded = {}
            for point in results:
                name = point.payload.get("name")
                if name and name not in loaded:
                    vector = np.array(point.vector, dtype=np.float32)
                    self._cache[name] = vector
                    loaded[name] = True

            print(f"[REGISTRY] Loaded {len(self._cache)} users from Qdrant")
        except Exception as e:
            print(f"[REGISTRY] Error loading from Qdrant: {e}")

    # ---------------------------------------------------------
    # PUBLIC: LIST + CEK USER
    # ---------------------------------------------------------
    def list_users(self) -> List[str]:
        return sorted(self._cache.keys())

    def exists(self, name: str) -> bool:
        return name in self._cache

    # ---------------------------------------------------------
    # GET / SET EMBEDDING
    # ---------------------------------------------------------
    def get_embedding(self, name: str) -> Optional[np.ndarray]:
        return self._cache.get(name, None)

    def save_embedding(self, name: str, embedding: np.ndarray, overwrite: bool = False) -> bool:
        """
        Simpan face embedding ke Qdrant.
        - name: nama user
        - embedding: vector 512D dari InsightFace
        """
        if self.client is None:
            print("[REGISTRY] No Qdrant client, cannot save")
            return False
        
        if (not overwrite) and self.exists(name):
            print(f"[REGISTRY] User '{name}' sudah ada. Set overwrite=True jika ingin ganti.")
            return False

        if embedding is None:
            print("[REGISTRY] Embedding kosong, tidak disimpan.")
            return False

        try:
            # Delete old embeddings if overwrite
            if overwrite and self.exists(name):
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=Filter(
                        must=[FieldCondition(key="name", match=MatchValue(value=name))]
                    )
                )
            
            # Add new embedding
            embedding_id = str(uuid.uuid4())
            point = PointStruct(
                id=embedding_id,
                vector=embedding.flatten().tolist(),
                payload={
                    "person_id": name,  # Use name as person_id for simplicity
                    "name": name,
                    "is_active": True,
                    "type": "face"
                }
            )
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            # Update cache
            self._cache[name] = embedding.astype(np.float32)
            
            print(f"[REGISTRY] Saved embedding for '{name}' to Qdrant")
            return True
            
        except Exception as e:
            print(f"[REGISTRY] Error saving to Qdrant: {e}")
            return False

    # ---------------------------------------------------------
    # HAPUS USER
    # ---------------------------------------------------------
    def delete_user(self, name: str) -> bool:
        if not self.exists(name):
            print(f"[REGISTRY] User '{name}' tidak ditemukan.")
            return False

        if self.client is None:
            print("[REGISTRY] No Qdrant client, cannot delete")
            return False

        try:
            # Delete from Qdrant
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="name", match=MatchValue(value=name))]
                )
            )
            
            # Delete from cache
            if name in self._cache:
                del self._cache[name]

            print(f"[REGISTRY] Deleted user '{name}' from Qdrant")
            return True
        except Exception as e:
            print(f"[REGISTRY] Error deleting from Qdrant: {e}")
            return False

    # ---------------------------------------------------------
    # RELOAD (Jika ada perubahan eksternal)
    # ---------------------------------------------------------
    def reload(self):
        """
        Reload ulang semua embeddings dari Qdrant ke cache.
        Dipanggil kalau ada edit manual di Qdrant.
        """
        self._load_all()
