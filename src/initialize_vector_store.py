"""
Vector store initialization for product embeddings.
Loads products, generates embeddings, and stores in ChromaDB for RAG retrieval.
"""

import json
import os
import logging
from typing import List, Dict, Any
from pathlib import Path

import chromadb
from chromadb.config import Settings
import openai
from openai import OpenAI
from dotenv import load_dotenv

from .models import Product

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VectorStoreManager:
    """Manages ChromaDB vector store for product embeddings"""
    
    def __init__(self, 
                 persist_directory: str = "vector_store",
                 collection_name: str = "products",
                 embedding_model: str = "text-embedding-3-small"):
        """
        Initialize vector store manager
        
        Args:
            persist_directory: Directory to persist ChromaDB data
            collection_name: Name of the ChromaDB collection
            embedding_model: OpenAI embedding model to use
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        
        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.openai_client = OpenAI(api_key=api_key)
        
        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
            logger.info(f"Loaded existing collection '{self.collection_name}'")
        except ValueError:
            # Collection doesn't exist, create it
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Product embeddings for e-commerce RAG"}
            )
            logger.info(f"Created new collection '{self.collection_name}'")
    
    def load_products(self, products_file: str) -> List[Product]:
        """
        Load products from JSON file
        
        Args:
            products_file: Path to products JSON file
            
        Returns:
            List of validated Product instances
        """
        try:
            with open(products_file, 'r', encoding='utf-8') as f:
                products_data = json.load(f)
            
            products = []
            for product_data in products_data:
                try:
                    product = Product(**product_data)
                    products.append(product)
                except Exception as e:
                    logger.error(f"Error validating product {product_data.get('product_id', 'unknown')}: {e}")
                    continue
            
            logger.info(f"Loaded {len(products)} valid products")
            return products
            
        except FileNotFoundError:
            logger.error(f"Products file not found: {products_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing products JSON: {e}")
            raise
    
    def create_product_text(self, product: Product) -> str:
        """
        Create searchable text representation of product
        
        Args:
            product: Product instance
            
        Returns:
            Formatted text for embedding
        """
        text_parts = [
            f"Product: {product.name}",
            f"Category: {product.category}",
            f"Price: ${product.price:.2f}",
            f"Stock: {product.stock_status.replace('_', ' ').title()}",
            f"Description: {product.description}"
        ]
        
        if product.specifications:
            text_parts.append(f"Specifications: {product.specifications}")
        
        return "\n".join(text_parts)
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using OpenAI API
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=texts
            )
            
            embeddings = [data.embedding for data in response.data]
            logger.info(f"Generated {len(embeddings)} embeddings")
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise
    
    def chunk_products(self, products: List[Product]) -> List[Dict[str, Any]]:
        """
        Create chunks from products for better retrieval
        
        Args:
            products: List of Product instances
            
        Returns:
            List of product chunks with metadata
        """
        chunks = []
        
        for product in products:
            # Main product chunk
            main_text = self.create_product_text(product)
            chunks.append({
                'id': f"{product.product_id}_main",
                'text': main_text,
                'metadata': {
                    'product_id': product.product_id,
                    'name': product.name,
                    'price': product.price,
                    'category': product.category,
                    'stock_status': product.stock_status,
                    'chunk_type': 'main'
                }
            })
            
            # Price-focused chunk
            price_text = f"{product.name} costs ${product.price:.2f}. {product.category} product. Stock status: {product.stock_status.replace('_', ' ').title()}."
            chunks.append({
                'id': f"{product.product_id}_price",
                'text': price_text,
                'metadata': {
                    'product_id': product.product_id,
                    'name': product.name,
                    'price': product.price,
                    'category': product.category,
                    'stock_status': product.stock_status,
                    'chunk_type': 'price'
                }
            })
            
            # Description-focused chunk
            desc_text = f"{product.name}: {product.description}"
            if product.specifications:
                desc_text += f" Technical specifications: {product.specifications}"
            
            chunks.append({
                'id': f"{product.product_id}_desc",
                'text': desc_text,
                'metadata': {
                    'product_id': product.product_id,
                    'name': product.name,
                    'price': product.price,
                    'category': product.category,
                    'stock_status': product.stock_status,
                    'chunk_type': 'description'
                }
            })
        
        logger.info(f"Created {len(chunks)} product chunks")
        return chunks
    
    def initialize_vector_store(self, products_file: str, force_rebuild: bool = False) -> None:
        """
        Initialize vector store with product embeddings
        
        Args:
            products_file: Path to products JSON file
            force_rebuild: Whether to rebuild even if data exists
        """
        try:
            # Check if collection already has data
            existing_count = self.collection.count()
            if existing_count > 0 and not force_rebuild:
                logger.info(f"Vector store already contains {existing_count} embeddings. Use force_rebuild=True to rebuild.")
                return
            
            # Clear existing data if rebuilding
            if existing_count > 0 and force_rebuild:
                logger.info("Clearing existing vector store data...")
                # Delete and recreate collection
                self.client.delete_collection(self.collection_name)
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Product embeddings for e-commerce RAG"}
                )
            
            # Load products
            logger.info("Loading products...")
            products = self.load_products(products_file)
            
            if not products:
                logger.error("No valid products found")
                return
            
            # Create chunks
            logger.info("Creating product chunks...")
            chunks = self.chunk_products(products)
            
            # Generate embeddings in batches
            batch_size = 100  # OpenAI API limit
            logger.info("Generating embeddings...")
            
            for i in range(0, len(chunks), batch_size):
                batch_chunks = chunks[i:i + batch_size]
                batch_texts = [chunk['text'] for chunk in batch_chunks]
                
                # Generate embeddings for batch
                embeddings = self.generate_embeddings(batch_texts)
                
                # Prepare data for ChromaDB
                ids = [chunk['id'] for chunk in batch_chunks]
                documents = [chunk['text'] for chunk in batch_chunks]
                metadatas = [chunk['metadata'] for chunk in batch_chunks]
                
                # Add to collection
                self.collection.add(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                
                logger.info(f"Added batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
            
            final_count = self.collection.count()
            logger.info(f"Vector store initialized successfully with {final_count} embeddings")
            
        except Exception as e:
            logger.error(f"Error initializing vector store: {e}")
            raise
    
    def search_products(self, query: str, n_results: int = 5, category_filter: str = None) -> List[Dict[str, Any]]:
        """
        Search for products using vector similarity
        
        Args:
            query: Search query
            n_results: Number of results to return
            category_filter: Optional category filter
            
        Returns:
            List of search results with metadata
        """
        try:
            # Generate query embedding
            query_embedding = self.generate_embeddings([query])[0]
            
            # Prepare where clause for filtering
            where_clause = None
            if category_filter:
                where_clause = {"category": category_filter}
            
            # Search in collection
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_clause,
                include=['documents', 'metadatas', 'distances']
            )
            
            # Format results
            search_results = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    result = {
                        'document': doc,
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i]
                    }
                    search_results.append(result)
            
            logger.info(f"Found {len(search_results)} results for query: '{query}'")
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return []
    
    def get_product_by_id(self, product_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific product
        
        Args:
            product_id: Product identifier
            
        Returns:
            List of product chunks
        """
        try:
            results = self.collection.get(
                where={"product_id": product_id},
                include=['documents', 'metadatas']
            )
            
            product_chunks = []
            if results['documents']:
                for i, doc in enumerate(results['documents']):
                    chunk = {
                        'document': doc,
                        'metadata': results['metadatas'][i]
                    }
                    product_chunks.append(chunk)
            
            return product_chunks
            
        except Exception as e:
            logger.error(f"Error getting product {product_id}: {e}")
            return []
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get vector store statistics
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            count = self.collection.count()
            
            # Get sample of metadata to analyze categories
            sample_results = self.collection.get(
                limit=min(count, 100),
                include=['metadatas']
            )
            
            categories = set()
            chunk_types = set()
            
            if sample_results['metadatas']:
                for metadata in sample_results['metadatas']:
                    categories.add(metadata.get('category', 'Unknown'))
                    chunk_types.add(metadata.get('chunk_type', 'Unknown'))
            
            return {
                'total_embeddings': count,
                'categories': list(categories),
                'chunk_types': list(chunk_types),
                'embedding_model': self.embedding_model
            }
            
        except Exception as e:
            logger.error(f"Error getting collection stats: {e}")
            return {}


def main():
    """Main function to initialize vector store"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize product vector store")
    parser.add_argument("--products-file", default="data/products.json", 
                       help="Path to products JSON file")
    parser.add_argument("--force-rebuild", action="store_true",
                       help="Force rebuild even if data exists")
    parser.add_argument("--vector-store-dir", default="vector_store",
                       help="Vector store directory")
    
    args = parser.parse_args()
    
    try:
        # Initialize vector store manager
        vs_manager = VectorStoreManager(persist_directory=args.vector_store_dir)
        
        # Initialize vector store
        vs_manager.initialize_vector_store(
            products_file=args.products_file,
            force_rebuild=args.force_rebuild
        )
        
        # Show statistics
        stats = vs_manager.get_collection_stats()
        print("\nVector Store Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # Test search
        print("\nTesting search functionality:")
        test_queries = ["iPhone price", "gaming laptop", "wireless headphones"]
        
        for query in test_queries:
            results = vs_manager.search_products(query, n_results=3)
            print(f"\nQuery: '{query}'")
            for i, result in enumerate(results[:2], 1):
                metadata = result['metadata']
                print(f"  {i}. {metadata['name']} - ${metadata['price']:.2f} ({metadata['category']})")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise


if __name__ == "__main__":
    main()
