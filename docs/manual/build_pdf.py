"""Rebuild the downloadable manual from README.md and editable SVG illustrations.
Run: python docs/manual/build_pdf.py (requires reportlab).
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.graphics.shapes import Drawing, Rect, Circle, String

root = Path(__file__).resolve().parent
output = root.parents[1] / 'frontend/public/manual-guia-tareas.pdf'
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyManual',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=7,textColor=colors.HexColor('#233744')))
styles['Heading1'].textColor=colors.HexColor('#195b87')
styles['Heading1'].fontSize=21
styles['Heading1'].leading=26
styles['Heading2'].fontSize=13
styles['Heading2'].leading=18

def inline(text):
    text=escape(text)
    text=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'`([^`]+)`',r'\1',text)
    return text

def illustration(path):
    drawing=Drawing(1000,410)
    for node in ET.parse(path).getroot():
        a=node.attrib; tag=node.tag.split('}')[-1]; fill=colors.toColor(a.get('fill','#000000'))
        if tag=='rect': drawing.add(Rect(float(a.get('x',0)),410-float(a.get('y',0))-float(a['height']),float(a['width']),float(a['height']),rx=float(a.get('rx',0)),fillColor=fill,strokeColor=None))
        elif tag=='circle':drawing.add(Circle(float(a['cx']),410-float(a['cy']),float(a['r']),fillColor=fill,strokeColor=None))
        elif tag=='text':drawing.add(String(float(a['x']),410-float(a['y']),''.join(node.itertext()),fontName='Helvetica-Bold' if a.get('font-weight')=='bold' else 'Helvetica',fontSize=float(a.get('font-size',16)),fillColor=fill,textAnchor=a.get('text-anchor','start')))
    drawing.scale(.49,.49);drawing.width=490;drawing.height=201
    return drawing

source=(root/'README.md').read_text().split('## Cómo mantener este manual')[0]
sections=re.split(r'(?m)^## (?=\d\.)',source)[1:]
story=[]
for index,section in enumerate(sections):
    if index:story.append(PageBreak())
    lines=section.strip().splitlines();story.append(Paragraph(inline(lines.pop(0)),styles['Heading1']))
    i=0
    while i<len(lines):
        line=lines[i].strip();i+=1
        if not line or line=='---':continue
        if line.startswith('!['):
            path=re.search(r'\]\((.*?)\)',line).group(1)
            story.extend([illustration(root/path),Spacer(1,12)]);continue
        if line.startswith('|'):
            rows=[line]
            while i<len(lines) and lines[i].strip().startswith('|'):rows.append(lines[i].strip());i+=1
            data=[[Paragraph(inline(v.strip()),styles['BodyManual']) for v in row.strip('|').split('|')] for row in rows if not re.match(r'^\|[\s:|-]+\|$',row)]
            table=Table(data,colWidths=[135,355],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7f0f6')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(-1,-1),.4,colors.HexColor('#dfe5e9')),('INNERGRID',(0,0),(-1,-1),.3,colors.HexColor('#dfe5e9')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),3)]));story.extend([table,Spacer(1,8)]);continue
        if line.startswith('### '):story.append(Paragraph(inline(line[4:]),styles['Heading2']));continue
        if line.startswith('- '):line='• '+line[2:]
        story.append(Paragraph(inline(line),styles['BodyManual']))

def footer(canvas,doc):
    canvas.setTitle('Manual de uso - Bermúdez Ulloa')
    canvas.setFont('Helvetica',9);canvas.setFillColor(colors.HexColor('#627581'))
    canvas.drawString(48,28,'Bermúdez Ulloa | Manual de uso | 11/10/2026')
    canvas.drawRightString(A4[0]-48,28,str(doc.page))
    canvas.setFont('Helvetica-Bold',10);canvas.setFillColor(colors.HexColor('#195b87'));canvas.drawString(48,A4[1]-28,'ÁREA PROFESIONAL · GUÍA PARA CLIENTES')

SimpleDocTemplate(str(output),pagesize=A4,rightMargin=48,leftMargin=48,topMargin=52,bottomMargin=48).build(story,onFirstPage=footer,onLaterPages=footer)
print(output)
