"""
Test scenarios for the conversational e-commerce chatbot.
Tests both RAG Agent and Order Agent functionality.
"""

import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.models import Product, OrderModel, OrderItem, CustomerInfo, OrderStatus
from src.database import DatabaseManager
from src.initialize_vector_store import VectorStoreManager
from src.chatbot import ConversationalECommerceBot


class TestDatabaseManager:
    """Test database operations"""
    
    def setup_method(self):
        """Setup test database"""
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        self.db_manager = DatabaseManager(db_path=self.temp_db.name)
    
    def teardown_method(self):
        """Cleanup test database"""
        os.unlink(self.temp_db.name)
    
    def test_create_order(self):
        """Test order creation"""
        # Create test order
        order_item = OrderItem(
            product_id="TEST-001",
            product_name="Test Product",
            quantity=2,
            unit_price=99.99,
            total_price=199.98
        )
        
        customer_info = CustomerInfo(
            name="John Doe",
            email="john@example.com",
            phone="1234567890"
        )
        
        order = OrderModel(
            order_id="",
            items=[order_item],
            customer_info=customer_info,
            total_amount=199.98,
            status=OrderStatus.CONFIRMED
        )
        
        # Create order
        order_id = self.db_manager.create_order(order)
        assert order_id is not None
        assert order_id.startswith("ORD-")
        
        # Retrieve order
        retrieved_order = self.db_manager.get_order_by_id(order_id)
        assert retrieved_order is not None
        assert retrieved_order.order_id == order_id
        assert len(retrieved_order.items) == 1
        assert retrieved_order.items[0].product_name == "Test Product"
        assert retrieved_order.customer_info.name == "John Doe"
    
    def test_order_validation(self):
        """Test order validation"""
        # Test invalid quantity
        with pytest.raises(ValueError):
            OrderItem(
                product_id="TEST-001",
                product_name="Test Product",
                quantity=0,  # Invalid
                unit_price=99.99,
                total_price=0
            )
        
        # Test invalid price
        with pytest.raises(ValueError):
            OrderItem(
                product_id="TEST-001",
                product_name="Test Product",
                quantity=1,
                unit_price=-10,  # Invalid
                total_price=-10
            )


class TestVectorStoreManager:
    """Test vector store operations"""
    
    def setup_method(self):
        """Setup test vector store"""
        self.temp_dir = tempfile.mkdtemp()
        
        # Create test products file
        self.products_file = os.path.join(self.temp_dir, "test_products.json")
        test_products = [
            {
                "product_id": "TEST-001",
                "name": "Test iPhone",
                "description": "A test iPhone for testing purposes",
                "price": 999.99,
                "category": "Smartphones",
                "stock_status": "in_stock",
                "specifications": "Test specs"
            },
            {
                "product_id": "TEST-002", 
                "name": "Test Laptop",
                "description": "A test laptop for testing purposes",
                "price": 1299.99,
                "category": "Laptops",
                "stock_status": "in_stock",
                "specifications": "Test laptop specs"
            }
        ]
        
        import json
        with open(self.products_file, 'w') as f:
            json.dump(test_products, f)
    
    def teardown_method(self):
        """Cleanup test vector store"""
        shutil.rmtree(self.temp_dir)
    
    @patch('src.initialize_vector_store.OpenAI')
    def test_load_products(self, mock_openai):
        """Test product loading"""
        vs_manager = VectorStoreManager(persist_directory=self.temp_dir)
        products = vs_manager.load_products(self.products_file)
        
        assert len(products) == 2
        assert products[0].name == "Test iPhone"
        assert products[1].name == "Test Laptop"
    
    def test_create_product_text(self):
        """Test product text creation"""
        vs_manager = VectorStoreManager(persist_directory=self.temp_dir)
        
        product = Product(
            product_id="TEST-001",
            name="Test Product",
            description="Test description",
            price=99.99,
            category="Smartphones",
            stock_status="in_stock"
        )
        
        text = vs_manager.create_product_text(product)
        assert "Test Product" in text
        assert "$99.99" in text
        assert "Smartphones" in text


class TestConversationalBot:
    """Test chatbot functionality"""
    
    def setup_method(self):
        """Setup test bot"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        
        # Mock OpenAI API key
        os.environ['OPENAI_API_KEY'] = 'test-key'
    
    def teardown_method(self):
        """Cleanup test bot"""
        shutil.rmtree(self.temp_dir)
        os.unlink(self.temp_db.name)
        if 'OPENAI_API_KEY' in os.environ:
            del os.environ['OPENAI_API_KEY']
    
    @patch('src.chatbot.OpenAI')
    @patch('src.initialize_vector_store.OpenAI')
    def test_bot_initialization(self, mock_vs_openai, mock_bot_openai):
        """Test bot initialization"""
        bot = ConversationalECommerceBot(
            openai_api_key="test-key",
            vector_store_dir=self.temp_dir,
            db_path=self.temp_db.name
        )
        
        assert bot is not None
        assert len(bot.chat_history) == 1  # System message
        assert bot.chat_history[0].role == "system"
    
    def test_order_intent_detection(self):
        """Test order intent detection"""
        bot = ConversationalECommerceBot(
            openai_api_key="test-key",
            vector_store_dir=self.temp_dir,
            db_path=self.temp_db.name
        )
        
        # Test positive cases
        assert bot._detect_order_intent("I'll take it")
        assert bot._detect_order_intent("I want to buy this")
        assert bot._detect_order_intent("Place order please")
        assert bot._detect_order_intent("Yes, I'll buy it")
        
        # Test negative cases
        assert not bot._detect_order_intent("What's the price?")
        assert not bot._detect_order_intent("Tell me more about this")
        assert not bot._detect_order_intent("Do you have laptops?")
    
    def test_search_products_function(self):
        """Test product search function"""
        bot = ConversationalECommerceBot(
            openai_api_key="test-key",
            vector_store_dir=self.temp_dir,
            db_path=self.temp_db.name
        )
        
        # Mock vector store search
        with patch.object(bot.vector_store, 'search_products') as mock_search:
            mock_search.return_value = [
                {
                    'metadata': {
                        'product_id': 'TEST-001',
                        'name': 'Test iPhone',
                        'price': 999.99,
                        'category': 'Smartphones',
                        'stock_status': 'in_stock'
                    },
                    'distance': 0.1,
                    'document': 'Test iPhone description'
                }
            ]
            
            result = bot._search_products("iPhone")
            
            assert result['success'] is True
            assert len(result['products']) == 1
            assert result['products'][0]['name'] == 'Test iPhone'
    
    def test_create_order_function(self):
        """Test order creation function"""
        bot = ConversationalECommerceBot(
            openai_api_key="test-key",
            vector_store_dir=self.temp_dir,
            db_path=self.temp_db.name
        )
        
        products = [
            {
                'product_id': 'TEST-001',
                'product_name': 'Test iPhone',
                'quantity': 1,
                'unit_price': 999.99
            }
        ]
        
        result = bot._create_order(
            products=products,
            customer_name="John Doe",
            customer_email="john@example.com"
        )
        
        assert result['success'] is True
        assert 'order_id' in result
        assert result['total_amount'] == 999.99


class TestManualScenarios:
    """Manual test scenarios for documentation"""
    
    def test_scenario_1_product_price_query(self):
        """
        Scenario 1: Product Price Query
        User asks about iPhone price, bot should use search_products function
        Expected: Bot returns accurate price information from vector store
        """
        # This would be tested manually or with integration tests
        # Expected flow:
        # User: "What's the price of iPhone 15 Pro?"
        # Bot: Calls search_products("iPhone 15 Pro")
        # Bot: "The iPhone 15 Pro is priced at $999.99 and is currently in stock."
        pass
    
    def test_scenario_2_multi_turn_discussion(self):
        """
        Scenario 2: Multi-turn Product Discussion
        User asks about laptops, then asks for gaming laptops specifically
        Expected: Bot maintains context and provides relevant information
        """
        # Expected flow:
        # User: "Do you have laptops?"
        # Bot: Shows available laptops
        # User: "Which ones are good for gaming?"
        # Bot: Filters and shows gaming laptops with specifications
        pass
    
    def test_scenario_3_order_confirmation(self):
        """
        Scenario 3: Order Confirmation with Extraction
        User discusses product, then confirms purchase
        Expected: Bot extracts order details from conversation and creates order
        """
        # Expected flow:
        # User: "Tell me about the MacBook Pro"
        # Bot: Provides MacBook Pro information
        # User: "I'll take one"
        # Bot: Calls create_order with MacBook Pro details
        # Bot: "Your order has been confirmed! Order ID: #ORD-..."
        pass
    
    def test_scenario_4_ambiguous_query(self):
        """
        Scenario 4: Ambiguous Query Handling
        User asks vague question, bot should ask for clarification
        Expected: Bot asks clarifying questions instead of making assumptions
        """
        # Expected flow:
        # User: "I want one"
        # Bot: "I'd be happy to help! Which product would you like to order?"
        pass
    
    def test_scenario_5_invalid_order_rejection(self):
        """
        Scenario 5: Invalid Order Rejection
        User tries to order out-of-stock item or invalid quantity
        Expected: Bot validates and rejects invalid orders gracefully
        """
        # Expected flow:
        # User: "I want 1000 iPhones"
        # Bot: "I'm sorry, but we can only process orders up to 100 units per item."
        pass


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
