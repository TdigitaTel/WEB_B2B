"""Rebuild the downloadable manual from README.md and editable SVG illustrations.
Run: python docs/manual/build_pdf.py (requires reportlab).
"""
from pathlib import Path
import re
import json
import xml.etree.ElementTree as ET
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.graphics.shapes import Drawing, Rect, Circle, String

root = Path(__file__).resolve().parent
output = root.parents[1] / 'frontend/public/manual-guia-tareas.pdf'
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyManual',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=7,textColor=colors.HexColor('#233744')))
styles['Heading1'].textColor=colors.HexColor('#233744')
styles['Heading1'].fontName='Helvetica-Bold'
styles['Heading1'].spaceAfter=18
styles['Heading1'].fontSize=23
styles['Heading1'].leading=26
styles['Heading2'].fontSize=13
styles['Heading2'].leading=18

def inline(text):
    text=escape(text)
    text=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'`([^`]+)`',r'\1',text)
    return text

def illustration(path, compact=False):
    height=float(ET.parse(path).getroot().attrib["height"])
    drawing=Drawing(622 if compact else 1000,height)
    for node in ET.parse(path).getroot():
        a=node.attrib; tag=node.tag.split('}')[-1]
        if compact and (float(a.get('x',a.get('cx',0)))>=622 or (tag=='rect' and float(a.get('width',0))>622)):
            continue
        fill=colors.toColor(a.get('fill','#000000'))
        if tag=='rect': drawing.add(Rect(float(a.get('x',0)),height-float(a.get('y',0))-float(a['height']),float(a['width']),float(a['height']),rx=float(a.get('rx',0)),fillColor=fill,strokeColor=None))
        elif tag=='circle':drawing.add(Circle(float(a['cx']),height-float(a['cy']),float(a['r']),fillColor=fill,strokeColor=None))
        elif tag=='text':drawing.add(String(float(a['x']),height-float(a['y']),''.join(node.itertext()),fontName='Helvetica-Bold' if a.get('font-weight')=='bold' else 'Helvetica',fontSize=float(a.get('font-size',16)),fillColor=fill,textAnchor=a.get('text-anchor','start')))
    scale=190/622 if compact else .49
    drawing.scale(scale,scale);drawing.width=190 if compact else 490;drawing.height=height*scale
    return drawing

class ScreenshotDetail(Flowable):
    """Place a readable detail of an original screenshot in the PDF layout."""
    def __init__(self, spec):
        super().__init__()
        self.spec=spec
        x1,y1,x2,y2=spec['box']
        self.scale=min(190/(x2-x1),spec.get("max_height",140)/(y2-y1))
        self.width=(x2-x1)*self.scale
        self.height=(y2-y1)*self.scale
    def draw(self):
        canvas=self.canv
        image=ImageReader(str(root/'assets'/self.spec['file']))
        iw,ih=image.getSize()
        x1,y1,x2,y2=self.spec['box']
        canvas.saveState()
        path=canvas.beginPath();path.rect(0,0,self.width,self.height)
        canvas.clipPath(path,stroke=0,fill=0)
        canvas.drawImage(image,-x1*self.scale,-(ih-y2)*self.scale,
                         width=iw*self.scale,height=ih*self.scale)
        canvas.restoreState()
        canvas.setStrokeColor(colors.HexColor('#dfe5e9'))
        canvas.roundRect(0,0,self.width,self.height,4,stroke=1,fill=0)

captures=json.loads((root/'assets/capturas.json').read_text())
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
        if re.match(r'^\d+\. ',line):
            number,text=line.split('. ',1)
            if index==1 and number=='6':
                story.append(PageBreak())
                story.append(Paragraph('Quiero hacer un pedido · continuación',styles['Heading1']))
            badge=Drawing(24,26)
            badge.add(Circle(11,14,10,fillColor=colors.HexColor('#195b87'),strokeColor=None))
            badge.add(String(11,10,number,fontName='Helvetica-Bold',fontSize=11,fillColor=colors.white,textAnchor='middle'))
            step=[Paragraph(inline(text),styles['BodyManual'])]
            j=i
            while j<len(lines) and not lines[j].strip():j+=1
            if j<len(lines) and lines[j].strip().startswith('!['):
                path=re.search(r'\]\((.*?)\)',lines[j]).group(1)
                spec=captures.get(f"{index+1}:{number}")
                visual=ScreenshotDetail(spec) if spec else illustration(root/path,compact=True)
                row=Table([[badge,step[0],visual]],colWidths=[28,269,198],hAlign='LEFT')
                row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(0,0),4),('RIGHTPADDING',(1,0),(1,0),16),('RIGHTPADDING',(2,0),(2,0),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
                step=[row,Spacer(1,8)]
                i=j+1
            story.append(KeepTogether(step))
        else:story.append(Paragraph(inline(line),styles['BodyManual']))

def footer(canvas,doc):
    canvas.setTitle('Manual de uso - Bermúdez Ulloa')
    canvas.setFont('Helvetica',9);canvas.setFillColor(colors.HexColor('#627581'))
    canvas.drawString(48,28,'Bermúdez Ulloa | Manual de uso | 11/10/2026')
    canvas.drawRightString(A4[0]-48,28,str(doc.page))
    canvas.setFont('Helvetica-Bold',10);canvas.setFillColor(colors.HexColor('#195b87'));canvas.drawString(48,A4[1]-28,'ÁREA PROFESIONAL · GUÍA PARA CLIENTES')

SimpleDocTemplate(str(output),pagesize=A4,rightMargin=48,leftMargin=48,topMargin=52,bottomMargin=48).build(story,onFirstPage=footer,onLaterPages=footer)
print(output)
