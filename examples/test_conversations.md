# Test Conversation Scenarios

This document contains manual test scenarios to validate the chatbot's functionality across different use cases.

## Scenario 1: Product Price Query

**Objective**: Test RAG Agent's ability to retrieve accurate product information

**Conversation Flow**:
```
User: What's the price of the iPhone 15 Pro?

Expected Bot Response:
- Calls search_products("iPhone 15 Pro")
- Returns: "I found 1 product for 'iPhone 15 Pro':

1. **iPhone 15 Pro** - $999.99 ✅
   Category: Smartphones | Stock: In Stock

Would you like more details about this product, or are you interested in purchasing one?"
```

**Validation Criteria**:
- ✅ Bot uses search_products function
- ✅ Returns accurate price ($999.99)
- ✅ Shows stock status
- ✅ Asks follow-up question

---

## Scenario 2: Multi-turn Product Discussion

**Objective**: Test conversation context maintenance and progressive refinement

**Conversation Flow**:
```
User: Do you have laptops?

Expected Bot Response:
- Shows multiple laptop options with prices and categories

User: Which ones are good for gaming?

Expected Bot Response:
- Filters to gaming laptops (ASUS ROG Zephyrus G14, etc.)
- Highlights gaming-specific features
- Maintains conversation context
```

**Validation Criteria**:
- ✅ Bot maintains context between turns
- ✅ Provides relevant filtering
- ✅ Shows appropriate products for gaming

---

## Scenario 3: Order Confirmation with Extraction

**Objective**: Test autonomous handoff from RAG Agent to Order Agent

**Conversation Flow**:
```
User: Tell me about the MacBook Pro 14-inch

Bot: [Provides MacBook Pro information including $1599.99 price]

User: I'll take it

Expected Bot Response:
- Detects order intent
- Calls create_order function with extracted details:
  - product_id: "LAPTOP-001"
  - product_name: "MacBook Pro 14-inch M3"
  - quantity: 1
  - unit_price: 1599.99
- Returns: "Perfect! Let me process your order for the MacBook Pro 14-inch M3...
  Your order has been confirmed! Order ID: #ORD-20231215143022-A1B2C3D4. 
  Total: $1599.99. Thank you!"
```

**Validation Criteria**:
- ✅ Detects order intent from "I'll take it"
- ✅ Extracts correct product details from conversation
- ✅ Creates order in database
- ✅ Provides order confirmation with ID

---

## Scenario 4: Ambiguous Query Handling

**Objective**: Test bot's ability to handle unclear requests

**Conversation Flow**:
```
User: I want one

Expected Bot Response:
- "I'd be happy to help you place an order! However, I need to know which product you'd like to purchase. Could you please specify which item you're interested in?"

User: The laptop we discussed

Expected Bot Response:
- If no laptop was previously discussed: "I don't see any laptop that we've discussed in our conversation. Could you please tell me which specific laptop you're interested in?"
- If laptop was discussed: Proceeds with that laptop
```

**Validation Criteria**:
- ✅ Bot asks for clarification instead of guessing
- ✅ References conversation context appropriately
- ✅ Guides user to provide necessary information

---

## Scenario 5: Invalid Order Rejection

**Objective**: Test order validation and error handling

**Conversation Flow**:
```
User: I want 150 iPhones

Expected Bot Response:
- "I'm sorry, but our system can only process orders up to 100 units per item. Would you like to order 100 iPhones, or would you prefer a different quantity?"

User: I want to buy the out-of-stock PlayStation

Expected Bot Response:
- "I apologize, but the PlayStation 5 is currently out of stock. Would you like me to show you other gaming consoles that are available, or would you prefer to be notified when it's back in stock?"
```

**Validation Criteria**:
- ✅ Validates quantity limits (max 100 per item)
- ✅ Checks stock status before order creation
- ✅ Provides helpful alternatives
- ✅ Maintains conversational tone

---

## Scenario 6: Customer Information Collection

**Objective**: Test optional customer information handling

**Conversation Flow**:
```
User: What's the price of AirPods Pro?

Bot: [Shows AirPods Pro at $249.99]

User: I'll buy them. My name is Sarah Johnson and my email is sarah@email.com

Expected Bot Response:
- Calls create_order with:
  - products: AirPods Pro details
  - customer_name: "Sarah Johnson"
  - customer_email: "sarah@email.com"
- "Thank you, Sarah! Your order for AirPods Pro 2nd Generation has been confirmed! 
  Order ID: #ORD-... Total: $249.99. 
  A confirmation will be sent to sarah@email.com."
```

**Validation Criteria**:
- ✅ Extracts customer information from natural language
- ✅ Stores customer info in order
- ✅ Personalizes response with customer name
- ✅ References provided email

---

## Scenario 7: Category-based Search

**Objective**: Test category filtering and search functionality

**Conversation Flow**:
```
User: Show me audio products under $200

Expected Bot Response:
- Calls search_products with category filter for "Audio"
- Shows products like:
  - JBL Charge 5 - $149.99
  - Bose QuietComfort 45 - $329.99 (over budget, but relevant)
- "I found several audio products. Here are the ones under $200: [list]
  Would you like to see more details about any of these?"
```

**Validation Criteria**:
- ✅ Filters by category correctly
- ✅ Considers price constraints
- ✅ Shows relevant products
- ✅ Offers additional assistance

---

## Scenario 8: Complex Multi-item Order

**Objective**: Test handling of multiple items in single order

**Conversation Flow**:
```
User: I want to buy an iPhone 15 Pro and AirPods Pro

Expected Bot Response:
- Calls create_order with multiple items:
  - iPhone 15 Pro: $999.99
  - AirPods Pro: $249.99
- "Perfect! I'll process your order for both items:
  - iPhone 15 Pro: $999.99
  - AirPods Pro 2nd Generation: $249.99
  
  Order Total: $1,249.98
  Order ID: #ORD-...
  Thank you for your purchase!"
```

**Validation Criteria**:
- ✅ Handles multiple products in single order
- ✅ Calculates total correctly
- ✅ Shows itemized breakdown
- ✅ Creates single order with multiple items

---

## Running Manual Tests

To run these test scenarios manually:

1. **Setup Environment**:
   ```bash
   cd /Users/king/product_ai_project
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Initialize Vector Store**:
   ```bash
   export OPENAI_API_KEY=your-api-key
   python -m src.initialize_vector_store --products-file data/products.json
   ```

3. **Run Interactive Chatbot**:
   ```bash
   python -m src.chatbot --interactive
   ```

4. **Test Each Scenario**:
   - Copy the user inputs from each scenario
   - Verify the bot responses match expected outcomes
   - Check that orders are created in the database
   - Validate function calls are made appropriately

## Expected Success Metrics

- **RAG Agent**: 95%+ accuracy in product information retrieval
- **Order Agent**: 100% success rate in order creation when valid
- **Function Calling**: Autonomous selection of correct tools
- **Context Maintenance**: Conversation context preserved across turns
- **Error Handling**: Graceful handling of invalid requests
- **Data Validation**: All orders pass Pydantic validation
