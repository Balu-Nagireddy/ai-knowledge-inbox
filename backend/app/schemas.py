from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator

class IngestRequest(BaseModel):
    source_type: Literal["note", "url"] = Field(..., description="Type of content: 'note' or 'url'")
    content: Optional[str] = Field(None, description="Plain text note content (required if source_type is 'note')")
    url: Optional[str] = Field(None, description="Web page URL to fetch (required if source_type is 'url')")
    title: Optional[str] = Field(None, description="Optional custom title for the note or URL")

    @model_validator(mode="after")
    def validate_inputs(self):
        if self.source_type == "note":
            if not self.content or not self.content.strip():
                raise ValueError("Field 'content' cannot be empty when source_type is 'note'.")
        elif self.source_type == "url":
            if not self.url or not self.url.strip():
                raise ValueError("Field 'url' cannot be empty when source_type is 'url'.")
            url_str = self.url.strip().lower()
            if not (url_str.startswith("http://") or url_str.startswith("https://")):
                raise ValueError("Field 'url' must start with http:// or https://")
        return self

class IngestResponse(BaseModel):
    id: str
    source_type: str
    title: str
    source_url: Optional[str] = None
    chunk_count: int
    created_at: str

class ItemResponse(BaseModel):
    id: str
    source_type: str
    source_url: Optional[str] = None
    title: str
    raw_content: str
    chunk_count: int
    created_at: str

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000, description="The user question to answer")
    top_k: Optional[int] = Field(4, ge=1, le=10, description="Number of top chunks to retrieve for context")

class SourceSnippet(BaseModel):
    chunk_id: str
    item_id: str
    source_title: str
    source_type: str
    source_url: Optional[str] = None
    content: str
    similarity_score: float

class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[SourceSnippet]
