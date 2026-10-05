#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Narrow native-MySQL semantic port of DBDesigner Fork's model exporter.

Derived from TEERTable.GetSQLCreateCode/GetSQLColumnCreateDefCode,
copyright Michael G. Zinner / Joao Paulo Schuler. See HANDOFF.md for pins.
Additive sale-root profile; renderer remains derived from the pinned quotation compiler.
No database connection, VO inference, seed generation or cross-engine mapping.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

MODEL_SHA = '539d45f095e707c9ce69811453ea991bafa39127aa2943aebbadd6bced160d50'
STANDALONE_SHA = 'bc7b68c3ce11f21012515e061c5adddb288a778d91cd1d93852811939c874793'
AUTHOR_REVISION = '4edadd042c8f2e484de95613c9ceb5548a342f91'
PUBLISHER_REVISION = '6d8a2635bc907100f46126d2512df0bf22b51c71'
PUBLISHER_UNIT_SHA = '81dd16fb554076f91e18049349aec80753c6e3c49a2f691cdd350dfcbf7595e7'
LEGACY_REVISION = '8b2b15f87d0b80c1623cf39a1948ef0bc19129d5'
LEGACY_UNIT_SHA = '98402b2ded35a893c98c948a8f5b494c047886d74ae262f7de2fa5d7add628ef'
ROOTS = {'CLIENTE', 'VENDA_CABECALHO', 'VENDA_DETALHE', 'VENDA_COMISSAO'}
BASE_COMPILER_SHA = '2529510cf3b36fc1ccf71e94c223a32118909dbe4666b8c8ae440e1cfdc87d30'
VIEW_NAMES = ('VIEW_PESSOA_CLIENTE', 'VIEW_PESSOA_TRANSPORTADORA')
VIEW_HASHES = {'VIEW_PESSOA_CLIENTE': 'e1f1f60eefc7520946f84128d744447b829ef838b8cefd129c4fdf5d06f406c9',
               'VIEW_PESSOA_TRANSPORTADORA': 'd8bfe5e4e7c59a71ecf1369c7124f7a249a13e6bd3eb159b8f6adbe7b2b9ae2f'}
VIEW_ROOTS = {'PESSOA_FISICA', 'PESSOA_JURIDICA', 'PESSOA_ENDERECO'}
ACTIONS = {'0': 'RESTRICT', '1': 'CASCADE', '2': 'SET NULL',
           '3': 'NO ACTION', '4': 'SET DEFAULT'}


class ModelError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ident(value):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', value or ''):
        raise ModelError('UnsupportedIdentifier')
    return '`' + value + '`'


def fields(value):
    result = {}
    for entry in value.replace('\\n', '\n').splitlines():
        if entry:
            key, val = entry.split('=', 1)
            if key in result:
                raise ModelError('DuplicateField')
            result[key] = val
    return result


def load_model(path, expected_sha):
    data = Path(path).read_bytes()
    if sha(data) != expected_sha:
        raise ModelError('ModelHashMismatch')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ModelError('ForbiddenXMLDeclaration')
    root = ET.fromstring(data)
    settings = root.find('.//GLOBALSETTINGS')
    if settings is None or settings.get('DatabaseType') != 'MySQL' or settings.get('DBQuoteCharacter') != '`':
        raise ModelError('NotPublisherMySQLModel')
    return root


def closure(root, names):
    tables = {t.get('ID'): t for t in root.iter('TABLE')}
    byname = {t.get('Tablename'): key for key, t in tables.items()}
    try:
        selected = {byname[name] for name in names}
    except KeyError as exc:
        raise ModelError('MissingRequiredTable') from exc
    relations = [r for r in root.iter('RELATION') if r.get('CreateRefDef') == '1']
    while True:
        parents = {r.get('SrcTable') for r in relations if r.get('DestTable') in selected}
        if not parents <= tables.keys():
            raise ModelError('MissingParentTable')
        if parents <= selected:
            break
        selected |= parents
    return tables, selected, relations


def column_sql(col, types):
    try:
        dt = types[col.get('idDatatype')]
    except KeyError as exc:
        raise ModelError('MissingDatatype') from exc
    typename = dt.get('TypeName')
    if dt.get('PhysicalMapping') != '0' or typename not in {'INTEGER', 'DECIMAL', 'DATE', 'CHAR', 'VARCHAR', 'TEXT'}:
        raise ModelError('UnsupportedPhysicalDatatype')
    params = col.get('DatatypeParams', '')
    patterns = {'INTEGER': r'(?:\([0-9]+\))?', 'DECIMAL': r'(?:\([0-9]+(?:,[0-9]+)?\))?',
                'CHAR': r'\([0-9]+\)', 'VARCHAR': r'\([0-9]+\)', 'DATE': '', 'TEXT': ''}
    if not re.fullmatch(patterns[typename], params):
        raise ModelError('UnsupportedDatatypeParameters')
    options = dt.findall('./OPTIONS/OPTION')
    selected = col.findall('./OPTIONSELECTED/OPTIONSELECT')
    if len(options) != len(selected) or len(options) != int(dt.get('OptionCount')):
        raise ModelError('DatatypeOptionShapeMismatch')
    sql = ident(col.get('ColName')) + ' ' + typename + params
    for option, value in zip(options, selected):
        if value.get('Value') not in ('0', '1') or option.get('Name') not in ('UNSIGNED', 'ZEROFILL', 'BINARY'):
            raise ModelError('UnsupportedDatatypeOption')
        if value.get('Value') == '1':
            sql += ' ' + option.get('Name')
    for attr in ('NotNull', 'AutoInc', 'PrimaryKey'):
        if col.get(attr) not in ('0', '1'):
            raise ModelError('UnsupportedColumnFlag')
    sql += ' NOT NULL' if col.get('NotNull') == '1' else ' NULL'
    default = col.get('DefaultValue', '')
    if default:
        # The selected model contains numeric zero defaults only. Do not invent quoting.
        if default != '0':
            raise ModelError('UnsupportedDefaultValue')
        sql += ' DEFAULT 0'
    if col.get('AutoInc') == '1':
        if typename != 'INTEGER':
            raise ModelError('UnsupportedAutoIncrementType')
        sql += ' AUTO_INCREMENT'
    return sql


def describe(root, include_views=True):
    tables, core, relations = closure(root, ROOTS)
    _, selected, _ = closure(root, ROOTS | VIEW_ROOTS if include_views else ROOTS)
    if len(core) != 36 or (include_views and len(selected) != 40):
        raise ModelError('ScopeMismatch')
    if any(r.get('OverwriteTableType') != '0' for r in root.iter('REGION')):
        raise ModelError('UnsupportedRegionEngineOverride')
    types = {t.get('ID'): t for t in root.iter('DATATYPE')}
    output = {}
    for key in sorted(selected, key=lambda k: tables[k].get('Tablename')):
        table = tables[key]
        if any(table.get(k) != '0' for k in ('TablePrefix', 'Temporary', 'IsLinkedObject')):
            raise ModelError('UnsupportedTableFeature')
        if table.get('TableType') != '1':
            raise ModelError('NotOriginalInnoDBTable')
        if any(v != '0' for v in fields(table.get('TableOptions', '')).values()):
            raise ModelError('UnsupportedTableOption')
        name = table.get('Tablename')
        cols = table.findall('./COLUMNS/COLUMN')
        colbyid = {c.get('ID'): c for c in cols}
        definitions = [column_sql(c, types) for c in cols]
        index_inventory = []
        for index in table.findall('./INDICES/INDEX'):
            parts = []
            column_names = []
            for item in index.findall('./INDEXCOLUMNS/INDEXCOLUMN'):
                if item.get('idColumn') not in colbyid:
                    raise ModelError('MissingIndexColumn')
                cn = colbyid[item.get('idColumn')].get('ColName')
                length = item.get('LengthParam')
                if not re.fullmatch('[0-9]+', length or ''):
                    raise ModelError('UnsupportedIndexLength')
                parts.append(ident(cn) + ('(' + length + ')' if length != '0' else ''))
                column_names.append({'name': cn, 'prefix_length': int(length)})
            if not parts:
                raise ModelError('EmptyIndex')
            kind = index.get('IndexKind')
            prefixes = {'0': 'PRIMARY KEY', '1': 'INDEX ' + ident(index.get('IndexName')),
                        '2': 'UNIQUE INDEX ' + ident(index.get('IndexName')),
                        '3': 'FULLTEXT INDEX ' + ident(index.get('IndexName'))}
            if kind not in prefixes:
                raise ModelError('UnsupportedIndexKind')
            definitions.append(prefixes[kind] + '(' + ', '.join(parts) + ')')
            index_inventory.append({'name': index.get('IndexName'), 'kind': kind, 'columns': column_names})
        foreign_keys = []
        for rel in relations:
            if rel.get('DestTable') != key:
                continue
            parent = tables[rel.get('SrcTable')]
            pairs = fields(rel.get('FKFields', ''))
            if not pairs:
                raise ModelError('EmptyForeignKey')
            parent_cols = {c.get('ColName') for c in parent.findall('./COLUMNS/COLUMN')}
            child_cols = {c.get('ColName') for c in cols}
            if not pairs.keys() <= parent_cols or not set(pairs.values()) <= child_cols:
                raise ModelError('MissingForeignKeyColumn')
            ref = fields(rel.get('RefDef', ''))
            if set(ref) != {'Matching', 'OnDelete', 'OnUpdate'} or ref['Matching'] != '0':
                raise ModelError('UnsupportedReferenceDefinition')
            if ref['OnDelete'] not in ACTIONS or ref['OnUpdate'] not in ACTIONS:
                raise ModelError('UnknownReferenceAction')
            fk = ('FOREIGN KEY ' + ident(rel.get('RelationName')) + ' (' +
                  ', '.join(ident(c) for c in pairs.values()) + ') REFERENCES ' +
                  ident(parent.get('Tablename')) + ' (' + ', '.join(ident(c) for c in pairs) +
                  ') ON DELETE ' + ACTIONS[ref['OnDelete']] + ' ON UPDATE ' + ACTIONS[ref['OnUpdate']])
            foreign_keys.append({'name': rel.get('RelationName'), 'parent': parent.get('Tablename'),
                                 'fields': pairs, 'raw_actions': ref, 'sql': fk})
        output[name] = {'model_id': key, 'engine': 'InnoDB', 'model_table_type': '1',
                        'columns': [{**c.attrib, 'model_type': types[c.get('idDatatype')].get('TypeName'),
                                     'selected_options': [o.get('Value') for o in c.findall('./OPTIONSELECTED/OPTIONSELECT')],
                                     'sql': column_sql(c, types)} for c in cols],
                        'indexes': index_inventory, 'foreign_keys': foreign_keys,
                        'create_sql': 'CREATE TABLE ' + ident(name) + ' (\n  ' +
                        ',\n  '.join(definitions) + '\n) ENGINE=InnoDB;'}
    return output, sorted(tables[k].get('Tablename') for k in core)


def export(model, views_dir, out, standalone=None):
    root = load_model(model, MODEL_SHA)
    tables, core = describe(root)
    # All tables first; ALTER adds unchanged model FKs without disabling FK checks,
    # including the author's self/cyclic EMPRESA dependency. No data are generated.
    sql = '\n\n'.join(t['create_sql'] for t in tables.values()) + '\n\n'
    sql += '\n'.join('ALTER TABLE ' + ident(name) + ' ADD ' + fk['sql'] + ';'
                     for name, table in tables.items() for fk in table['foreign_keys']) + '\n'
    view_blobs = []
    view_info = []
    for name in VIEW_NAMES:
        path = Path(views_dir) / (name + '.txt')
        data = path.read_bytes()
        if sha(data) != VIEW_HASHES[name]:
            raise ModelError('AuthorViewHashMismatch')
        text = data.decode('utf-8-sig')
        if not re.match(r'\s*CREATE\s+VIEW\s+' + name + r'\s+AS\b', text, re.I):
            raise ModelError('UnexpectedAuthorView')
        dependencies = set(re.findall(r'\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z_0-9]*)', text, re.I))
        if not dependencies <= tables.keys():
            raise ModelError('MissingViewDependency')
        # Source bytes preserved, only an explicit statement terminator appended.
        view_blobs.append(data + b'\n;\n')
        view_info.append({'name': name, 'source_file': path.name, 'sha256': sha(data),
                          'bytes': len(data), 'dependencies': sorted(dependencies)})
    comparison = None
    if standalone:
        other, other_core = describe(load_model(standalone, STANDALONE_SHA))
        semantic = lambda t: {k: {f: v[f] for f in ('engine', 'indexes', 'foreign_keys', 'create_sql')}
                             for k, v in t.items()}
        # Column renderer included in create_sql; UI/comment/previous-name differences excluded.
        changed = [name for name in tables if semantic(tables)[name] != semantic(other)[name]]
        comparison = {'standalone_sha256': STANDALONE_SHA,
                      'internal_version': '1.0.0.1', 'core_equal': core == other_core,
                      'changed_semantic_tables': changed}
    receipt = {'status': 'MODEL_DERIVED_NATIVE_MYSQL_EXPORT_PORT',
               'native_database_execution': 'NOT_EXECUTED', 'publisher_binary_execution': 'NOT_EXECUTED',
               'author_revision': AUTHOR_REVISION, 'model_sha256': MODEL_SHA,
               'model_version': '2.0.0.16', 'publisher_revision': PUBLISHER_REVISION,
               'publisher_source': {'repository': 'https://github.com/joaopauloschuler/dbdesigner-fork',
                                    'unit': 'src/EERModel.pas', 'sha256': PUBLISHER_UNIT_SHA,
                                    'legacy_revision': LEGACY_REVISION, 'legacy_unit_sha256': LEGACY_UNIT_SHA,
                                    'foreign_key_actions': ACTIONS,
                                    'selected_engine': {'model_table_type': '1', 'mysql_engine': 'InnoDB'},
                                    'license': 'GPL-2.0-or-later'},
               'compiler_sha256': sha(Path(__file__).read_bytes()),
               'base_compiler_sha256': BASE_COMPILER_SHA,
               'root_tables': sorted(ROOTS),
               'scope_note': 'Nullable sales FK requires quotation header in parent closure; it is not a quotation workload root or seeded quotation. No quotation detail root added.',
               'core_parent_fk_tables': core,
               'view_support_tables': sorted(set(tables) - set(core)),
               'tables': tables, 'views': view_info, 'standalone_comparison': comparison,
               'profile': {'enclose_names': True, 'hide_null': False, 'comments': False,
                           'add_quotes_to_defaults': False, 'define_pk': True,
                           'create_indices': True, 'create_refdefs': True,
                           'region_override': False, 'fk_emission': 'ALTER after all CREATE',
                           'charset_collation': 'not defined by model; runtime must explicitly report',
                           'sql_mode': 'ANSI_QUOTES must be absent for unmodified author views'},
               'limitations': ['Not a restored original database or publisher-binary export',
                               'No seed rows, stored procedures or trigger reconstruction',
                               'Only the two unchanged author person views included; other VO associations remain separate qualification dependencies',
                               'Database/import/runtime/DDL compatibility qualification pending']}
    payloads = {'schema.sql': sql.encode('utf-8'), 'views.sql': b'\n'.join(view_blobs)}
    receipt['artifacts'] = {n: {'sha256': sha(b), 'bytes': len(b)} for n, b in payloads.items()}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        (out / name).write_bytes(data)
    (out / 'export-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--views-dir', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--standalone')
    args = parser.parse_args()
    try:
        result = export(args.model, args.views_dir, args.out, args.standalone)
        print(json.dumps({'status': result['status'], 'tables': len(result['tables']),
                          'model_sha256': result['model_sha256'], 'artifacts': result['artifacts']}))
    except (ModelError, ET.ParseError, OSError) as exc:
        raise SystemExit(type(exc).__name__ + ': ' + str(exc))
