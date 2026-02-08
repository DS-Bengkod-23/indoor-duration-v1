"""Standard API Response Schemas"""
from pydantic import BaseModel
from typing import Optional, Any, Generic, TypeVar


DataT = TypeVar("DataT")


class StandardResponse(BaseModel, Generic[DataT]):
    """Standard API response wrapper"""
    success: bool
    message: str
    data: Optional[DataT] = None


class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[dict] = None


class PaginationParams(BaseModel):
    """Pagination parameters"""
    page: int = 1
    page_size: int = 20
    total: Optional[int] = None


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Paginated response"""
    success: bool = True
    message: str = "Success"
    data: list[DataT]
    pagination: PaginationParams
