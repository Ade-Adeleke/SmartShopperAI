"""
E-commerce Conversational AI Chatbot Package

A dual-agent system combining RAG-based product information retrieval
with autonomous order processing using OpenAI Function Calling.
"""

__version__ = "1.0.0"
__author__ = "AI Engineer"

from .models import Product, OrderModel, OrderItem, CustomerInfo, OrderStatus
from .database import DatabaseManager
from .initialize_vector_store import VectorStoreManager
from .chatbot import ConversationalECommerceBot, AgentState

__all__ = [
    "Product",
    "OrderModel", 
    "OrderItem",
    "CustomerInfo",
    "OrderStatus",
    "DatabaseManager",
    "VectorStoreManager", 
    "ConversationalECommerceBot",
    "AgentState"
]
