"""Streaming synthetic datasets on pinned author40 schema; no SQL execution."""
from pathlib import Path
from decimal import Decimal
import argparse,hashlib,importlib.util,json,re,datetime
MODEL='539d45f095e707c9ce69811453ea991bafa39127aa2943aebbadd6bced160d50'
RECEIPT='19a7608b0ee4d001e78c0b1abad67b6cf3ec6e14ab34ebfbc78e597cfb4d22d6'
SCHEMA='5fb9355cc6d9b2842d629c9409dd5f1f94ab12b2eecbcdf5acc30fcaa1192901'
VIEWS='d98cc3aaca4768f3abd7d0a088723d1c3f9138c5221bc98e646aaa6fef677468'
SEED='438fa31d84ee2ef843d539d31af2a3eb4cf37f7e5dabf7e8194586bdfe745914'
INT32=2147483647;SIZES=(10000,100000,1000000)
def need(ok,code):
 if not ok:raise ValueError(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def ident(n):need(bool(re.fullmatch('[A-Z][A-Z0-9_]{0,63}',n)),'IDENTIFIER');return '`'+n+'`'
def strict(s):return json.loads(s,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
def pairs(items):
 d={}
 for k,v in items:need(k not in d,'DUPLICATE_JSON_KEY');d[k]=v
 return d
def cpf(i):
 need(isinstance(i,int) and 0<=i<=1000000,'CPF_RANGE');digits=list(map(int,str(900000000+i)))
 for n in (9,10):
  rem=sum(v*(n+1-j) for j,v in enumerate(digits))%11;digits.append(0 if rem<2 else 11-rem)
 return ''.join(map(str,digits))
def cpf_valid(s):
 if not re.fullmatch('[0-9]{11}',s) or len(set(s))==1:return False
 d=list(map(int,s));return all(d[n]==(0 if (r:=sum(v*(n+1-j) for j,v in enumerate(d[:n]))%11)<2 else 11-r) for n in (9,10))
def inputs(model,receipt,schema,views):
 for p,h in ((model,MODEL),(receipt,RECEIPT),(schema,SCHEMA),(views,VIEWS)):need(sha(Path(p).read_bytes())==h,'AUTHOR_INPUT_PIN')
 r=strict(Path(receipt).read_text());need(len(r['tables'])==40 and sum(len(t['columns']) for t in r['tables'].values())==451,'AUTHOR_SCOPE');need(sum(len(t['foreign_keys']) for t in r['tables'].values())==58,'AUTHOR_FKS')
 seed=Path(__file__).resolve().parent.parent/'unified-mysql-schema/generate_sale_seed_ui_codes_v2.py';need(sha(seed.read_bytes())==SEED,'UI_SEED_SOURCE_PIN');spec=importlib.util.spec_from_file_location('accepted_ui_seed',seed);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 _,_,rows,order=m.plan(r,'0'*32)
 return r,rows,order
class Dataset:
 def __init__(self,receipt,base,order,size,run,seed,workers=32,maximum_attempts=1000000):
  need(isinstance(size,int) and 1<=size<=1000000,'SIZE_BOUND');need(re.fullmatch('[a-f0-9]{32}',run) is not None,'RUN');need(isinstance(seed,int) and 0<=seed<=2147483647,'SEED');need(isinstance(workers,int) and 1<=workers<=64 and isinstance(maximum_attempts,int) and maximum_attempts>0,'WORKER_BUDGET')
  need(5*size+6*workers*maximum_attempts<INT32,'SIGNED_ID_HEADROOM')
  self.r,self.base,self.order,self.size,self.run,self.seed=receipt,base,order,size,run,seed
  self.workers,self.maximum_attempts=workers,maximum_attempts
  self.tag='SYNTHETIC '+run[:8].upper()+' '+str(seed)
  self.counts={t:len(base.get(t,[])) for t in receipt['tables']}
  for t in ('PESSOA','PESSOA_FISICA','PESSOA_ENDERECO'):self.counts[t]=size+1
  for t in ('CLIENTE','VENDA_CABECALHO','VENDA_COMISSAO'):self.counts[t]=size
  self.counts['VENDA_DETALHE']=5*size;self.counts['PRODUTO']=5
 def sparse_rows(self,t):
  base=self.base.get(t,[])
  if t in ('PESSOA','PESSOA_FISICA','PESSOA_ENDERECO'):
   master=dict(base[0]);
   if t=='PESSOA_FISICA':master['CPF']=cpf(0)
   yield master
   for i in range(1,self.size+1):
    row=dict(base[0]);row['ID']=i+1
    if t=='PESSOA':row.update(NOME=self.tag+' CUSTOMER '+str(i),COLABORADOR='N',TRANSPORTADORA='N')
    else:
     row['ID_PESSOA']=i+1
     if t=='PESSOA_FISICA':row['CPF']=cpf(i)
    yield row
  elif t=='CLIENTE':
   for i in range(1,self.size+1):yield {**base[0],'ID':i,'ID_PESSOA':i+1,'OBSERVACAO':self.tag+' CUSTOMER '+str(i)}
  elif t=='VENDA_CABECALHO':
   for i in range(1,self.size+1):yield {**base[0],'ID':i,'ID_CLIENTE':i,'OBSERVACAO':self.tag+' SALE '+str(i)}
  elif t=='VENDA_COMISSAO':
   for i in range(1,self.size+1):yield {**base[0],'ID':i,'ID_VENDA_CABECALHO':i}
  elif t=='VENDA_DETALHE':
   for i in range(1,self.size+1):
    for j in range(1,6):yield {**base[j-1],'ID':5*(i-1)+j,'ID_VENDA_CABECALHO':i,'ID_PRODUTO':j}
  elif t=='PRODUTO':
   for i in range(1,6):yield {**base[0],'ID':i,'NOME':self.tag+' PRODUCT '+str(i)}
  else:yield from base
 def rows(self,t):
  for sparse in self.sparse_rows(t):
   row={c['ColName']:sparse.get(c['ColName']) for c in self.r['tables'][t]['columns']};self.validate_row(t,row);yield row
 def validate_row(self,t,row):
  table=self.r['tables'][t];need(set(row)=={c['ColName'] for c in table['columns']},'FULL_COLUMN_SET')
  for c in table['columns']:
   v=row[c['ColName']];kind=c['model_type']
   if v is None:need(c['NotNull']!='1','NONNULL');continue
   if kind=='INTEGER':need(type(v) is int and 0<=v<=INT32,'INTEGER_TYPE_RANGE')
   elif kind=='DECIMAL':
    need(type(v) is int or isinstance(v,Decimal),'DECIMAL_TYPE');precision,scale=map(int,c['DatatypeParams'].strip('()').split(','));need(Decimal(v).is_finite() and abs(Decimal(v))<Decimal(10)**(precision-scale) and Decimal(v)==Decimal(v).quantize(Decimal(10)**-scale),'DECIMAL_RANGE_SCALE')
   elif kind=='DATE':need(type(v) is str and datetime.date.fromisoformat(v).isoformat()==v,'DATE_TYPE')
   else:
    need(type(v) is str,'STRING_TYPE');width=65535 if kind=='TEXT' else int(c['DatatypeParams'].strip('()'));need(len(v.encode('utf8'))<=width and re.fullmatch('[A-Z0-9 ]*',v) is not None,'STRING_WIDTH_DOMAIN')
  need(1<=row['ID']<=self.counts[t],'SETUP_ID_SCOPE')
  for fk in table['foreign_keys']:
   for parent,child in fk['fields'].items():
    v=row[child]
    if v is not None:need(parent=='ID' and type(v) is int and 1<=v<=self.counts[fk['parent']],'FOREIGN_REF')
  if t=='CLIENTE':need((row['TIPO_FRETE'],row['INDICADOR_PRECO'],row['FORMA_DESCONTO'])==('S','P','F'),'CUSTOMER_UI')
  if t=='PESSOA_FISICA':need(cpf_valid(row['CPF']),'CPF_CHECKSUM')
  if t=='VENDA_CABECALHO':need((row['TIPO_FRETE'],row['FORMA_PAGAMENTO'],row['SITUACAO'])==('C','0','D') and row['VALOR_TOTAL']==150 and row['VALOR_COMISSAO']==15,'SALE_UI_TOTAL')
  if t=='VENDA_COMISSAO':need((row['TIPO_CONTABIL'],row['SITUACAO'],row['VALOR_VENDA'],row['VALOR_COMISSAO'])==('C','A',150,15),'COMMISSION_DOMAIN_TOTAL')
  if t=='VENDA_DETALHE':need(1<=row['QUANTIDADE']<=5 and row['VALOR_TOTAL']==10*row['QUANTIDADE'] and row['VALOR_COMISSAO']==row['QUANTIDADE'],'DETAIL_TOTAL')
 def canonical(self,t,row):
  values=[]
  for c in self.r['tables'][t]['columns']:
   v=row[c['ColName']]
   if v is not None:
    if c['model_type']=='DECIMAL':v=format(Decimal(v),'.'+c['DatatypeParams'].strip('()').split(',')[1]+'f')
    else:v=str(v)
   values.append(v)
  return (json.dumps(values,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8')
 def value_sql(self,v):
  if v is None:return 'NULL'
  if type(v) is int or isinstance(v,Decimal):return str(v)
  need("'" not in v and '\\' not in v and '\n' not in v,'SQL_LITERAL');return "'"+v+"'"
 def generate(self,out,batch=1000):
  out=Path(out);need(not out.exists(),'FRESH_OUTPUT');need(1<=batch<=10000,'BATCH_BOUND');out.mkdir(parents=True);hashes={};nexts={};written={}
  with (out/'dataset.sql').open('wb') as f:
   for t in self.order:
    h=hashlib.sha256();count=0;columns=self.r['tables'][t]['columns'];prefix='INSERT INTO '+ident(t)+' ('+','.join(ident(c['ColName']) for c in columns)+') VALUES ('
    for row in self.rows(t):
     if count%batch==0:f.write(b'START TRANSACTION;\n')
     f.write((prefix+','.join(self.value_sql(row[c['ColName']]) for c in columns)+');\n').encode('utf8'));h.update(self.canonical(t,row));count+=1
     if count%batch==0:f.write(b'COMMIT;\n')
    if count%batch:f.write(b'COMMIT;\n')
    written[t]=count;hashes[t]=h.hexdigest();nexts[t]=count+1
   for t in self.r['tables']:
    if t not in written:written[t]=0;hashes[t]=sha(b'');nexts[t]=1
    need(written[t]==self.counts[t],'STREAM_COUNT');f.write(('ALTER TABLE '+ident(t)+' AUTO_INCREMENT='+str(nexts[t])+';\n').encode())
  verification=verify_sql(self.r);(out/'verification.sql').write_text(verification)
  manifest={'schema_version':1,'classification':'ACTUAL_GENERATED_STREAM_NOT_IMPORTED','native_execution':'NOT_EXECUTED','run_id':self.run,'dataset_seed':self.seed,'population_customers':self.size,'population_sales':self.size,'population_details':5*self.size,'population_commissions':self.size,'model_sha256':MODEL,'export_receipt_sha256':RECEIPT,'schema_sha256':SCHEMA,'views_sha256':VIEWS,'generator_sha256':sha(Path(__file__).read_bytes()),'accepted_ui_seed_source_sha256':SEED,'table_columns':{t:[c['ColName'] for c in tab['columns']] for t,tab in self.r['tables'].items()},'expected_table_rows':written,'expected_canonical_content_sha256':hashes,'expected_auto_increment_next':nexts,'dataset_sql_sha256':file_sha(out/'dataset.sql'),'verification_sql_sha256':sha(verification.encode()),'setup_ids':'Explicit deterministic per-table IDs only; business IDs must be generated, above actual independently verified maxima. Never infer runtime IDs.','signed_id_budget':{'workers':self.workers,'maximum_attempts_per_worker':self.maximum_attempts,'detail_ids_maximum':5*self.size+6*self.workers*self.maximum_attempts,'required_upper_bound':INT32},'person_policy':'Distinct PESSOA/PESSOA_FISICA/address per customer plus shared reference person1; CPF algorithmically generated, checksum-valid, no PII source and no assertion about real registration/nonexistence. Never contact real people.','reference_policy':'Five shared products and master seller/payment/transporter/invoice refs; no separate contention classification. Original controller stock/accounting/commission side effects not executed: dataset fixture representation only.','nullable_policy':'Every original column explicit; unassigned nullable values SQLNULL, no schema defaults exist in pinned model. DECIMAL canonical strings retain declared scale; originalVO nullable loss remains disclosed.','import_requirements':['fresh t2ti_dataset_<run> database on unchanged author40schema/views','FK/check constraints ON, strict SQL mode/utf8mb4/InnoDB and no concurrent actors','import must stop on first error; partial batches are not qualified, discard own fresh database on failure','independent fresh SELECT snapshot verification and actual reseed/key/FK/domain/content checks before any benchmark']}
  (out/'dataset-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest

def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def schema_records(r):
 records={'COLUMN':{},'INDEX':{},'RELATION':{}}
 for t,tab in r['tables'].items():
  records['COLUMN'][t]=[];records['INDEX'][t]=[];records['RELATION'][t]=[]
  for c in tab['columns']:
   kind=c['model_type'];typ=('int' if kind=='INTEGER' else kind.lower())+('' if kind in ('INTEGER','DATE','TEXT') else c['DatatypeParams'])
   if ' UNSIGNED' in c['sql']:typ+=' unsigned'
   records['COLUMN'][t].append([c['ColName'],typ,'NO' if c['NotNull']=='1' else 'YES',None,'auto_increment' if c['AutoInc']=='1' else ''])
  for idx in tab['indexes']:
   need(idx['kind'] in ('0','1'),'INDEX_KIND')
   for pos,col in enumerate(idx['columns'],1):records['INDEX'][t].append([idx['name'],0 if idx['kind']=='0' else 1,pos,col['name'],None if col['prefix_length']==0 else col['prefix_length']])
  for fk in tab['foreign_keys']:
   need(len(fk['fields'])==1 and fk['sql'].endswith('ON DELETE NO ACTION ON UPDATE NO ACTION'),'FK_ACTION_SCOPE')
   for parent,child in fk['fields'].items():records['RELATION'][t].append([child,fk['parent'],parent,'NO ACTION','NO ACTION'])
 return records
def verify_sql(r):
 q=['SET TRANSACTION READ ONLY;','START TRANSACTION WITH CONSISTENT SNAPSHOT;',"SELECT CONCAT('TRIGGERS',CHAR(9),'ALL',CHAR(9),COUNT(*)) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE();"]
 q.append("SELECT CONCAT('SCOPE',CHAR(9),TABLE_TYPE,CHAR(9),UPPER(TABLE_NAME)) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_TYPE,TABLE_NAME;")
 q.append("SELECT CONCAT('VIEW',CHAR(9),UPPER(TABLE_NAME),CHAR(9),JSON_ARRAY(VIEW_DEFINITION,CHECK_OPTION,IS_UPDATABLE)) FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME;")
 for t,tab in sorted(r['tables'].items()):
  values=','.join('CAST('+ident(c['ColName'])+' AS CHAR)' for c in tab['columns'])
  q.append("SELECT CONCAT('ROW',CHAR(9),'"+t+"',CHAR(9),JSON_ARRAY("+values+")) FROM "+ident(t)+' ORDER BY `ID`;')
  q.append("SELECT CONCAT('META',CHAR(9),'"+t+"',CHAR(9),COUNT(*),CHAR(9),COALESCE(MAX(`ID`),0)) FROM "+ident(t)+';')
  q.append("SELECT CONCAT('NEXT',CHAR(9),'"+t+"',CHAR(9),AUTO_INCREMENT) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+t+"';")
  q.append("SELECT CONCAT('COLUMN',CHAR(9),'"+t+"',CHAR(9),JSON_ARRAY(COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA)) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+t+"' ORDER BY ORDINAL_POSITION;")
  q.append("SELECT CONCAT('INDEX',CHAR(9),'"+t+"',CHAR(9),JSON_ARRAY(INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART)) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+t+"' ORDER BY INDEX_NAME,SEQ_IN_INDEX;")
  q.append("SELECT CONCAT('RELATION',CHAR(9),'"+t+"',CHAR(9),JSON_ARRAY(k.COLUMN_NAME,UPPER(k.REFERENCED_TABLE_NAME),k.REFERENCED_COLUMN_NAME,IF(r.DELETE_RULE='RESTRICT','NO ACTION',r.DELETE_RULE),IF(r.UPDATE_RULE='RESTRICT','NO ACTION',r.UPDATE_RULE))) FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME='"+t+"' AND k.REFERENCED_TABLE_NAME IS NOT NULL ORDER BY k.COLUMN_NAME;")
  q.append("SELECT CONCAT('ENGINE',CHAR(9),'"+t+"',CHAR(9),ENGINE) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+t+"';")
  for fk in tab['foreign_keys']:
   join=' AND '.join('c.'+ident(child)+'=p.'+ident(parent) for parent,child in fk['fields'].items());nonnull=' AND '.join('c.'+ident(child)+' IS NOT NULL' for child in fk['fields'].values());parent=next(iter(fk['fields']))
   q.append("SELECT CONCAT('FK',CHAR(9),'"+t+'.'+fk['name']+"',CHAR(9),COUNT(*)) FROM "+ident(t)+' c LEFT JOIN '+ident(fk['parent'])+' p ON '+join+' WHERE '+nonnull+' AND p.'+ident(parent)+' IS NULL;')
 q.append('COMMIT;');return '\n'.join(q)+'\n'
def verify_capture(manifest,receipt,stream):
 need(manifest['export_receipt_sha256']==RECEIPT,'MANIFEST_MODEL');hashes={t:hashlib.sha256() for t in receipt['tables']};counts={t:0 for t in hashes};last={t:0 for t in hashes};meta={};nexts={};fks={};engines={};triggers=None;scope={'BASE TABLE':set(),'VIEW':set()};view_fingerprints={};expected_schema=schema_records(receipt);observed_schema={k:{t:[] for t in hashes} for k in expected_schema};expected_fks={t+'.'+fk['name'] for t,tab in receipt['tables'].items() for fk in tab['foreign_keys']}
 for line in stream:
  fields=line.rstrip('\r\n').split('\t');need(len(fields)>=3,'CAPTURE_FORMAT');kind,t=fields[:2]
  if kind=='SCOPE':need(len(fields)==3 and t in scope and fields[2] not in scope[t],'SCOPE_DUP');scope[t].add(fields[2])
  elif kind=='VIEW':need(len(fields)==3 and t not in view_fingerprints,'VIEW_DUP');v=strict(fields[2]);need(type(v) is list and len(v)==3 and all(type(x) is str for x in v),'VIEW_METADATA');view_fingerprints[t]=sha(json.dumps(v,separators=(',',':')).encode())
  elif kind in observed_schema:
   need(len(fields)==3 and t in hashes,'SCHEMA_ROW');observed_schema[kind][t].append(strict(fields[2]))
  elif kind=='ENGINE':need(len(fields)==3 and t in hashes and t not in engines,'ENGINE_DUP');engines[t]=fields[2]
  elif kind=='TRIGGERS':need(len(fields)==3 and t=='ALL' and triggers is None,'TRIGGER_DUP');triggers=int(fields[2])
  elif kind=='ROW':
   need(len(fields)==3 and t in hashes,'ROW_SCOPE');v=strict(fields[2]);need(type(v) is list and len(v)==len(receipt['tables'][t]['columns']) and all(x is None or type(x) is str for x in v),'ROW_VALUES');cols=manifest['table_columns'][t];i=int(v[cols.index('ID')]);need(last[t]<i<=INT32,'ID_KEY_ORDER');last[t]=i;counts[t]+=1;hashes[t].update((json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n').encode())
  elif kind=='META':need(len(fields)==4 and t in hashes and t not in meta,'META_DUP');meta[t]=(int(fields[2]),int(fields[3]))
  elif kind=='NEXT':need(len(fields)==3 and t in hashes and t not in nexts,'NEXT_DUP');nexts[t]=int(fields[2])
  elif kind=='FK':need(len(fields)==3 and t in expected_fks and t not in fks,'FK_DUP');fks[t]=int(fields[2])
  else:raise ValueError('UNEXPECTED_CAPTURE_RECORD')
 need(scope['BASE TABLE']==set(hashes) and scope['VIEW']=={v['name'] for v in receipt['views']} and set(view_fingerprints)==scope['VIEW'],'TABLE_VIEW_SCOPE')
 need(set(engines)==set(hashes) and all(v=='InnoDB' for v in engines.values()) and triggers==0,'ENGINE_OR_TRIGGER')
 for k in expected_schema:
  for t,values in expected_schema[k].items():
   observed=observed_schema[k][t]
   if k=='COLUMN':need(observed==values,'COLUMN_SCHEMA')
   else:need(sorted(observed,key=lambda v:json.dumps(v))==sorted(values,key=lambda v:json.dumps(v)),'INDEX_OR_FK_SCHEMA')
 need(set(meta)==set(nexts)==set(hashes) and set(fks)==expected_fks,'CAPTURE_INCOMPLETE');need(all(x==0 for x in fks.values()),'FK_ORPHANS')
 for t,h in hashes.items():need(counts[t]==manifest['expected_table_rows'][t] and meta[t]==(counts[t],last[t]) and h.hexdigest()==manifest['expected_canonical_content_sha256'][t] and nexts[t]==manifest['expected_auto_increment_next'][t],'TABLE_CONTENT_OR_RESEED')
 return {'status':'CAPTURE_MATCHED_SOURCE_MANIFEST_PENDING_NATIVE_PROVENANCE','tables':40,'foreign_keys':len(fks),'rows':sum(counts.values()),'native_view_metadata_sha256':view_fingerprints,'view_definition_equivalence':'PENDING_INDEPENDENT_NATIVE_AUTHOR_SQL_REVIEW_BEFORE_ADMISSION','provenance':'Caller must independently prove fresh SELECT process/identity/source/credentials/snapshot schema and absence of concurrent actors; a supplied capture alone cannot establish actual native PASS.'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',required=True);p.add_argument('--export-receipt',required=True);p.add_argument('--schema',required=True);p.add_argument('--views',required=True);p.add_argument('--size',type=int,choices=SIZES,required=True);p.add_argument('--run-id',required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--workers',type=int,default=32);p.add_argument('--maximum-attempts',type=int,default=1000000);p.add_argument('--out',required=True);a=p.parse_args();r,b,o=inputs(a.model,a.export_receipt,a.schema,a.views);m=Dataset(r,b,o,a.size,a.run_id,a.seed,a.workers,a.maximum_attempts).generate(a.out);print(json.dumps({'native_execution':'NOT_EXECUTED','dataset_sql_sha256':m['dataset_sql_sha256'],'customers':m['population_customers']}))
