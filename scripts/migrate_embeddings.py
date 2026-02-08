"""Migration Script: Export existing .npy embeddings (face + body) to Qdrant"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pathlib import Path
from app.services.embedding_service import EmbeddingService
from app.config import settings
import uuid

def migrate_face_embeddings(embedding_service):
    """Migrate face embeddings from data/embeddings/*.npy"""
    print("\n[MIGRATION] === Face Embeddings Migration ===")
    
    embed_dir = Path("data/embeddings")
    
    if not embed_dir.exists():
        print(f"[WARNING] Directory not found: {embed_dir}")
        return 0
    
    migrated_count = 0
    for npy_file in embed_dir.glob("*.npy"):
        try:
            # Parse filename: "Name_NIM.npy" or "Name.npy"
            filename = npy_file.stem
            parts = filename.rsplit("_", 1)
            
            if len(parts) == 2:
                name, nim_nip = parts
            else:
                name = filename
                nim_nip = f"MIGRATED_{uuid.uuid4().hex[:8]}"
            
            # Load embedding (should be 512D from InsightFace)
            embedding = np.load(npy_file)
            
            # Validate dimension
            if embedding.shape[0] != 512:
                print(f"❌ Skipped {name}: Invalid dimension {embedding.shape}")
                continue
            
            # Generate person_id
            person_id = str(uuid.uuid4())
            
            # Add to Qdrant (face collection)
            embedding_id = embedding_service.add_embedding(
                embedding=embedding,
                person_id=person_id,
                person_name=name,
                nim_nip=nim_nip,
                embedding_type="face"
            )
            
            print(f"✅ Face: {name} (NIM: {nim_nip}) -> {embedding_id}")
            migrated_count += 1
            
        except Exception as e:
            print(f"❌ Failed to migrate face {npy_file}: {e}")
    
    return migrated_count

def migrate_body_embeddings(embedding_service):
    """Migrate body embeddings from data/body_embeddings/*.npy"""
    print("\n[MIGRATION] === Body Embeddings Migration ===")
    
    body_dir = Path("data/body_embeddings")
    
    if not body_dir.exists():
        print(f"[WARNING] Directory not found: {body_dir}")
        return 0
    
    migrated_count = 0
    for npy_file in body_dir.glob("*.npy"):
        try:
            # Parse filename
            filename = npy_file.stem
            parts = filename.rsplit("_", 1)
            
            if len(parts) == 2:
                name, nim_nip = parts
            else:
                name = filename
                nim_nip = None
            
            # Load body features (OSNet)
            data = np.load(npy_file, allow_pickle=True)
            
            # Handle both 1D (single vector) and 2D (gallery) formats
            if data.ndim == 1:
                vectors = [data]
            elif data.ndim == 2:
                vectors = [vec for vec in data]
            else:
                print(f"❌ Skipped {name}: Invalid ndim {data.ndim}")
                continue
            
            # Migrate each body feature vector
            for idx, vector in enumerate(vectors):
                # Validate and normalize
                if vector.shape[0] not in [512, 256]:  # OSNet can be 512 or 256
                    print(f"⚠️  Skipped {name} vector {idx}: Unexpected dimension {vector.shape}")
                    continue
                
                # Pad to 512D if needed (OSNet x0.5 is 256D)
                if vector.shape[0] == 256:
                    vector = np.pad(vector, (0, 256), mode='constant')
                
                # Normalize
                norm = np.linalg.norm(vector)
                if norm > 0:
                    vector = vector / norm
                
                # Add to Qdrant (body collection)
                person_id = name  # Use name as person_id for body embeddings
                
                embedding_id = embedding_service.add_embedding(
                    embedding=vector,
                    person_id=person_id,
                    person_name=name,
                    nim_nip=nim_nip,
                    embedding_type="body"
                )
                
                migrated_count += 1
            
            print(f"✅ Body: {name} ({len(vectors)} vectors) -> Qdrant")
            
        except Exception as e:
            print(f"❌ Failed to migrate body {npy_file}: {e}")
    
    return migrated_count

def migrate_embeddings():
    """Migrate all embeddings (face + body) to Qdrant"""
    print("[MIGRATION] Starting embedding migration to Qdrant...")
    print(f"Target: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    
    # Initialize embedding service
    embedding_service = EmbeddingService()
    
    # Migrate face embeddings
    face_count = migrate_face_embeddings(embedding_service)
    
    # Migrate body embeddings  
    body_count = migrate_body_embeddings(embedding_service)
    
    # Summary
    print("\n" + "="*60)
    print(f"[MIGRATION] Completed!")
    print(f"  Face embeddings migrated: {face_count}")
    print(f"  Body embeddings migrated: {body_count}")
    print(f"  Total in Qdrant: {embedding_service.count_embeddings('all')}")
    print(f"    - Face collection: {embedding_service.count_embeddings('face')}")
    print(f"    - Body collection: {embedding_service.count_embeddings('body')}")
    print("="*60)
    print("\n💡 Next steps:")
    print("  1. Verify data in Qdrant: http://localhost:6333/dashboard")
    print("  2. Backup original .npy files:")
    print("     mkdir -p data/embeddings_backup data/body_embeddings_backup")
    print("     mv data/embeddings/*.npy data/embeddings_backup/")
    print("     mv data/body_embeddings/*.npy data/body_embeddings_backup/")
    print("  3. Test camera worker to ensure it loads from Qdrant")


if __name__ == "__main__":
    migrate_embeddings()
