"""
Helper: patch compute_product_embedding_task to chain recommendation tasks.
Run once from project root: python patch_embedding_task.py
"""
import re

target = 'marketplace/tasks.py'

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = '    logger.info("compute_product_embedding: saved embedding for %s.", product_id)'
NEW = '''    logger.info("compute_product_embedding: saved embedding for %s.", product_id)

    # Chain: trigger recommendation engines now that embedding exists
    # Engine 1: find similar products (cosine similarity)
    compute_similar_products_task.delay(product_id)
    # Engine 4: compute price intelligence (market comparison)
    compute_price_intelligence_task.delay(product_id)'''

if OLD not in content:
    print('ERROR: target string not found. Check for encoding differences.')
    exit(1)

if 'compute_similar_products_task.delay(product_id)' in content:
    print('SKIP: chain already present.')
    exit(0)

content = content.replace(OLD, NEW, 1)

with open(target, 'w', encoding='utf-8') as f:
    f.write(content)

print('SUCCESS: embedding task chain added.')
