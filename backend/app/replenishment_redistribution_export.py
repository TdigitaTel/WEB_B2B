"""Excel rendering of a validated redistribution proposal, never client supplied rows."""
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from .replenishment_source import DELEGATIONS


def workbook_bytes(proposal):
    book=Workbook(write_only=True)
    names={'00':'Almeiras',**DELEGATIONS}

    def sheet(name,headers,rows):
        page=book.create_sheet(name);page.freeze_panes='A2'
        for index,label in enumerate(headers,1):page.column_dimensions[get_column_letter(index)].width=min(48,max(18,len(label)+3))
        def append(values,heading=False):
            cells=[]
            for value in values:
                if isinstance(value,str):
                    cell=WriteOnlyCell(page,value=ILLEGAL_CHARACTERS_RE.sub('',value));cell.data_type='s'
                else:
                    cell=WriteOnlyCell(page,value=value)
                    if len(cells)<len(headers) and headers[len(cells)]=='Sobrestock transferible en origen':cell.number_format='0'
                if heading:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='1D608A')
                cells.append(cell)
            page.append(cells)
        append(headers,True);count=0
        for row in rows:append(row);count+=1
        page.auto_filter.ref=f'A1:{get_column_letter(len(headers))}{count+1}'
        return page

    sheet('Movimientos',['Código material','Descripción','Origen código','Origen delegación','Destino código','Destino delegación',
        'Cantidad','Unidad','Motivo','Stock máximo en origen','Sobrestock transferible en origen'],
        ([m['sku'],m['description'],m['from_delegation'],names.get(m['from_delegation'],m['from_delegation']),
          m['to_delegation'],names.get(m['to_delegation'],m['to_delegation']),m['quantity'],m['unit_type'],
          'Devolución a Almeiras' if m['kind']=='RETURN_CENTRAL' else 'Cubrir necesidad de otra delegación',
          m['origin_maximum_stock'],m['origin_transferable_surplus']] for m in proposal['movements']))
    sheet('Necesidades sin cubrir',['Código material','Delegación código','Delegación','Cantidad pendiente','Unidad'],
        ([n['sku'],n['delegation'],names.get(n['delegation'],n['delegation']),n['quantity'],n['unit_type']] for n in proposal['unmet_needs']))
    sheet('Alertas',['Ámbito','Código material','Mensaje'],
        [*(['General','',w] for w in proposal['warnings']),*(['Material excluido',w['sku'],w['reason']] for w in proposal['material_warnings'])])
    sheet('Cálculos utilizados',['Delegación código','Delegación','Identificador cálculo','Stock consultado','Ventas desde','Ventas hasta'],
        ([c['delegation'],c['name'],c['scenario_id'],c['captured_at'],c['date_from'],c['date_to']] for c in proposal['calculations']))
    summary=proposal['summary']
    sheet('Resumen',['Dato','Valor'],[
        ['Exportado el (Europe/Madrid)',datetime.now(ZoneInfo('Europe/Madrid')).isoformat()],
        ['Referencia de la propuesta',proposal['fingerprint']],['Criterio de consumo',proposal.get('consumption_basis_label','Media')],['Materiales con movimientos',summary['materials']],
        ['Movimientos entre delegaciones',summary['transfers']],['Devoluciones a Almeiras',summary['returns_to_central']],
        ['Necesidades sin cubrir',summary['unmet_needs']],['Materiales excluidos',summary['excluded_materials']],
        ['Alcance','Propuesta completa; la búsqueda de pantalla no limita el Excel. No se ejecutan traslados ni reservas en EXIT.'],
        ['Regla de origen','Stock físico − comprometido − stock máximo; no se despachan entradas pendientes.'],
        ['Unidades','Las cantidades conservan su unidad. No se suman cantidades de unidades diferentes.'],
    ])
    buffer=io.BytesIO();book.save(buffer);return buffer.getvalue()
