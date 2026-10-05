"""Verify root-captured SELECT stream against immutable generated manifest; no DB/API."""
from pathlib import Path
import argparse,json
from generate_dataset import strict,sha,need,inputs,verify_capture,MODEL,RECEIPT,SCHEMA,VIEWS,SIZES,file_sha

def verify(manifest_path,manifest_sha,model,receipt,schema,views,capture_path):
 raw=Path(manifest_path).read_bytes();need(sha(raw)==manifest_sha,'MANIFEST_PIN');m=strict(raw);r,_,_=inputs(model,receipt,schema,views)
 need(m['schema_version']==1 and m['model_sha256']==MODEL and m['export_receipt_sha256']==RECEIPT and m['schema_sha256']==SCHEMA and m['views_sha256']==VIEWS,'MANIFEST_INPUTS')
 need(m['generator_sha256']==sha(Path(__file__).with_name('generate_dataset.py').read_bytes()),'GENERATOR_PIN');need(m['population_customers'] in SIZES and m['population_sales']==m['population_customers'] and m['population_details']==5*m['population_customers'] and m['population_commissions']==m['population_customers'],'DATASET_PROFILE')
 need(m['table_columns']=={t:[c['ColName'] for c in tab['columns']] for t,tab in r['tables'].items()},'AUTHOR_COLUMNS')
 with Path(capture_path).open(encoding='utf8') as f:result=verify_capture(m,r,f)
 result['manifest_sha256']=manifest_sha;result['capture_sha256']=file_sha(capture_path);return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('manifest','manifest-sha256','model','export-receipt','schema','views','capture','out'):p.add_argument('--'+n,required=True)
 a=p.parse_args();result=verify(a.manifest,a.manifest_sha256,a.model,a.export_receipt,a.schema,a.views,a.capture);out=Path(a.out);need(not out.exists(),'FRESH_OUTPUT');out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'tables':result['tables']}))
