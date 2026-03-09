"""
Gerador de PDF de Renovações — para as gurias imprimirem/encaminharem
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from datetime import date, timedelta
import io


# Sierra palette
BLUE_DARK = colors.HexColor("#1a5276")
BLUE_MED = colors.HexColor("#2980b9")
BLUE_LIGHT = colors.HexColor("#d6eaf8")
GOLD = colors.HexColor("#f39c12")
GOLD_LIGHT = colors.HexColor("#fef9e7")
RED = colors.HexColor("#e74c3c")
RED_LIGHT = colors.HexColor("#fdedec")
ORANGE = colors.HexColor("#f39c12")
GREEN = colors.HexColor("#27ae60")
GRAY = colors.HexColor("#95a5a6")
WHITE = colors.white


def generate_renovacoes_pdf(data: list, dias: int = 60) -> bytes:
    """
    Gera PDF com lista de renovações.
    data: list of dicts com campos: vencimento, cliente, cpf, seguradora, ramo, numero, produtor, premio, renovacao_status
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, 
        pagesize=landscape(A4),
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=16, textColor=BLUE_DARK, fontName='Helvetica-Bold',
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle', parent=styles['Normal'],
        fontSize=9, textColor=GRAY, fontName='Helvetica',
        spaceAfter=12
    )
    
    elements = []
    
    # Header
    today = date.today()
    elements.append(Paragraph("🔄 Renovações — Sierra Seguros", title_style))
    elements.append(Paragraph(
        f"Próximos {dias} dias · Gerado em {today.strftime('%d/%m/%Y')} · {len(data)} apólices",
        subtitle_style
    ))
    
    # Summary stats
    total_premio = sum(r.get('premio', 0) or 0 for r in data)
    urgentes = len([r for r in data if _days_until(r.get('vencimento')) <= 7])
    atencao = len([r for r in data if 7 < _days_until(r.get('vencimento')) <= 30])
    
    summary_data = [[
        Paragraph(f'<b>{len(data)}</b><br/><font size=7>Total</font>', 
                  ParagraphStyle('s', alignment=TA_CENTER, fontSize=14, textColor=BLUE_DARK)),
        Paragraph(f'<b>{urgentes}</b><br/><font size=7 color="red">Urgentes (≤7d)</font>', 
                  ParagraphStyle('s', alignment=TA_CENTER, fontSize=14, textColor=RED)),
        Paragraph(f'<b>{atencao}</b><br/><font size=7 color="#f39c12">Atenção (≤30d)</font>', 
                  ParagraphStyle('s', alignment=TA_CENTER, fontSize=14, textColor=ORANGE)),
        Paragraph(f'<b>R$ {total_premio:,.2f}</b><br/><font size=7>Prêmio Total</font>', 
                  ParagraphStyle('s', alignment=TA_CENTER, fontSize=14, textColor=GREEN)),
    ]]
    
    summary_table = Table(summary_data, colWidths=[60*mm, 60*mm, 60*mm, 80*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8f9fb")),
        ('BOX', (0, 0), (-1, -1), 0.5, BLUE_LIGHT),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BLUE_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 8*mm))
    
    # Main table
    cell_style = ParagraphStyle('cell', fontSize=8, fontName='Helvetica', leading=10)
    cell_bold = ParagraphStyle('cellb', fontSize=8, fontName='Helvetica-Bold', leading=10)
    cell_right = ParagraphStyle('cellr', fontSize=8, fontName='Helvetica', alignment=TA_RIGHT, leading=10)
    cell_center = ParagraphStyle('cellc', fontSize=8, fontName='Helvetica', alignment=TA_CENTER, leading=10)
    
    header_style = ParagraphStyle('hdr', fontSize=7, fontName='Helvetica-Bold', textColor=WHITE, 
                                   alignment=TA_CENTER, leading=9)
    
    # Table header
    table_data = [[
        Paragraph('VENCE EM', header_style),
        Paragraph('DATA', header_style),
        Paragraph('CLIENTE', header_style),
        Paragraph('CPF/CNPJ', header_style),
        Paragraph('SEGURADORA', header_style),
        Paragraph('RAMO', header_style),
        Paragraph('APÓLICE', header_style),
        Paragraph('PRODUTOR', header_style),
        Paragraph('PRÊMIO', header_style),
        Paragraph('STATUS', header_style),
        Paragraph('✓', header_style),
    ]]
    
    # Sort by vencimento
    data_sorted = sorted(data, key=lambda r: r.get('vencimento', '9999'))
    
    for r in data_sorted:
        days = _days_until(r.get('vencimento'))
        if days < 0:
            days_txt = f'{abs(days)}d atrás'
        else:
            days_txt = f'{days}d'
        
        venc = _fmt_date(r.get('vencimento', ''))
        
        table_data.append([
            Paragraph(f'<b>{days_txt}</b>', cell_center),
            Paragraph(venc, cell_center),
            Paragraph(f'<b>{(r.get("cliente") or "—")[:35]}</b>', cell_style),
            Paragraph(r.get('cpf', '') or '—', cell_style),
            Paragraph(r.get('seguradora', '') or '—', cell_center),
            Paragraph(r.get('ramo', '') or '—', cell_center),
            Paragraph(r.get('numero', '') or '—', cell_style),
            Paragraph((r.get('produtor', '') or '—')[:15], cell_style),
            Paragraph(f'R$ {(r.get("premio") or 0):,.2f}', cell_right),
            Paragraph(_status_label(r.get('renovacao_status', 'pendente')), cell_center),
            Paragraph('☐', cell_center),  # checkbox for manual marking
        ])
    
    col_widths = [18*mm, 20*mm, 55*mm, 32*mm, 22*mm, 15*mm, 25*mm, 25*mm, 25*mm, 20*mm, 10*mm]
    
    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Style rows with alternating colors and urgency highlighting
    style_cmds = [
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), BLUE_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        
        # Grid
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#ddd")),
        ('BOX', (0, 0), (-1, -1), 0.5, BLUE_DARK),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    
    # Alternating row colors + urgency
    for i, r in enumerate(data_sorted):
        row = i + 1  # skip header
        days = _days_until(r.get('vencimento'))
        
        if days <= 7:
            style_cmds.append(('BACKGROUND', (0, row), (-1, row), RED_LIGHT))
        elif days <= 30:
            style_cmds.append(('BACKGROUND', (0, row), (-1, row), GOLD_LIGHT))
        elif i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, row), (-1, row), colors.HexColor("#f8f9fb")))
    
    main_table.setStyle(TableStyle(style_cmds))
    elements.append(main_table)
    
    # Footer
    elements.append(Spacer(1, 6*mm))
    footer_style = ParagraphStyle('footer', fontSize=7, textColor=GRAY, alignment=TA_CENTER)
    elements.append(Paragraph(
        f"Sierra Seguros · Relatório de Renovações · {today.strftime('%d/%m/%Y')} · Gerado automaticamente",
        footer_style
    ))
    
    doc.build(elements)
    return buf.getvalue()


def _days_until(d):
    if not d:
        return 999
    try:
        parts = d.split('-')
        target = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return (target - date.today()).days
    except:
        return 999


def _fmt_date(d):
    if not d:
        return '—'
    try:
        parts = d.split('-')
        return f'{parts[2]}/{parts[1]}/{parts[0]}'
    except:
        return d


def _status_label(s):
    labels = {
        'pendente': '⏳',
        'contatado': '📞',
        'cotando': '📝',
        'renovado': '✅',
        'perdido': '❌',
        'cancelado': '🚫',
    }
    return labels.get(s, s)
