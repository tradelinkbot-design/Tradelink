import os
import traceback

os.environ['HUGGINGFACE_HUB_SYMLINKS_MODE'] = 'copy'
os.environ['HF_HOME'] = os.path.join(os.path.expanduser('~'), '.hf_cache')

print('Copying model files (this may take 2-5 minutes for 420MB)...')

try:
    print('Step 1: importing SentenceTransformer...')
    from sentence_transformers import SentenceTransformer
    print('Step 2: loading model...')
    model = SentenceTransformer('all-mpnet-base-v2')
    print('Step 3: testing encode...')
    test = model.encode('test sentence')
    print(f'Done — embedding dim: {len(test)}')
    print('Model is ready. You can delete this file now.')
except Exception as e:
    print(f'FAILED at: {e}')
    traceback.print_exc()

input('Press Enter to close...')