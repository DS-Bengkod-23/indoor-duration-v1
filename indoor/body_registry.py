# indoor/body_registry.py
import numpy as np
import os
import sys
import time
import threading
from typing import List, Optional, Dict, Any
from config.settings import SETTINGS

# Import Qdrant client for vector database
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
    import uuid
except ImportError:
    print("[BodyRegistry] Warning: qdrant-client not installed. Install with: pip install qdrant-client")

class BodyRegistry:
    def __init__(self, qdrant_host="localhost", qdrant_port=6333):
        """
        Body embeddings registry using Qdrant vector database
        No more .npy files - all body features stored in Qdrant
        """
        self.qdrant_host = os.environ.get("QDRANT_HOST", qdrant_host)
        self.qdrant_port = int(os.environ.get("QDRANT_PORT", qdrant_port))
        self.collection_name = "body_embeddings"
        
        # In-memory cache for fast lookup (loaded from Qdrant on init)
        self.profiles = {}  # {name: [feature1, feature2, ...]}
        self.last_seen = {}
        self.save_lock = threading.Lock()
        
        # Initialize Qdrant client
        try:
            self.client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
            self._ensure_collection()
            self.load()
        except Exception as e:
            print(f"[BodyRegistry] ERROR connecting to Qdrant at {self.qdrant_host}:{self.qdrant_port}: {e}")
            print(f"[BodyRegistry] Falling back to empty registry (no persistence)")
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
                        size=512,  # OSNet x1.0 produces 512D vectors
                        distance=Distance.COSINE
                    )
                )
                print(f"[BodyRegistry] Created Qdrant collection: {self.collection_name}")
            else:
                print(f"[BodyRegistry] Using existing collection: {self.collection_name}")
        except Exception as e:
            print(f"[BodyRegistry] Error ensuring collection: {e}")

    # Note: clear_memory method is defined at the end of the class
    # to have full Qdrant wipe capability

    def load(self):
        """Load all body embeddings from Qdrant into memory cache"""
        self.profiles = {}
        
        if self.client is None:
            print("[BodyRegistry] No Qdrant client, skipping load")
            return
        
        try:
            # Scroll through all body embeddings
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
                ),
                limit=10000,  # Load all active embeddings
                with_vectors=True
            )
            
            # Group by person name
            for point in results:
                name = point.payload.get("name")
                if not name:
                    continue
                
                vector = np.array(point.vector, dtype=np.float32)
                
                # Normalize
                norm = np.linalg.norm(vector)
                if norm > 0:
                    vector = vector / norm
                
                if name not in self.profiles:
                    self.profiles[name] = []
                
                self.profiles[name].append(vector)
            
            print(f"[BodyRegistry] Loaded {len(self.profiles)} identities from Qdrant (total {len(results)} vectors)")
        except Exception as e:
            print(f"[BodyRegistry] Error loading from Qdrant: {e}")

    def register(self, name, feature, force_replace_anchors=False):
        if feature is None: return
        
        norm = np.linalg.norm(feature)
        if norm > 0: feature = feature / norm
        
        if name not in self.profiles:
            self.profiles[name] = []
            
        #  SMART ANCHOR REPLACEMENT (New Outfit) 
        # Jika ganti baju, kita RESET total history lama.
        # Biar baju lama (yang mungkin mirip teman) tidak disimpan lagi.
        if force_replace_anchors:
            print(f"[BodyRegistry] FORCE RESET profile for {name} (New Outfit Detected). Old size: {len(self.profiles[name])}")

    def register(self, name, feature, force_replace_anchors=False):
        """Register body embedding to Qdrant"""
        if feature is None:
            return
        
        if self.client is None:
            # Fallback: only store in memory if no Qdrant
            if name not in self.profiles:
                self.profiles[name] = []
            self.profiles[name].append(feature)
            return
        
        norm = np.linalg.norm(feature)
        if norm > 0:
            feature = feature / norm
        else:
            return
        
        if name not in self.profiles:
            self.profiles[name] = []
            
        #  SMART ANCHOR REPLACEMENT (New Outfit) 
        # Jika ganti baju, kita RESET total history lama.
        if force_replace_anchors:
            print(f"[BodyRegistry] FORCE RESET profile for {name} (New Outfit Detected). Old size: {len(self.profiles[name])}")
            # Delete all old embeddings for this person in Qdrant
            try:
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=Filter(
                        must=[FieldCondition(key="name", match=MatchValue(value=name))]
                    )
                )
            except Exception as e:
                print(f"[BodyRegistry] Error deleting old embeddings for {name}: {e}")
            
            self.profiles[name] = []  # Clear memory cache
        
        # Check for duplicates in memory
        is_duplicate = False
        for existing in self.profiles[name]:
            if np.dot(existing, feature) > 0.95: 
                is_duplicate = True
                break
        
        if not is_duplicate:
            # Add to memory cache
            self.profiles[name].append(feature)
            
            # 🔥 Limit profile list size to prevent memory leak (max 50 features)
            if len(self.profiles[name]) > 50:
                # Strategy: Keep first 5 (anchor data), rotate the rest
                removed_vector = self.profiles[name].pop(5)
                # Note: We don't delete from Qdrant here, periodic cleanup will handle it
            
            # Save to Qdrant (async in thread)
            def _save_to_qdrant():
                with self.save_lock:
                    try:
                        embedding_id = str(uuid.uuid4())
                        point = PointStruct(
                            id=embedding_id,
                            vector=feature.flatten().tolist(),
                            payload={
                                "person_id": name,  # Use name as person_id for body embeddings
                                "name": name,
                                "is_active": True,
                                "type": "body",
                                "timestamp": time.time()
                            }
                        )
                        
                        self.client.upsert(
                            collection_name=self.collection_name,
                            points=[point]
                        )
                    except Exception as e:
                        print(f"[BodyRegistry] Failed to save {name} to Qdrant: {e}")
            
            from threading import Thread
            t = Thread(target=_save_to_qdrant, daemon=True)
            t.start()

    def match_global(self, query_feat, active_names=[]):
        if len(self.profiles) == 0 or query_feat is None:
            return None, 0.0

        with self.save_lock: # 🛡️ Thread Safety Reading
            query_feat = query_feat.flatten()

        norm = np.linalg.norm(query_feat)
        if norm > 0: query_feat = query_feat / norm
        else: return None, 0.0

        best_name = None
        best_score = -1.0

        candidates = []

        for name, gallery in self.profiles.items():
            local_max_score = 0.0
            for db_feat in gallery:
                db_feat = db_feat.flatten()
                if db_feat.shape[0] != query_feat.shape[0]: 
                    continue
                s = np.dot(query_feat, db_feat)
                if s > local_max_score:
                    local_max_score = s
            
            raw_score = local_max_score
            
            gate_threshold = SETTINGS.get("gate_threshold_global", 0.55)
            if raw_score < gate_threshold: 
                continue 

            final_score = raw_score
            
            # Bonus kecil (0.05) hanya kalau skornya SANGAT TINGGI (>0.75)
            if name in active_names and raw_score > 0.75:
                final_score += 0.05 
            
            candidates.append((final_score, name))

        if not candidates: return None, 0.0
        
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        best_match = candidates[0]
        best_name = best_match[1]
        best_score = best_match[0]

        # AMBIGUITY CHECK (ANTI-SALAH ORANG v12.19) 
        # Jika Top 1 dan Top 2 bedanya kurang dari 5%, jangan tebak!
        # Biarkan sistem menunggu wajah.
        if len(candidates) > 1:
            second_match = candidates[1]
            margin = best_score - second_match[0]
            if margin < 0.05:
                # print(f"[AMBIGUITY REJECT] {best_name} ({best_score:.2f}) == {second_match[1]} ({second_match[0]:.2f}). Too close.")
                return None, 0.0
    def update_activity(self, name):
        self.last_seen[name] = time.time()

    def clear_memory(self):
        """HARD RESET: Wipes memory & Qdrant collection"""
        print("[BodyRegistry] Wiping all memory & Qdrant data...")
        with self.save_lock:
            # 1. Clear RAM
            self.profiles.clear()
            self.last_seen.clear()
            
            # 2. Clear Qdrant (delete all points in collection)
            if self.client:
                try:
                    # Delete entire collection and recreate
                    self.client.delete_collection(collection_name=self.collection_name)
                    self._ensure_collection()
                    print(f"[BodyRegistry] Wiped Qdrant collection: {self.collection_name}")
                except Exception as e:
                    print(f"[BodyRegistry] Qdrant wipe error: {e}")

body_registry = BodyRegistry()