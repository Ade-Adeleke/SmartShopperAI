"""
Main chatbot application with dual-agent system.
Implements RAG Agent for product queries and Order Agent for autonomous order processing.
"""

import os
import json
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

import openai
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from .models import (
    Product, OrderModel, OrderItem, CustomerInfo, OrderStatus, 
    ChatMessage, SearchQuery
)
from .database import DatabaseManager
from .initialize_vector_store import VectorStoreManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Current active agent state"""
    RAG_AGENT = "rag_agent"
    ORDER_AGENT = "order_agent"


class ConversationalECommerceBot:
    """
    Dual-agent conversational e-commerce chatbot with RAG and autonomous ordering.
    """
    
    def __init__(self, 
                 openai_api_key: str = None,
                 vector_store_dir: str = "vector_store",
                 db_path: str = "orders.db"):
        """
        Initialize the chatbot with required components
        
        Args:
            openai_api_key: OpenAI API key (or from environment)
            vector_store_dir: Vector store directory path
            db_path: Database file path
        """
        # Initialize OpenAI client
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is required")
        
        self.openai_client = OpenAI(api_key=api_key)
        self.model = "gpt-4-turbo-preview"
        
        # Initialize components
        self.vector_store = VectorStoreManager(persist_directory=vector_store_dir)
        self.db_manager = DatabaseManager(db_path=db_path)
        
        # Conversation state
        self.chat_history: List[ChatMessage] = []
        self.current_agent = AgentState.RAG_AGENT
        self.order_context = {}  # Stores order-related context
        
        # Initialize conversation
        self._initialize_conversation()
        
        logger.info("ConversationalECommerceBot initialized successfully")
    
    def _initialize_conversation(self):
        """Initialize conversation with system message"""
        system_message = ChatMessage(
            role="system",
            content="""You are an intelligent e-commerce assistant with two specialized roles:

1. **RAG Agent** (Primary): Answer product questions using the vector store database. Provide accurate information about products, prices, availability, and specifications. Be helpful and conversational.

2. **Order Agent** (Secondary): When a customer shows clear purchase intent (phrases like "I'll take it", "I want to buy", "place order", "confirm order", "yes, please"), automatically transition to order processing mode.

**CRITICAL INSTRUCTIONS:**
- Use the search_products function to find product information
- When order intent is detected, use the create_order function
- Extract order details from conversation history (product, quantity, customer info)
- Always confirm order details before processing
- Be natural and conversational
- Never hallucinate product information - only use retrieved data
- Ask for clarification when needed

**Function Usage:**
- search_products: Use for any product-related questions
- create_order: Use when customer confirms they want to purchase

Start in RAG Agent mode and help customers find products they're interested in."""
        )
        self.chat_history.append(system_message)
    
    def _get_function_definitions(self) -> List[Dict[str, Any]]:
        """Define OpenAI function calling tools"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_products",
                    "description": "Search for products in the database using vector similarity. Use this for any product-related questions including prices, availability, specifications, or comparisons.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query describing what the customer is looking for"
                            },
                            "category": {
                                "type": "string",
                                "enum": ["Smartphones", "Laptops", "Tablets", "Audio", "Wearables", "Cameras", "Gaming", "Monitors", "Accessories", "Storage", "Smart Home"],
                                "description": "Optional category filter"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 5)",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_order",
                    "description": "Create an order when customer confirms purchase intent. Extract all details from conversation history.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "products": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "product_id": {"type": "string"},
                                        "product_name": {"type": "string"},
                                        "quantity": {"type": "integer", "minimum": 1},
                                        "unit_price": {"type": "number", "minimum": 0}
                                    },
                                    "required": ["product_id", "product_name", "quantity", "unit_price"]
                                },
                                "description": "List of products to order"
                            },
                            "customer_name": {
                                "type": "string",
                                "description": "Customer name if provided in conversation"
                            },
                            "customer_email": {
                                "type": "string",
                                "description": "Customer email if provided in conversation"
                            },
                            "customer_phone": {
                                "type": "string",
                                "description": "Customer phone if provided in conversation"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Any special notes or instructions"
                            }
                        },
                        "required": ["products"]
                    }
                }
            }
        ]
    
    def _search_products(self, query: str, category: str = None, max_results: int = 5) -> Dict[str, Any]:
        """
        Search for products using vector store
        
        Args:
            query: Search query
            category: Optional category filter
            max_results: Maximum results to return
            
        Returns:
            Search results with product information
        """
        try:
            # Search in vector store
            results = self.vector_store.search_products(
                query=query,
                n_results=max_results,
                category_filter=category
            )
            
            # Process and deduplicate results by product_id
            products_found = {}
            for result in results:
                metadata = result['metadata']
                product_id = metadata['product_id']
                
                if product_id not in products_found:
                    products_found[product_id] = {
                        'product_id': product_id,
                        'name': metadata['name'],
                        'price': metadata['price'],
                        'category': metadata['category'],
                        'stock_status': metadata['stock_status'],
                        'relevance_score': 1 - result['distance'],  # Convert distance to similarity
                        'content': result['document']
                    }
            
            # Sort by relevance and limit results
            sorted_products = sorted(
                products_found.values(),
                key=lambda x: x['relevance_score'],
                reverse=True
            )[:max_results]
            
            return {
                'success': True,
                'products': sorted_products,
                'total_found': len(sorted_products),
                'query': query
            }
            
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return {
                'success': False,
                'error': str(e),
                'products': [],
                'total_found': 0,
                'query': query
            }
    
    def _create_order(self, products: List[Dict], customer_name: str = None, 
                     customer_email: str = None, customer_phone: str = None, 
                     notes: str = None) -> Dict[str, Any]:
        """
        Create an order in the database
        
        Args:
            products: List of product dictionaries
            customer_name: Optional customer name
            customer_email: Optional customer email
            customer_phone: Optional customer phone
            notes: Optional order notes
            
        Returns:
            Order creation result
        """
        try:
            # Create order items
            order_items = []
            total_amount = 0
            
            for product_data in products:
                item = OrderItem(
                    product_id=product_data['product_id'],
                    product_name=product_data['product_name'],
                    quantity=product_data['quantity'],
                    unit_price=product_data['unit_price'],
                    total_price=product_data['quantity'] * product_data['unit_price']
                )
                order_items.append(item)
                total_amount += item.total_price
            
            # Create customer info if provided
            customer_info = None
            if any([customer_name, customer_email, customer_phone]):
                customer_info = CustomerInfo(
                    name=customer_name,
                    email=customer_email,
                    phone=customer_phone
                )
            
            # Create order (order_id will be generated by database)
            order_data = {
                "items": order_items,
                "customer_info": customer_info,
                "total_amount": total_amount,
                "status": OrderStatus.CONFIRMED,
                "notes": notes
            }
            
            # Create order without validation first, then validate after ID generation
            order = OrderModel(**order_data)
            
            # Save to database
            order_id = self.db_manager.create_order(order)
            
            return {
                'success': True,
                'order_id': order_id,
                'total_amount': total_amount,
                'items_count': len(order_items),
                'message': f"Order {order_id} created successfully!"
            }
            
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f"Failed to create order: {str(e)}"
            }
    
    def _execute_function_call(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a function call and return results"""
        try:
            if function_name == "search_products":
                return self._search_products(**arguments)
            elif function_name == "create_order":
                return self._create_order(**arguments)
            else:
                return {
                    'success': False,
                    'error': f"Unknown function: {function_name}"
                }
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _detect_order_intent(self, message: str) -> bool:
        """
        Detect if user message contains order/purchase intent
        
        Args:
            message: User message
            
        Returns:
            True if order intent detected
        """
        order_intent_patterns = [
            r'\b(i\'ll take|i want|i\'d like|i need)\b.*\b(it|this|that|one|them)\b',
            r'\b(buy|purchase|order|get)\b',
            r'\b(place.*order|confirm.*order)\b',
            r'\b(yes,?\s*(please)?|sure|okay|ok)\b.*\b(order|buy|purchase)\b',
            r'\b(add to cart|checkout|proceed)\b',
            r'\b(i\'ll buy|i want to buy|i\'d like to order)\b'
        ]
        
        message_lower = message.lower()
        for pattern in order_intent_patterns:
            if re.search(pattern, message_lower):
                return True
        
        return False
    
    def _format_products_response(self, search_result: Dict[str, Any]) -> str:
        """Format product search results for display"""
        if not search_result['success']:
            return f"I apologize, but I encountered an error searching for products: {search_result.get('error', 'Unknown error')}"
        
        products = search_result['products']
        if not products:
            return f"I couldn't find any products matching '{search_result['query']}'. Could you try a different search term or be more specific?"
        
        response_parts = [f"I found {len(products)} product(s) for '{search_result['query']}':"]
        
        for i, product in enumerate(products, 1):
            stock_emoji = "✅" if product['stock_status'] == 'in_stock' else "⚠️" if product['stock_status'] == 'low_stock' else "❌"
            response_parts.append(
                f"\n{i}. **{product['name']}** - ${product['price']:.2f} {stock_emoji}\n"
                f"   Category: {product['category']} | Stock: {product['stock_status'].replace('_', ' ').title()}"
            )
        
        response_parts.append("\nWould you like more details about any of these products, or are you interested in purchasing one?")
        
        return "\n".join(response_parts)
    
    def process_message(self, user_message: str) -> str:
        """
        Process user message and return bot response
        
        Args:
            user_message: User's message
            
        Returns:
            Bot's response
        """
        try:
            # Add user message to history
            user_chat_message = ChatMessage(role="user", content=user_message)
            self.chat_history.append(user_chat_message)
            
            # Prepare messages for OpenAI API - include full conversation context
            messages = self._prepare_messages_for_api()
            
            # Call OpenAI API with function calling
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self._get_function_definitions(),
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1000
            )
            
            message = response.choices[0].message
            
            # Handle function calls
            if message.tool_calls:
                return self._handle_function_calls(message)
            else:
                # Regular response without function calls
                bot_response = message.content
                bot_message = ChatMessage(role="assistant", content=bot_response)
                self.chat_history.append(bot_message)
                return bot_response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return f"I apologize, but I encountered an error processing your request: {str(e)}. Please try again."
    
    def _prepare_messages_for_api(self) -> List[Dict[str, Any]]:
        """Prepare messages for OpenAI API call"""
        messages = []
        
        for msg in self.chat_history:
            if msg.role == "system":
                messages.append({"role": "system", "content": msg.content})
            elif msg.role == "user":
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                if msg.tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": msg.tool_calls
                    })
                else:
                    messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == "tool":
                # Only include tool messages if they have a valid tool_call_id
                if msg.tool_calls and msg.tool_calls[0].get("id"):
                    messages.append({
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": msg.tool_calls[0]["id"]
                    })
        
        return messages
    
    def _handle_function_calls(self, message) -> str:
        """Handle function calls and return final response"""
        # Add assistant message with tool calls
        assistant_message = ChatMessage(
            role="assistant",
            content=message.content or "",
            tool_calls=[{
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            } for tool_call in message.tool_calls]
        )
        self.chat_history.append(assistant_message)
        
        # Execute each function call
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            logger.info(f"Executing function: {function_name} with args: {arguments}")
            
            # Execute function
            function_result = self._execute_function_call(function_name, arguments)
            
            # Add function result
            function_message = ChatMessage(
                role="tool",
                content=json.dumps(function_result),
                tool_calls=[{"id": tool_call.id}]
            )
            self.chat_history.append(function_message)
        
        # Get final response after function execution
        messages = self._prepare_messages_for_api()
        
        final_response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        bot_response = final_response.choices[0].message.content
        
        # Add final response to history
        bot_message = ChatMessage(role="assistant", content=bot_response)
        self.chat_history.append(bot_message)
        
        return bot_response
    
    def get_chat_history(self) -> List[Dict[str, Any]]:
        """Get formatted chat history"""
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in self.chat_history
            if msg.role in ["user", "assistant"]
        ]
    
    def clear_chat_history(self):
        """Clear chat history and reinitialize"""
        self.chat_history.clear()
        self.current_agent = AgentState.RAG_AGENT
        self.order_context.clear()
        self._initialize_conversation()
        logger.info("Chat history cleared and conversation reinitialized")
    
    def get_order_by_id(self, order_id: str) -> Optional[OrderModel]:
        """Get order details by ID"""
        return self.db_manager.get_order_by_id(order_id)
    
    def get_recent_orders(self, limit: int = 5) -> List[OrderModel]:
        """Get recent orders"""
        return self.db_manager.get_recent_orders(limit)


def main():
    """Main function for testing the chatbot"""
    import argparse
    
    parser = argparse.ArgumentParser(description="E-commerce Chatbot")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--vector-store-dir", default="vector_store", help="Vector store directory")
    parser.add_argument("--db-path", default="orders.db", help="Database file path")
    
    args = parser.parse_args()
    
    try:
        # Initialize chatbot
        print("Initializing E-commerce Chatbot...")
        bot = ConversationalECommerceBot(
            vector_store_dir=args.vector_store_dir,
            db_path=args.db_path
        )
        print("Chatbot initialized successfully!")
        
        if args.interactive:
            print("\n" + "="*50)
            print("E-COMMERCE CHATBOT - Interactive Mode")
            print("Type 'quit' to exit, 'clear' to clear history")
            print("="*50 + "\n")
            
            while True:
                try:
                    user_input = input("You: ").strip()
                    
                    if user_input.lower() in ['quit', 'exit', 'q']:
                        print("Goodbye!")
                        break
                    elif user_input.lower() == 'clear':
                        bot.clear_chat_history()
                        print("Chat history cleared!")
                        continue
                    elif not user_input:
                        continue
                    
                    # Process message
                    response = bot.process_message(user_input)
                    print(f"Bot: {response}\n")
                    
                except KeyboardInterrupt:
                    print("\nGoodbye!")
                    break
                except Exception as e:
                    print(f"Error: {e}")
        else:
            # Test with sample queries
            test_queries = [
                "What's the price of the iPhone 15 Pro?",
                "Show me gaming laptops",
                "I'll take the iPhone 15 Pro",
                "Do you have wireless headphones?"
            ]
            
            print("\nTesting with sample queries:")
            for query in test_queries:
                print(f"\nUser: {query}")
                response = bot.process_message(query)
                print(f"Bot: {response}")
    
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
