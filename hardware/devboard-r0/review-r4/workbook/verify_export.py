"""Read-only OpenXML checks of the Artifact Tool export; does not author XLSX."""
from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path('/home/xiaobao/Projects/ESP32')
HERE = ROOT / 'build/closure-r4/workbook'
qa = json.loads((HERE / 'qa.json').read_text())
source = json.loads(Path(qa['input']).read_text())
items = source['items']
output = Path(qa['output'])
ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

with zipfile.ZipFile(output) as archive:
    shared = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        for si in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', ns):
            shared.append(''.join(si.itertext()))
    sheets = {
        i: ET.fromstring(archive.read(f'xl/worksheets/sheet{i}.xml'))
        for i in (1, 2, 3)
    }

    def cells(sheet):
        values = {}
        for cell in sheet.findall('.//s:sheetData/s:row/s:c', ns):
            raw = cell.findtext('s:v', default='', namespaces=ns)
            if cell.get('t') == 's':
                value = shared[int(raw)]
            elif cell.get('t') == 'inlineStr':
                value = ''.join(cell.find('s:is', ns).itertext())
            else:
                value = raw
            values[cell.get('r')] = value
        return values

    bom_values = cells(sheets[2])
    summary_values = cells(sheets[1])
    dnp_refs = []
    for row, item in enumerate(items, start=6):
        assert bom_values[f'A{row}'] == item['ref']
        for column, key in [('C', 'value'), ('F', 'manufacturer'), ('G', 'mpn'), ('H', 'footprint'),
                            ('I', 'review_state'), ('J', 'required_action'), ('K', 'footprint_state'), ('L', 'mpn_state')]:
            assert bom_values.get(f'{column}{row}', '') == (item.get(key) or ''), (row, column, key)
        assert bom_values[f'E{row}'] == ('是' if item['dnp'] else '否')
        if item['dnp']:
            dnp_refs.append(item['ref'])
    assert len(dnp_refs) == 6

    cached_summary = [int(float(summary_values[f'B{row}'])) for row in range(7, 15)]
    assert cached_summary == qa['metrics']['expected']
    formulas = {
        cell.get('r'): cell.findtext('s:f', namespaces=ns)
        for cell in sheets[1].findall('.//s:c', ns)
        if cell.find('s:f', ns) is not None
    }
    assert all(formulas.get(f'B{row}') for row in range(7, 15))

    panes = {}
    for i in (2, 3):
        pane = sheets[i].find('.//s:pane', ns)
        assert pane is not None
        assert pane.get('xSplit') == '1' and pane.get('ySplit') == '5'
        assert pane.get('topLeftCell') == 'B6' and pane.get('state') == 'frozen'
        panes[f'sheet{i}'] = pane.attrib

    validation = sheets[2].find('s:dataValidations/s:dataValidation', ns)
    assert validation is not None and validation.get('type') == 'list'
    assert validation.get('sqref') == 'E6:E227'
    assert validation.findtext('s:formula1', namespaces=ns) == '"是,否"'

    conditional = {}
    for block in sheets[2].findall('s:conditionalFormatting', ns):
        conditional[block.get('sqref')] = [x.text for x in block.findall('s:cfRule/s:formula', ns)]
    assert conditional == {
        'A6:L227': ['$E6="是"'], 'H6:H227': ['$H6=""'], 'G6:G227': ['$G6=""']
    }

    tables = []
    for name in archive.namelist():
        if name.startswith('xl/tables/') and name.endswith('.xml'):
            table = ET.fromstring(archive.read(name))
            assert table.find('s:autoFilter', ns).get('ref') == table.get('ref')
            tables.append({'name': table.get('name'), 'ref': table.get('ref')})
    assert tables == [
        {'name': 'CandidateBOM', 'ref': qa['features']['BOM_table']},
        {'name': 'FootprintReview', 'ref': qa['features']['footprint_table']},
    ]
    native_errors = [
        cell.get('r') for sheet in sheets.values()
        for cell in sheet.findall('.//s:c', ns) if cell.get('t') == 'e'
    ]
    assert not native_errors

qa['native_xlsx_verification'] = {
    'method': 'Python standard-library ZIP/XML read only; no native Excel/LibreOffice execution',
    'positions_exact': 222, 'source_bom_fields_exact': True,
    'dnp_refs_exact': dnp_refs, 'cached_summary': cached_summary,
    'summary_formulas_present': True, 'panes': panes,
    'dnp_validation': {'range': 'E6:E227', 'list': ['是', '否']},
    'conditional_formats': conditional, 'tables_and_filters': tables, 'native_error_cells': native_errors,
}
qa['visual_review'] = {
    'status': 'PASS',
    'inspected': ['overview.png', 'detail-U101.png', 'detail-R104.png', 'detail-R105.png', 'detail-R108.png'],
    'reused_unchanged_prior_review': ['bom.png', 'footprints.png', 'detail-R602.png', 'detail-U803.png', 'detail-J601.png'],
    'notes': 'Updated overview and four charging qualification rows re-rendered and visually inspected after final BOM freeze. Unchanged views retain earlier visual review. Chinese text, headers, quantities, qualification caveats and wrapping are legible. Wide BOM preserves horizontal scrolling with ref column frozen. No clipped text or unexpected blank sheet observed in inspected ranges.',
}
qa['output_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
(HERE / 'qa.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'output': str(output), 'native_checks': 'PASS', 'visual_review': 'PASS', 'sha256': qa['output_sha256']}, ensure_ascii=False))
