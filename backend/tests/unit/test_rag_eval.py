import numpy as np
import pytest

from app.rag.chunking import CodeChunker
from app.rag.embeddings.fake import DeterministicFakeEmbeddingProvider

# Controlled fixture repository representing typical SaaS backend codebase
FIXTURE_REPOSITORY = {
    "app/core/security.py": """import jwt
from argon2 import PasswordHasher

ph = PasswordHasher()

def hash_password(password: str) -> str:
    \"\"\"Hash a user password using argon2id.\"\"\"
    return ph.hash(password)

def verify_password(hash: str, password: str) -> bool:
    \"\"\"Verify an argon2 password hash against cleartext.\"\"\"
    try:
        return ph.verify(hash, password)
    except Exception:
        return False

def create_access_token(user_id: str, secret_key: str) -> str:
    \"\"\"Sign a JWT access token with user_id.\"\"\"
    payload = {"sub": user_id}
    return jwt.encode(payload, secret_key, algorithm="HS256")
""",
    "app/db/session.py": """from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

engine = create_engine("postgresql://user:pass@localhost:5432/db", pool_size=10, max_overflow=5)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    \"\"\"FastAPI dependency yielding database session per request.\"\"\"
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
""",
    "app/services/payment.py": """import stripe

class PaymentService:
    \"\"\"Service handling Stripe checkout sessions, customer charges, and refunds.\"\"\"

    def create_checkout_session(self, customer_id: str, amount: int) -> dict:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            line_items=[{"price_data": {"unit_amount": amount}, "quantity": 1}],
            mode="payment",
        )
        return {"session_id": session.id, "url": session.url}

    def refund_charge(self, charge_id: str, amount: int | None = None) -> bool:
        \"\"\"Process customer refund for a charge.\"\"\"
        refund = stripe.Refund.create(charge=charge_id, amount=amount)
        return refund.status == "succeeded"
""",
    "app/api/auth.py": """from fastapi import APIRouter, Depends, HTTPException
from app.services.security import verify_password, create_access_token

router = APIRouter(prefix="/auth")

@router.post("/login")
def login(username: str, password: str):
    \"\"\"User login endpoint validating credentials and issuing JWT token.\"\"\"
    user = find_user_by_name(username)
    if not user or not verify_password(user.hashed_password, password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(str(user.id), "secret-key")
    return {"access_token": token, "token_type": "bearer"}

@router.post("/refresh")
def refresh_token(refresh_token: str):
    \"\"\"Issue new access token from valid refresh token.\"\"\"
    return {"access_token": "new-token"}
""",
    "app/models/user.py": """import uuid
from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class User(Base):
    \"\"\"User database entity with email and hashed password columns.\"\"\"
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
""",
    "app/workers/cleanup.py": """import asyncio
from datetime import datetime

async def purge_expired_tokens(db):
    \"\"\"Background worker task purging expired security tokens from database.\"\"\"
    now = datetime.utcnow()
    db.query(SecurityToken).filter(SecurityToken.expires_at < now).delete()
    db.commit()
""",
}

# Ground-truth evaluation dataset: (query, expected_file_path)
GOLDEN_EVAL_QUERIES = [
    ("Where is user password hashed with argon2?", "app/core/security.py"),
    ("How are database sessions created and yielded as FastAPI dependency?", "app/db/session.py"),
    ("Stripe checkout session creation and customer refunds", "app/services/payment.py"),
    ("User login endpoint validating credentials and issuing tokens", "app/api/auth.py"),
    ("User database model entity with email and hashed_password", "app/models/user.py"),
    ("Background worker purging expired security tokens", "app/workers/cleanup.py"),
    ("Where is JWT access token signed with secret key?", "app/core/security.py"),
    ("Database engine connection pooling and pool_size configuration", "app/db/session.py"),
]


@pytest.mark.asyncio
async def test_code_rag_benchmark_metrics():
    """Evaluate Code RAG retrieval accuracy (Recall@k and MRR) on the benchmark repository."""
    chunker = CodeChunker(target_lines=30)
    provider = DeterministicFakeEmbeddingProvider(dimensions=384)

    # 1. Chunk all fixture files
    all_chunks: list[dict] = []
    for path, code in FIXTURE_REPOSITORY.items():
        lang = "python"
        file_chunks = chunker.chunk_file(path, code, lang)
        for fc in file_chunks:
            all_chunks.append({
                "file_path": path,
                "content": fc.chunk_content,
                "start_line": fc.start_line,
                "end_line": fc.end_line,
                "symbol_name": fc.symbol_name,
            })

    assert len(all_chunks) >= len(FIXTURE_REPOSITORY)

    # 2. Embed all chunks
    texts = [c["content"] for c in all_chunks]
    chunk_vectors = np.array(await provider.embed_texts(texts), dtype=np.float32)

    # 3. Run queries and compute retrieval ranks
    reciprocal_ranks: list[float] = []
    recall_at_1: list[int] = []
    recall_at_3: list[int] = []
    recall_at_5: list[int] = []

    for query, expected_path in GOLDEN_EVAL_QUERIES:
        q_vec = np.array(await provider.embed_query(query), dtype=np.float32)
        q_vec = q_vec / np.linalg.norm(q_vec)

        # Vector cosine similarity
        sims = np.dot(chunk_vectors, q_vec)

        # Lexical boost
        query_words = set(query.lower().split())
        scored: list[tuple[float, str]] = []
        for i, c in enumerate(all_chunks):
            cos_score = float(sims[i])
            content_lower = c["content"].lower()
            path_lower = c["file_path"].lower()
            sym_lower = (c["symbol_name"] or "").lower()

            matches = sum(1 for w in query_words if w in content_lower or w in path_lower)
            lex_ratio = matches / len(query_words) if query_words else 0
            sym_boost = 0.15 if any(w in sym_lower for w in query_words) else 0.0

            total_score = (cos_score * 0.70) + (lex_ratio * 0.20) + sym_boost
            scored.append((total_score, c["file_path"]))

        # Sort descending by score
        scored.sort(key=lambda x: -x[0])

        # Find first rank of expected_path
        rank = None
        for r_idx, (_, path) in enumerate(scored):
            if path == expected_path:
                rank = r_idx + 1
                break

        if rank is not None:
            reciprocal_ranks.append(1.0 / rank)
            recall_at_1.append(1 if rank <= 1 else 0)
            recall_at_3.append(1 if rank <= 3 else 0)
            recall_at_5.append(1 if rank <= 5 else 0)
        else:
            reciprocal_ranks.append(0.0)
            recall_at_1.append(0)
            recall_at_3.append(0)
            recall_at_5.append(0)

    # Calculate final aggregate metrics
    mrr = float(np.mean(reciprocal_ranks))
    r1 = float(np.mean(recall_at_1))
    r3 = float(np.mean(recall_at_3))
    r5 = float(np.mean(recall_at_5))

    print("\n--- Code RAG Benchmark Evaluation ---")
    print(f"Queries Evaluated: {len(GOLDEN_EVAL_QUERIES)}")
    print(f"Recall@1: {r1 * 100:.1f}%")
    print(f"Recall@3: {r3 * 100:.1f}%")
    print(f"Recall@5: {r5 * 100:.1f}%")
    print(f"MRR:      {mrr:.4f}")

    # Benchmark assertions
    assert r3 >= 0.75, f"Expected Recall@3 >= 75%, got {r3 * 100:.1f}%"
    assert r5 >= 0.85, f"Expected Recall@5 >= 85%, got {r5 * 100:.1f}%"
    assert mrr >= 0.70, f"Expected MRR >= 0.70, got {mrr:.4f}"
