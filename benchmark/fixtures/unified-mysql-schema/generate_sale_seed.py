#!/usr/bin/env python3
"""Minimal deterministic synthetic references on the accepted author schema.

No inferred columns, schema changes, disabled constraints or database execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

MODEL_SHA = '539d45f095e707c9ce69811453ea991bafa39127aa2943aebbadd6bced160d50'
SCHEMA_SHA = '5fb9355cc6d9b2842d629c9409dd5f1f94ab12b2eecbcdf5acc30fcaa1192901'
VIEWS_SHA = 'd98cc3aaca4768f3abd7d0a088723d1c3f9138c5221bc98e646aaa6fef677468'
ROOTS = {'PESSOA', 'ATIVIDADE_FOR_CLI', 'SITUACAO_FOR_CLI', 'TRIBUT_OPERACAO_FISCAL',
         'VENDA_CONDICOES_PAGAMENTO', 'TRANSPORTADORA', 'VENDEDOR', 'PRODUTO',
         'PESSOA_FISICA', 'PESSOA_ENDERECO', 'CLIENTE',
         'VENDA_CABECALHO', 'VENDA_DETALHE', 'VENDA_COMISSAO', 'NOTA_FISCAL_TIPO', 'NOTA_FISCAL_MODELO', 'EMPRESA'}
VALUES = {
    'PESSOA': {'NOME': 'T2TI FUNCTIONAL REFERENCE', 'TIPO': 'F', 'CLIENTE': 'S',
               'COLABORADOR': 'S', 'TRANSPORTADORA': 'S'},
    'VENDEDOR': {'ID_COLABORADOR': 1, 'GERENTE': 'N'},
    'PESSOA_ENDERECO': {'PRINCIPAL': 'S'},
    'PRODUTO': {'NOME': 'FUNCTIONAL PRODUCT', 'DESCRICAO': 'SYNTHETIC FUNCTIONAL REFERENCE',
                'DESCRICAO_PDV': 'FUNCTIONAL PRODUCT', 'VALOR_COMPRA': 10, 'VALOR_VENDA': 10,
                'PRECO_VENDA_MINIMO': 10, 'PRECO_SUGERIDO': 10, 'EXCLUIDO': 'N', 'INATIVO': 'N'},
    'UNIDADE_PRODUTO': {'SIGLA': 'UN', 'DESCRICAO': 'FUNCTIONAL UNIT', 'PODE_FRACIONAR': 'N'},
    'VENDA_CONDICOES_PAGAMENTO': {'NOME': 'FUNCTIONAL CASH', 'DESCRICAO': 'SYNTHETIC CASH TERMS', 'VISTA_PRAZO': 'V'},
    'CLIENTE': {'ID_OPERACAO_FISCAL': 1, 'DESDE': '2026-01-01', 'DATA_CADASTRO': '2026-01-01',
                'OBSERVACAO': 'SYNTHETIC BASELINE CUSTOMER', 'GERA_FINANCEIRO': 'N',
                'INDICADOR_PRECO': 'P', 'FORMA_DESCONTO': 'F', 'TIPO_FRETE': 'S'},
    'EMPRESA': {'RAZAO_SOCIAL': 'SYNTHETIC FUNCTIONAL COMPANY'},
    'NOTA_FISCAL_MODELO': {'MODELO': '55', 'DESCRICAO': 'SYNTHETIC INVOICE MODEL'},
    'NOTA_FISCAL_TIPO': {'NOME': 'SYNTHETIC SALE INVOICE', 'DESCRICAO': 'FUNCTIONAL TYPE', 'SERIE': '001', 'ULTIMO_NUMERO': 1},
    'VENDA_CABECALHO': {'ID_TRANSPORTADORA': 1, 'DATA_VENDA': '2026-01-01',
                'DATA_SAIDA': '2026-01-02', 'TIPO_FRETE': 'S', 'FORMA_PAGAMENTO': 'V',
                'VALOR_SUBTOTAL': 150, 'VALOR_TOTAL': 150, 'TAXA_COMISSAO': 10, 'VALOR_COMISSAO': 15,
                'LOCAL_ENTREGA': 'SYNTHETIC DELIVERY', 'LOCAL_COBRANCA': 'SYNTHETIC COLLECTION',
                'OBSERVACAO': 'SYNTHETIC BASELINE SALE', 'SITUACAO': 'A'},
    'VENDA_DETALHE': {'QUANTIDADE': 1, 'VALOR_UNITARIO': 10, 'VALOR_SUBTOTAL': 10,
                'VALOR_TOTAL': 10, 'TAXA_COMISSAO': 10, 'VALOR_COMISSAO': 1},
    'VENDA_COMISSAO': {'VALOR_VENDA': 150, 'TIPO_CONTABIL': 'C', 'VALOR_COMISSAO': 15,
                'SITUACAO': 'A', 'DATA_LANCAMENTO': '2026-01-01'},
}


def synthetic_cpf():
    # Generated test identifier, no assertion of registration/real-person identity.
    digits = [int(c) for c in '900000001']
    for size in (9, 10):
        remainder = sum(d * (size + 1 - i) for i, d in enumerate(digits)) % 11
        digits.append(0 if remainder < 2 else 11 - remainder)
    return ''.join(str(d) for d in digits)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier(name):
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', name):
        raise ValueError('InvalidModelIdentifier')
    return '`' + name + '`'


def plan(receipt, run_id):
    if not re.fullmatch('[a-f0-9]{32}', run_id):
        raise ValueError('InvalidRunId')
    if receipt.get('model_sha256') != MODEL_SHA or receipt.get('model_version') != '2.0.0.16':
        raise ValueError('WrongAuthorModel')
    for name, expected in [('schema.sql', SCHEMA_SHA), ('views.sql', VIEWS_SHA)]:
        if receipt.get('artifacts', {}).get(name, {}).get('sha256') != expected:
            raise ValueError('WrongSchemaArtifact')
    tables = receipt['tables']
    if len(tables) != 40:
        raise ValueError('WrongTableScope')
    required = set(ROOTS)
    rows = {}
    while required - rows.keys():
        name = sorted(required - rows.keys())[0]
        table = tables[name]
        columns = {c['ColName']: c for c in table['columns']}
        row = {'ID': 1, **VALUES.get(name, {})}
        if name == 'PESSOA_FISICA':
            row['CPF'] = synthetic_cpf()
        if not row.keys() <= columns.keys():
            raise ValueError('MissingModelSeedColumn')
        fk_fields = {child: fk['parent'] for fk in table['foreign_keys'] for child in fk['fields'].values()}
        for cn, col in columns.items():
            if cn in row or col['NotNull'] != '1' or col['AutoInc'] == '1':
                continue
            if cn in fk_fields:
                row[cn] = 1
            else:
                raise ValueError('UnspecifiedRequiredModelValue:' + name + '.' + cn)
        for cn, value in row.items():
            col = columns[cn]
            if isinstance(value, int):
                if col['model_type'] not in ('INTEGER', 'DECIMAL') or value < 1 or value > 1000000:
                    raise ValueError('SeedIntegerTypeMismatch')
            elif isinstance(value, str):
                if col['model_type'] == 'DATE':
                    if not re.fullmatch(r'2026-01-0[12]', value):
                        raise ValueError('SeedDateBound')
                    continue
                if col['model_type'] not in ('CHAR', 'VARCHAR', 'TEXT'):
                    raise ValueError('SeedStringTypeMismatch')
                width = 65535 if col['model_type'] == 'TEXT' else int(col['DatatypeParams'].strip('()'))
                if len(value) > width or not re.fullmatch('[A-Z0-9 ]+', value):
                    raise ValueError('SeedStringBound')
            else:
                raise ValueError('UnsupportedSeedValue')
            if cn in fk_fields:
                required.add(fk_fields[cn])
        if columns['ID']['AutoInc'] != '1':
            raise ValueError('SeedIdNotNativeAutoIncrement')
        rows[name] = row
    # Topological inserts follow only populated FK edges. Omitted nullable refs
    # remain genuinely NULL; mandatory self/cycles are rejected, never disabled.
    ordered = []
    pending = dict(rows)
    while pending:
        ready = []
        for name, row in pending.items():
            parents = {fk['parent'] for fk in tables[name]['foreign_keys']
                       if any(child in row for child in fk['fields'].values())}
            if parents <= set(ordered):
                ready.append(name)
        if not ready:
            raise ValueError('PopulatedForeignKeyCycle')
        for name in sorted(ready):
            ordered.append(name)
            del pending[name]
    config = {'run_id': run_id, 'database': 't2ti_mf_' + run_id,
              'person_id': 1, 'operation_fiscal_id': 1, 'activity_id': 1,
              'situation_id': 1, 'seller_id': 1, 'payment_terms_id': 1,
              'transporter_id': 1, 'product_ids': [1] * 5,
              'sale_delete_action': 'NO ACTION', 'invoice_type_id': 1,
              'optional_quotation_id': None, 'optional_romaneio_id': None}
    expanded = {name: [row] for name, row in rows.items()}
    expanded['VENDA_DETALHE'] = [{**rows['VENDA_DETALHE'],
        'ID': i, 'QUANTIDADE': i, 'VALOR_SUBTOTAL': i * 10, 'VALOR_TOTAL': i * 10, 'VALOR_COMISSAO': i} for i in range(1, 6)]
    sql = ['START TRANSACTION;']
    for name in ordered:
        for row in expanded[name]:
            values = [str(v) if isinstance(v, int) else "'" + v + "'" for v in row.values()]
            sql.append('INSERT INTO ' + identifier(name) + ' (' + ', '.join(identifier(k) for k in row) +
                       ') VALUES (' + ', '.join(values) + ');')
    sql.append('COMMIT;')
    # DDL reseed is explicitly outside the insertion transaction (implicit commit).
    sql.extend('ALTER TABLE ' + identifier(name) + ' AUTO_INCREMENT=' +
               str(max(row['ID'] for row in expanded[name]) + 1) + ';' for name in ordered)
    return ('\n'.join(sql) + '\n').encode(), config, expanded, ordered


def generate(receipt_path, expected_receipt_sha, run_id, output):
    raw = Path(receipt_path).read_bytes()
    if digest(raw) != expected_receipt_sha:
        raise ValueError('ExportReceiptHashMismatch')
    sql, config, rows, order = plan(json.loads(raw), run_id)
    cfg = (json.dumps(config, indent=2, sort_keys=True) + '\n').encode()
    manifest = {'classification': 'DETERMINISTIC_SYNTHETIC_CUSTOMER_SALE_COMMISSION_ON_AUTHOR_SCHEMA',
                'native_execution': 'NOT_EXECUTED', 'run_id': run_id,
                'model_sha256': MODEL_SHA, 'schema_sha256': SCHEMA_SHA, 'views_sha256': VIEWS_SHA,
                'export_receipt_sha256': expected_receipt_sha,
                'generator_sha256': digest(Path(__file__).read_bytes()),
                'seed_sha256': digest(sql), 'config_sha256': digest(cfg),
                'expected_table_rows': {n: len(rows.get(n, [])) for n in json.loads(raw)['tables']},
                'seed_insert_order': order, 'seed_rows': rows,
                'explicit_ids': '1 per reference/customer/sale header/commission; details 1..5',
                'reseed_minimum_next_ids': {n: max(row['ID'] for row in entries) + 1 for n, entries in rows.items()},
                'preserved_baseline': {'customer_id': 1, 'header_id': 1, 'detail_ids': [1, 2, 3, 4, 5], 'commission_id': 1,
                                       'total': 150, 'commission_total': 15},
                'limitations': ['Not author seed data or a production business dataset',
                                'Original controller is not invoked; required commission side effects represented only as fixture data',
                                'Sale mapped VO columns/association compatibility is reported separately; no native proof',
                                'Optional quotation and romaneio remain NULL/unseeded, with full schema FKs preserved',
                                'Seller/product full-VO schema gaps remain unqualified',
                                'Native independent FK/row/reseed and CRUD proof pending']}
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    for name, data in [('seed.sql', sql), ('functional-config.json', cfg)]:
        (out / name).write_bytes(data)
    (out / 'seed-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export-receipt', required=True)
    p.add_argument('--receipt-sha256', required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    result = generate(a.export_receipt, a.receipt_sha256, a.run_id, a.out)
    print(json.dumps({k: result[k] for k in ('classification', 'native_execution', 'seed_sha256', 'config_sha256')}))
