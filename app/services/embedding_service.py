"""Embedding Service - Qdrant Vector Database Integration"""
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from typing import List, Optional, Dict, Any, Literal
import uuid
from app.config import settings


class EmbeddingService:
    """
    Service for managing embeddings in Qdrant vector database
    Handles both face embeddings (512D InsightFace) and body embeddings (OSNet re-ID)
    """
    
    def __init__(self):
        self.client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        self.face_collection = settings.QDRANT_FACE_COLLECTION
        self.body_collection = settings.QDRANT_BODY_COLLECTION
        self._ensure_collections()
    
    def _ensure_collections(self):
        """Create collections if they don't exist"""
        try:
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            # Face embeddings collection (512D InsightFace)
            if self.face_collection not in collection_names:
                self.client.create_collection(
                    collection_name=self.face_collection,
                    vectors_config=VectorParams(
                        size=512,  # InsightFace embedding dimension
                        distance=Distance.COSINE
                    )
                )
                print(f"[QDRANT] Created collection: {self.face_collection}")
            else:
                print(f"[QDRANT] Collection exists: {self.face_collection}")
            
            # Body embeddings collection (OSNet re-identification)
            if self.body_collection not in collection_names:
                self.client.create_collection(
                    collection_name=self.body_collection,
                    vectors_config=VectorParams(
                        size=512,  # OSNet x1.0 embedding dimension
                        distance=Distance.COSINE
                    )
                )
                print(f"[QDRANT] Created collection: {self.body_collection}")
            else:
                print(f"[QDRANT] Collection exists: {self.body_collection}")
                
        except Exception as e:
            print(f"[QDRANT] Error ensuring collections: {e}")
    
    def add_embedding(
        self, 
        embedding: np.ndarray, 
        person_id: str,
        person_name: str,
        nim_nip: str = None,
        embedding_type: Literal["face", "body"] = "face"
    ) -> str:
        """
        Add or update embedding in Qdrant
        
        Args:
            embedding: Embedding vector (512D for both face and body)
            person_id: UUID of person in PostgreSQL (or name for body embeddings)
            person_name: Person's name
            nim_nip: Student/Staff ID (optional for body embeddings)
            embedding_type: "face" or "body"
            
        Returns:
            embedding_id: UUID of the vector in Qdrant
        """
        try:
            # Convert numpy array to list
            if isinstance(embedding, np.ndarray):
                embedding = embedding.flatten().tolist()
            
            # Generate unique ID for Qdrant
            embedding_id = str(uuid.uuid4())
            
            # Determine collection
            collection = self.face_collection if embedding_type == "face" else self.body_collection
            
            # Create point with metadata
            payload = {
                "person_id": person_id,
                "name": person_name,
                "is_active": True,
                "type": embedding_type
            }
            if nim_nip:
                payload["nim_nip"] = nim_nip
            
            point = PointStruct(
                id=embedding_id,
                vector=embedding,
                payload=payload
            )
            
            # Upsert to Qdrant
            self.client.upsert(
                collection_name=collection,
                points=[point]
            )
            
            print(f"[QDRANT] Added {embedding_type} embedding for {person_name} (ID: {embedding_id})")
            return embedding_id
            
        except Exception as e:
            print(f"[QDRANT] Error adding embedding: {e}")
            raise
    
    def search_similar(
        self, 
        embedding: np.ndarray, 
        limit: int = 5,
        threshold: float = None,
        embedding_type: Literal["face", "body"] = "face",
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for similar embeddings
        
        Args:
            embedding: Query embedding vector
            limit: Maximum number of results
            threshold: Minimum similarity score (optional)
            embedding_type: "face" or "body"
            active_only: Only search active embeddings (default True)
            
        Returns:
            List of matches with scores and metadata
        """
        try:
            # Convert numpy to list
            if isinstance(embedding, np.ndarray):
                embedding = embedding.flatten().tolist()
            
            # Determine collection and threshold
            collection = self.face_collection if embedding_type == "face" else self.body_collection
            default_threshold = settings.FACE_MATCH_THRESHOLD if embedding_type == "face" else 0.50
            
            # Prepare filter
            query_filter = None
            if active_only:
                query_filter = Filter(
                    must=[
                        FieldCondition(key="is_active", match=MatchValue(value=True))
                    ]
                )
            
            # Search in Qdrant
            results = self.client.search(
                collection_name=collection,
                query_vector=embedding,
                query_filter=query_filter,
                limit=limit,
                score_threshold=threshold or default_threshold
            )
            
            # Format results
            matches = []
            for result in results:
                match_data = {
                    "embedding_id": result.id,
                    "person_id": result.payload.get("person_id"),
                    "name": result.payload.get("name"),
                    "score": result.score,
                    "confidence": result.score,
                    "type": embedding_type
                }
                if result.payload.get("nim_nip"):
                    match_data["nim_nip"] = result.payload.get("nim_nip")
                matches.append(match_data)
            
            return matches
            
        except Exception as e:
            print(f"[QDRANT] Error searching {embedding_type} embeddings: {e}")
            return []
    
    def get_embedding(
        self, 
        embedding_id: str,
        embedding_type: Literal["face", "body"] = "face"
    ) -> Optional[Dict[str, Any]]:
        """Get embedding by ID"""
        try:
            collection = self.face_collection if embedding_type == "face" else self.body_collection
            
            result = self.client.retrieve(
                collection_name=collection,
                ids=[embedding_id],
                with_vectors=True
            )
            
            if result:
                point = result[0]
                return {
                    "embedding_id": point.id,
                    "vector": point.vector,
                    "person_id": point.payload.get("person_id"),
                    "name": point.payload.get("name"),
                    "type": embedding_type
                }
            return None
            
        except Exception as e:
            print(f"[QDRANT] Error retrieving {embedding_type} embedding: {e}")
            return None
    
    def delete_embedding(
        self, 
        embedding_id: str,
        embedding_type: Literal["face", "body"] = "face"
    ) -> bool:
        """Delete embedding from Qdrant"""
        try:
            collection = self.face_collection if embedding_type == "face" else self.body_collection
            
            self.client.delete(
                collection_name=collection,
                points_selector=[embedding_id]
            )
            print(f"[QDRANT] Deleted {embedding_type} embedding: {embedding_id}")
            return True
            
        except Exception as e:
            print(f"[QDRANT] Error deleting {embedding_type} embedding: {e}")
            return False
    
    def update_embedding_metadata(
        self, 
        embedding_id: str, 
        person_name: str = None,
        is_active: bool = None,
        embedding_type: Literal["face", "body"] = "face"
    ) -> bool:
        """Update embedding metadata without changing vector"""
        try:
            collection = self.face_collection if embedding_type == "face" else self.body_collection
            
            payload = {}
            if person_name is not None:
                payload["name"] = person_name
            if is_active is not None:
                payload["is_active"] = is_active
            
            self.client.set_payload(
                collection_name=collection,
                payload=payload,
                points=[embedding_id]
            )
            return True
            
        except Exception as e:
            print(f"[QDRANT] Error updating {embedding_type} metadata: {e}")
            return False
    
    def count_embeddings(
        self, 
        embedding_type: Literal["face", "body", "all"] = "all"
    ) -> int:
        """Get total count of embeddings"""
        try:
            if embedding_type == "all":
                face_count = self.client.get_collection(collection_name=self.face_collection).points_count
                body_count = self.client.get_collection(collection_name=self.body_collection).points_count
                return face_count + body_count
            else:
                collection = self.face_collection if embedding_type == "face" else self.body_collection
                info = self.client.get_collection(collection_name=collection)
                return info.points_count
        except Exception as e:
            print(f"[QDRANT] Error counting embeddings: {e}")
            return 0
    
    def get_all_embeddings_by_name(
        self,
        person_name: str,
        embedding_type: Literal["face", "body"] = "body"
    ) -> List[np.ndarray]:
        """Get all embedding vectors for a person (useful for body embeddings gallery)"""
        try:
            collection = self.face_collection if embedding_type == "face" else self.body_collection
            
            # Scroll through all points with matching name
            results, _ = self.client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="name", match=MatchValue(value=person_name)),
                        FieldCondition(key="is_active", match=MatchValue(value=True))
                    ]
                ),
                limit=100,  # Max 100 body features per person
                with_vectors=True
            )
            
            vectors = []
            for point in results:
                if point.vector:
                    vectors.append(np.array(point.vector, dtype=np.float32))
            
            return vectors
            
        except Exception as e:
            print(f"[QDRANT] Error getting {embedding_type} embeddings for {person_name}: {e}")
            return []
