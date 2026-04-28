"""
Test News Service Integration

This script tests the updated news service with enhanced fallback capabilities.
"""

import asyncio
import logging
import sys
import os
sys.path.append('/Users/prathamraj/Documents/Placement-Prep/10.Projects/stocxi')
from backend.services.news_service import get_news

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def test_news_service():
    """Test the news service with different stocks"""
    test_stocks = [
        ("RELIANCE", "Reliance Industries"),
        ("TCS", "Tata Consultancy Services"),
        ("HDFCBANK", "HDFC Bank"),
        ("INFY", "Infosys"),
        ("SBIN", "State Bank of India")
    ]
    
    for symbol, company_name in test_stocks:
        print(f"\n=== Testing {symbol} ({company_name}) ===")
        
        try:
            articles = await get_news(symbol, company_name)
            
            if articles:
                print(f"✓ Found {len(articles)} articles:")
                for i, article in enumerate(articles[:3], 1):
                    print(f"{i}. Title: {article['title'][:80]}...")
                    print(f"   Source: {article['source_name']}")
                    print(f"   Published: {article['published']}")
                    print(f"   Signal Class: {article['signal_class']}")
                    print(f"   Key Sentence: {article['key_sentence'][:100]}...")
                    if article.get('llm_summary'):
                        print(f"   LLM Summary: {article['llm_summary'][:100]}...")
                    print()
            else:
                print("✗ No articles found")
                
        except Exception as e:
            print(f"✗ Error testing {symbol}: {e}")

if __name__ == "__main__":
    asyncio.run(test_news_service())