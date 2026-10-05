"""Add customer ID ranges to the pinned fixture; preserve original ERP DDL."""
from pathlib import Path
import sys,json,hashlib,argparse
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'unified-mysql-datasets'))
from generate_dataset import Dataset,inputs,need,file_sha
class CustomerPartition(Dataset):
 def __init__(self,*args,shard_index,**kwargs):
  super().__init__(*args,**kwargs);need(0<=shard_index<4,'SHARD_INDEX');self.shard_index=shard_index;self.customer_offset=shard_index*self.size
 def sparse_rows(self,table):
  for row in super().sparse_rows(table):
   row=dict(row)
   if table=='CLIENTE':row['ID']+=self.customer_offset
   elif table=='VENDA_CABECALHO':row['ID_CLIENTE']+=self.customer_offset
   yield row
 def validate_row(self,table,row):
  local=dict(row)
  if table=='CLIENTE':local['ID']-=self.customer_offset
  elif table=='VENDA_CABECALHO':local['ID_CLIENTE']-=self.customer_offset
  super().validate_row(table,local)
  if table=='CLIENTE':need(self.customer_offset<row['ID']<=self.customer_offset+self.size,'CUSTOMER_PARTITION')
  if table=='VENDA_CABECALHO':need(self.customer_offset<row['ID_CLIENTE']<=self.customer_offset+self.size,'ORDER_CUSTOMER_PARTITION')
 def generate(self,out,batch=1000):
  m=super().generate(out,batch);out=Path(out);next_id=self.customer_offset+self.size+1
  with (out/'dataset.sql').open('a') as f:f.write('ALTER TABLE `CLIENTE` AUTO_INCREMENT='+str(next_id)+';\n')
  m['expected_auto_increment_next']['CLIENTE']=next_id;m['dataset_sql_sha256']=file_sha(out/'dataset.sql')
  m['partition']={'key':'VENDA_CABECALHO.ID_CLIENTE','index':self.shard_index,'customer_range':[self.customer_offset+1,self.customer_offset+self.size],'local_order_ids':[1,self.size],'global_order_identity':'(customer_id, shard-local order_id)','reference_policy':'Original immutable shared refs copied; customer/person relationships valid locally. Customer records partitioned.'}
  m['partition_generator_sha256']=file_sha(__file__);(out/'dataset-manifest.json').write_text(json.dumps(m,indent=2)+'\n');return m
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--export-receipt',required=True);p.add_argument('--schema',required=True);p.add_argument('--views',required=True);p.add_argument('--size',type=int,default=100000);p.add_argument('--shard-index',type=int,required=True);p.add_argument('--run-id',required=True);p.add_argument('--seed',type=int,default=17);p.add_argument('--out',required=True);a=p.parse_args();r,b,o=inputs(a.model,a.export_receipt,a.schema,a.views);m=CustomerPartition(r,b,o,a.size,a.run_id,a.seed,8,100000,shard_index=a.shard_index).generate(a.out);print(json.dumps(m['partition']))
