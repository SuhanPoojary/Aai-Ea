"""Normalize the downloaded Bitext customer-support CSV for evaluation.
Usage: python scripts/normalize_bitext.py path/to/bitext.csv
Output: data/processed/customer_support_intents.csv
"""
import sys
from pathlib import Path
import pandas as pd
if len(sys.argv)<2:
    raise SystemExit('Usage: python scripts/normalize_bitext.py <path-to-downloaded-csv>')
src=Path(sys.argv[1])
df=pd.read_csv(src)
# Bitext mirrors can use slightly different column names; select by common names.
cols={str(c).strip().lower().replace(' ','_'):c for c in df.columns}
text_col=next((cols[k] for k in ('utterance','text','query','customer_query') if k in cols),None)
intent_col=next((cols[k] for k in ('intent','label') if k in cols),None)
category_col=next((cols[k] for k in ('category','intent_group') if k in cols),None)
if not text_col or not intent_col:
    raise SystemExit(f'Could not detect utterance and intent columns. Found: {list(df.columns)}')
out=pd.DataFrame({'text':df[text_col].astype(str),'intent':df[intent_col].astype(str),'category':df[category_col].astype(str) if category_col else 'unknown'})
out=out.dropna().drop_duplicates(subset=['text']).query("text.str.len() > 2",engine='python')
dest=Path('data/processed/customer_support_intents.csv'); dest.parent.mkdir(parents=True,exist_ok=True); out.to_csv(dest,index=False)
print(f'Wrote {len(out):,} unique examples to {dest}')
print(out['intent'].value_counts().head(15).to_string())
