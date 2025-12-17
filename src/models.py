"""
Pydantic models for data validation and serialization.
Defines Product and Order models with comprehensive validation rules.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, validator, model_validator
from enum import Enum


class StockStatus(str, Enum):
    """Stock status enumeration"""
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


class ProductCategory(str, Enum):
    """Product category enumeration"""
    SMARTPHONES = "Smartphones"
    LAPTOPS = "Laptops"
    TABLETS = "Tablets"
    AUDIO = "Audio"
    WEARABLES = "Wearables"
    CAMERAS = "Cameras"
    GAMING = "Gaming"
    MONITORS = "Monitors"
    ACCESSORIES = "Accessories"
    STORAGE = "Storage"
    SMART_HOME = "Smart Home"


class Product(BaseModel):
    """Product model with comprehensive validation"""
    product_id: str = Field(..., min_length=1, max_length=50, description="Unique product identifier")
    name: str = Field(..., min_length=1, max_length=200, description="Product name")
    description: str = Field(..., min_length=10, max_length=2000, description="Product description")
    price: float = Field(..., gt=0, le=50000, description="Product price in USD")
    category: ProductCategory = Field(..., description="Product category")
    stock_status: StockStatus = Field(..., description="Current stock status")
    specifications: Optional[str] = Field(None, max_length=1000, description="Technical specifications")

    @validator('price')
    def validate_price(cls, v):
        """Validate price is reasonable and properly formatted"""
        if v <= 0:
            raise ValueError('Price must be greater than 0')
        if v > 50000:
            raise ValueError('Price cannot exceed $50,000')
        # Round to 2 decimal places
        return round(v, 2)

    @validator('product_id')
    def validate_product_id(cls, v):
        """Validate product ID format"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Product ID cannot be empty')
        return v.strip().upper()

    class Config:
        """Pydantic configuration"""
        use_enum_values = True
        validate_assignment = True


class CustomerInfo(BaseModel):
    """Customer information model"""
    name: Optional[str] = Field(None, min_length=2, max_length=100, description="Customer full name")
    email: Optional[str] = Field(None, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', description="Customer email")
    phone: Optional[str] = Field(None, min_length=10, max_length=20, description="Customer phone number")
    address: Optional[str] = Field(None, min_length=10, max_length=500, description="Customer address")

    @validator('phone')
    def validate_phone(cls, v):
        """Validate phone number format"""
        if v:
            # Remove all non-digit characters
            digits_only = ''.join(filter(str.isdigit, v))
            if len(digits_only) < 10:
                raise ValueError('Phone number must have at least 10 digits')
        return v

    @validator('name')
    def validate_name(cls, v):
        """Validate customer name"""
        if v:
            v = v.strip()
            if len(v) < 2:
                raise ValueError('Name must be at least 2 characters long')
        return v


class OrderItem(BaseModel):
    """Individual order item model"""
    product_id: str = Field(..., min_length=1, description="Product identifier")
    product_name: str = Field(..., min_length=1, max_length=200, description="Product name")
    quantity: int = Field(..., gt=0, le=100, description="Quantity ordered")
    unit_price: float = Field(..., gt=0, description="Price per unit")
    total_price: float = Field(..., gt=0, description="Total price for this item")

    @validator('total_price')
    def validate_total_price(cls, v, values):
        """Validate total price matches quantity * unit_price"""
        if 'quantity' in values and 'unit_price' in values:
            expected_total = round(values['quantity'] * values['unit_price'], 2)
            if abs(v - expected_total) > 0.01:  # Allow for small floating point differences
                raise ValueError(f'Total price {v} does not match quantity * unit_price = {expected_total}')
        return round(v, 2)

    @validator('quantity')
    def validate_quantity(cls, v):
        """Validate quantity is reasonable"""
        if v <= 0:
            raise ValueError('Quantity must be greater than 0')
        if v > 100:
            raise ValueError('Quantity cannot exceed 100 per item')
        return v


class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderModel(BaseModel):
    """Complete order model with validation"""
    order_id: str = Field(default="", description="Unique order identifier")
    items: List[OrderItem] = Field(..., min_items=1, max_items=20, description="List of ordered items")
    customer_info: Optional[CustomerInfo] = Field(None, description="Customer information")
    total_amount: float = Field(..., gt=0, description="Total order amount")
    status: OrderStatus = Field(default=OrderStatus.PENDING, description="Order status")
    created_at: datetime = Field(default_factory=datetime.now, description="Order creation timestamp")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional order notes")

    @validator('total_amount')
    def validate_total_amount(cls, v, values):
        """Validate total amount matches sum of all item totals"""
        if 'items' in values and values['items']:
            expected_total = sum(item.total_price for item in values['items'])
            if abs(v - expected_total) > 0.01:  # Allow for small floating point differences
                raise ValueError(f'Total amount {v} does not match sum of item totals = {expected_total}')
        return round(v, 2)

    @validator('items')
    def validate_items(cls, v):
        """Validate order items"""
        if not v:
            raise ValueError('Order must contain at least one item')
        if len(v) > 20:
            raise ValueError('Order cannot contain more than 20 different items')
        
        # Check for duplicate product IDs
        product_ids = [item.product_id for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError('Order cannot contain duplicate products')
        
        return v

    @model_validator(mode='before')
    @classmethod
    def validate_order_consistency(cls, values):
        """Validate overall order consistency"""
        if isinstance(values, dict):
            items = values.get('items', [])
            total_amount = values.get('total_amount', 0)
            
            if items and total_amount:
                calculated_total = sum(item.total_price for item in items)
                if abs(total_amount - calculated_total) > 0.01:
                    values['total_amount'] = round(calculated_total, 2)
        
        return values

    def calculate_total(self) -> float:
        """Calculate total order amount from items"""
        return round(sum(item.total_price for item in self.items), 2)

    def add_item(self, product_id: str, product_name: str, quantity: int, unit_price: float) -> None:
        """Add an item to the order"""
        total_price = round(quantity * unit_price, 2)
        new_item = OrderItem(
            product_id=product_id,
            product_name=product_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price
        )
        self.items.append(new_item)
        self.total_amount = self.calculate_total()

    class Config:
        """Pydantic configuration"""
        use_enum_values = True
        validate_assignment = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SearchQuery(BaseModel):
    """Search query model for product searches"""
    query: str = Field(..., min_length=1, max_length=200, description="Search query string")
    category: Optional[ProductCategory] = Field(None, description="Filter by category")
    max_price: Optional[float] = Field(None, gt=0, description="Maximum price filter")
    min_price: Optional[float] = Field(None, gt=0, description="Minimum price filter")
    in_stock_only: bool = Field(default=True, description="Show only in-stock items")

    @validator('max_price')
    def validate_max_price(cls, v, values):
        """Validate max_price is greater than min_price"""
        if v is not None and 'min_price' in values and values['min_price'] is not None:
            if v <= values['min_price']:
                raise ValueError('Maximum price must be greater than minimum price')
        return v

    class Config:
        """Pydantic configuration"""
        use_enum_values = True


class ChatMessage(BaseModel):
    """Chat message model for conversation history"""
    role: Literal["user", "assistant", "system", "tool"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.now, description="Message timestamp")
    function_call: Optional[dict] = Field(None, description="Function call data if applicable")
    tool_calls: Optional[List[dict]] = Field(None, description="Tool calls data if applicable")
    
    @validator('content')
    def validate_content(cls, v, values):
        """Validate content - allow empty for assistant messages with tool calls"""
        role = values.get('role')
        
        # Allow empty content for assistant and tool messages (function calling)
        if role in ['assistant', 'tool']:
            return v
        
        # Require non-empty content for user and system messages
        if role in ['user', 'system'] and (not v or len(v.strip()) == 0):
            raise ValueError('Content cannot be empty for this message type')
        
        return v

    class Config:
        """Pydantic configuration"""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
