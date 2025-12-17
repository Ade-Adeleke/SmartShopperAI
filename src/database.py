"""
Database operations for order management.
Implements SQLite database with CRUD operations for orders.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
from contextlib import contextmanager

from .models import OrderModel, OrderItem, CustomerInfo, OrderStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database operations for orders"""
    
    def __init__(self, db_path: str = "orders.db"):
        """Initialize database manager with path"""
        self.db_path = Path(db_path)
        self.init_database()
    
    def init_database(self) -> None:
        """Initialize database with required tables"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create orders table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id TEXT PRIMARY KEY,
                        customer_name TEXT,
                        customer_email TEXT,
                        customer_phone TEXT,
                        customer_address TEXT,
                        total_amount REAL NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        notes TEXT,
                        items_json TEXT NOT NULL
                    )
                """)
                
                # Create order_items table for normalized storage
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS order_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        product_name TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        unit_price REAL NOT NULL,
                        total_price REAL NOT NULL,
                        FOREIGN KEY (order_id) REFERENCES orders (order_id)
                    )
                """)
                
                # Create indexes for better performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)")
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def generate_order_id(self) -> str:
        """Generate unique order ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"ORD-{timestamp}-{unique_id}"
    
    def create_order(self, order: OrderModel) -> str:
        """
        Create a new order in the database
        
        Args:
            order: OrderModel instance with validated data
            
        Returns:
            str: Created order ID
            
        Raises:
            ValueError: If order validation fails
            sqlite3.Error: If database operation fails
        """
        try:
            # Generate order ID if not provided
            if not order.order_id or order.order_id == "":
                order.order_id = self.generate_order_id()
            
            # Validate order
            order_dict = order.dict()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if order ID already exists
                cursor.execute("SELECT order_id FROM orders WHERE order_id = ?", (order.order_id,))
                if cursor.fetchone():
                    raise ValueError(f"Order ID {order.order_id} already exists")
                
                # Prepare customer info
                customer_info = order.customer_info
                customer_name = customer_info.name if customer_info else None
                customer_email = customer_info.email if customer_info else None
                customer_phone = customer_info.phone if customer_info else None
                customer_address = customer_info.address if customer_info else None
                
                # Insert order
                cursor.execute("""
                    INSERT INTO orders (
                        order_id, customer_name, customer_email, customer_phone, 
                        customer_address, total_amount, status, created_at, notes, items_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order.order_id,
                    customer_name,
                    customer_email,
                    customer_phone,
                    customer_address,
                    order.total_amount,
                    order.status.value if hasattr(order.status, 'value') else order.status,
                    order.created_at.isoformat(),
                    order.notes,
                    json.dumps([item.dict() for item in order.items])
                ))
                
                # Insert order items
                for item in order.items:
                    cursor.execute("""
                        INSERT INTO order_items (
                            order_id, product_id, product_name, quantity, unit_price, total_price
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        order.order_id,
                        item.product_id,
                        item.product_name,
                        item.quantity,
                        item.unit_price,
                        item.total_price
                    ))
                
                conn.commit()
                logger.info(f"Order {order.order_id} created successfully")
                return order.order_id
                
        except sqlite3.Error as e:
            logger.error(f"Database error creating order: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            raise
    
    def get_order_by_id(self, order_id: str) -> Optional[OrderModel]:
        """
        Retrieve order by ID
        
        Args:
            order_id: Order identifier
            
        Returns:
            OrderModel instance or None if not found
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get order data
                cursor.execute("""
                    SELECT * FROM orders WHERE order_id = ?
                """, (order_id,))
                
                order_row = cursor.fetchone()
                if not order_row:
                    return None
                
                # Parse order data
                order_data = dict(order_row)
                
                # Parse items from JSON
                items_data = json.loads(order_data['items_json'])
                items = [OrderItem(**item_data) for item_data in items_data]
                
                # Create customer info if available
                customer_info = None
                if any([order_data['customer_name'], order_data['customer_email'], 
                       order_data['customer_phone'], order_data['customer_address']]):
                    customer_info = CustomerInfo(
                        name=order_data['customer_name'],
                        email=order_data['customer_email'],
                        phone=order_data['customer_phone'],
                        address=order_data['customer_address']
                    )
                
                # Create order model
                order = OrderModel(
                    order_id=order_data['order_id'],
                    items=items,
                    customer_info=customer_info,
                    total_amount=order_data['total_amount'],
                    status=OrderStatus(order_data['status']),
                    created_at=datetime.fromisoformat(order_data['created_at']),
                    notes=order_data['notes']
                )
                
                return order
                
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving order {order_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving order {order_id}: {e}")
            return None
    
    def update_order_status(self, order_id: str, status: OrderStatus) -> bool:
        """
        Update order status
        
        Args:
            order_id: Order identifier
            status: New order status
            
        Returns:
            bool: True if updated successfully
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE orders SET status = ? WHERE order_id = ?
                """, (status.value, order_id))
                
                if cursor.rowcount == 0:
                    logger.warning(f"Order {order_id} not found for status update")
                    return False
                
                conn.commit()
                logger.info(f"Order {order_id} status updated to {status.value}")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Database error updating order status: {e}")
            return False
    
    def get_orders_by_status(self, status: OrderStatus) -> List[OrderModel]:
        """
        Get all orders with specific status
        
        Args:
            status: Order status to filter by
            
        Returns:
            List of OrderModel instances
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT order_id FROM orders WHERE status = ? ORDER BY created_at DESC
                """, (status.value,))
                
                order_ids = [row['order_id'] for row in cursor.fetchall()]
                orders = []
                
                for order_id in order_ids:
                    order = self.get_order_by_id(order_id)
                    if order:
                        orders.append(order)
                
                return orders
                
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving orders by status: {e}")
            return []
    
    def get_recent_orders(self, limit: int = 10) -> List[OrderModel]:
        """
        Get recent orders
        
        Args:
            limit: Maximum number of orders to return
            
        Returns:
            List of recent OrderModel instances
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT order_id FROM orders ORDER BY created_at DESC LIMIT ?
                """, (limit,))
                
                order_ids = [row['order_id'] for row in cursor.fetchall()]
                orders = []
                
                for order_id in order_ids:
                    order = self.get_order_by_id(order_id)
                    if order:
                        orders.append(order)
                
                return orders
                
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving recent orders: {e}")
            return []
    
    def delete_order(self, order_id: str) -> bool:
        """
        Delete order (for testing purposes)
        
        Args:
            order_id: Order identifier
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete order items first (foreign key constraint)
                cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
                
                # Delete order
                cursor.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
                
                if cursor.rowcount == 0:
                    logger.warning(f"Order {order_id} not found for deletion")
                    return False
                
                conn.commit()
                logger.info(f"Order {order_id} deleted successfully")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Database error deleting order: {e}")
            return False
    
    def get_order_statistics(self) -> Dict[str, Any]:
        """
        Get order statistics
        
        Returns:
            Dictionary with order statistics
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Total orders
                cursor.execute("SELECT COUNT(*) as total FROM orders")
                total_orders = cursor.fetchone()['total']
                
                # Orders by status
                cursor.execute("""
                    SELECT status, COUNT(*) as count FROM orders GROUP BY status
                """)
                status_counts = {row['status']: row['count'] for row in cursor.fetchall()}
                
                # Total revenue
                cursor.execute("SELECT SUM(total_amount) as revenue FROM orders WHERE status != 'cancelled'")
                total_revenue = cursor.fetchone()['revenue'] or 0
                
                # Average order value
                cursor.execute("""
                    SELECT AVG(total_amount) as avg_value FROM orders WHERE status != 'cancelled'
                """)
                avg_order_value = cursor.fetchone()['avg_value'] or 0
                
                return {
                    'total_orders': total_orders,
                    'status_counts': status_counts,
                    'total_revenue': round(total_revenue, 2),
                    'average_order_value': round(avg_order_value, 2)
                }
                
        except sqlite3.Error as e:
            logger.error(f"Database error getting statistics: {e}")
            return {}
    
    def close(self) -> None:
        """Close database connection (if needed for cleanup)"""
        # SQLite connections are closed automatically with context manager
        pass


# Global database instance
db_manager = DatabaseManager()
