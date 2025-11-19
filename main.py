import os
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId

from database import db
from schemas import BlogPost

app = FastAPI(title="Blog API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BlogPostOut(BaseModel):
    title: str
    slug: str
    excerpt: str
    content: str
    author: str
    tags: List[str]
    cover_image: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@app.get("/")
def read_root():
    return {"message": "Blog API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# Utilities

def ensure_indexes():
    if db is None:
        return
    db["blogpost"].create_index("slug", unique=True)
    db["blogpost"].create_index([("title", 1)])
    db["blogpost"].create_index([("tags", 1)])
    db["blogpost"].create_index([("created_at", -1)])


ensure_indexes()


# Seed endpoint to generate 1500 sample posts
@app.post("/api/seed")
def seed_posts(total: int = 1500):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    collection = db["blogpost"]
    existing = collection.estimated_document_count()
    if existing >= total:
        return {"status": "ok", "message": f"Database already has {existing} posts"}

    authors = [
        "Alex Carter", "Jordan Lee", "Taylor Morgan", "Riley Brooks", "Casey Kim",
        "Avery Patel", "Jamie Rivera", "Morgan Blake", "Quinn Parker", "Drew Nguyen"
    ]
    tag_pool = [
        "tech", "design", "business", "ai", "dev", "life", "product", "growth", "marketing", "tutorial"
    ]

    lorem_paras = [
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vivamus at mi sit amet odio ultrices pulvinar.",
        "Curabitur at sapien sollicitudin, aliquam neque et, lacinia augue. Mauris nec massa quis justo cursus.",
        "Suspendisse potenti. Ut a ligula sed arcu vestibulum dapibus vitae non mi. Donec vel sagittis risus.",
        "Integer vitae dui at sapien volutpat ullamcorper. Praesent feugiat, enim vitae suscipit dapibus, urna massa.",
        "Sed sit amet tortor vitae justo scelerisque rhoncus. Cras at semper elit. Proin pretium, sapien ut bibendum."
    ]

    docs = []
    now = datetime.now(timezone.utc)
    for i in range(1, total + 1):
        idx = str(i).zfill(4)
        title = f"Sample Blog Post {idx}"
        slug = f"sample-blog-post-{idx}"
        excerpt = f"This is a short summary for post {idx}. {lorem_paras[i % len(lorem_paras)]}"
        # Create a few paragraphs of content
        content = "\n\n".join([
            f"# {title}",
            lorem_paras[(i + 0) % len(lorem_paras)],
            lorem_paras[(i + 1) % len(lorem_paras)],
            lorem_paras[(i + 2) % len(lorem_paras)],
            "## Key Takeaways",
            "- Insight one about the topic",
            "- Practical tip for readers",
            "- Closing thought to inspire action",
        ])
        tags = list({tag_pool[i % len(tag_pool)], tag_pool[(i * 3) % len(tag_pool)], tag_pool[(i * 7) % len(tag_pool)]})
        author = authors[i % len(authors)]
        docs.append({
            "title": title,
            "slug": slug,
            "excerpt": excerpt,
            "content": content,
            "author": author,
            "tags": tags,
            "cover_image": None,
            "created_at": now,
            "updated_at": now,
        })

    # Bulk insert missing docs only
    inserted = 0
    for doc in docs:
        try:
            collection.insert_one(doc)
            inserted += 1
        except Exception:
            # likely duplicate slug, skip
            pass

    return {"status": "ok", "inserted": inserted, "total": collection.estimated_document_count()}


# List posts with pagination and search
@app.get("/api/posts")
def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    q: Optional[str] = Query(None),
    tag: Optional[str] = Query(None)
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    collection = db["blogpost"]

    filter_q = {}
    if q:
        filter_q["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"excerpt": {"$regex": q, "$options": "i"}},
            {"content": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    if tag:
        filter_q["tags"] = tag

    total = collection.count_documents(filter_q)

    cursor = (
        collection
        .find(filter_q, {"content": 0})  # exclude heavy content for listing
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )

    items = []
    for d in cursor:
        d["_id"] = str(d["_id"])  # not used but safe stringify
        items.append(d)

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit if limit else 1,
        "items": items,
    }


# Get single post by slug
@app.get("/api/posts/{slug}", response_model=BlogPostOut)
def get_post(slug: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    doc = db["blogpost"].find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")

    doc.pop("_id", None)
    return doc


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
