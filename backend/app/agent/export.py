import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from typing import List, Dict, Any
import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../../../data/exports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_pdf_quotation(quotation_id: str, items_data: Any, total_cost: float) -> str:
    """Generates a professional PDF quotation with 6 columns."""
    filename = f"quotation_{quotation_id}_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Flatten items if it's a dict (materials/labor)
    items = []
    if isinstance(items_data, dict):
        if "materials" in items_data:
            items.extend(items_data["materials"].get("items", []))
        if "labor" in items_data:
            items.extend(items_data["labor"].get("trades", []))
    elif isinstance(items_data, list):
        items = items_data
    
    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 750, f"Construction Quotation #{quotation_id}")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, 730, f"Date: {datetime.date.today()}")
    c.drawString(50, 715, "Status: Professional Estimate")
    
    # Table Headers
    y = 680
    c.setFont("Helvetica-Bold", 10)
    c.drawString(30, y, "No")
    c.drawString(60, y, "Description (Unified BOQ)")
    c.drawString(350, y, "Unit")
    c.drawString(400, y, "Qty")
    c.drawString(450, y, "Price")
    c.drawString(510, y, "Total (EGP)")
    
    c.line(30, y-5, 570, y-5)
    
    y -= 25
    c.setFont("Helvetica", 9)
    
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict): continue
        
        name = item.get("description") or item.get("name") or item.get("trade", "Unknown Item")
        # simple truncation for PDF layout
        if len(name) > 60: name = name[:57] + "..."
        
        unit = item.get("unit", "ea")
        qty = item.get("quantity") or item.get("hours", 0)
        price = item.get("unit_price") or item.get("rate", 0)
        line_total = item.get("total") or (float(qty) * float(price))
        
        c.drawString(30, y, str(i))
        c.drawString(60, y, name)
        c.drawString(350, y, str(unit))
        c.drawString(400, y, f"{qty:.2f}")
        c.drawString(450, y, f"{price:.2f}")
        c.drawString(510, y, f"{line_total:.2f}")
        y -= 20
        
        if y < 60:
            c.showPage()
            y = 750
            c.setFont("Helvetica", 9)
            
    c.line(30, y, 570, y)
    y -= 25
    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, y, "Grand Total:")
    c.drawString(500, y, f"{total_cost:,.2f} EGP")
    
    c.save()
    return filepath

def generate_excel_quotation(quotation_id: str, items_data: Any, total_cost: float) -> str:
    """Generates a professional Excel quotation matching the 6-column reference."""
    filename = f"quotation_{quotation_id}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Flatten items if it's a dict
    items = []
    if isinstance(items_data, dict):
        if "materials" in items_data:
            items.extend(items_data["materials"].get("items", []))
        if "labor" in items_data:
            items.extend(items_data["labor"].get("trades", []))
    elif isinstance(items_data, list):
        items = items_data
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Professional BOQ"
    
    # Style headers
    from openpyxl.styles import Font, Alignment, PatternFill
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    
    ws.append(["Quotation ID", quotation_id])
    ws.append(["Date", datetime.date.today()])
    ws.append([])
    
    # 6-Column Header
    headers = ["Item No", "Description (الوصف)", "Unit (وحدة)", "Unit Price (EGP)", "Quantity (MOQ)", "Total (EGP)"]
    ws.append(headers)
    
    for cell in ws[4]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict): continue
        
        # Priority: explicit description > name > trade
        desc = item.get("description") or item.get("name") or item.get("trade", "Unknown")
        unit = item.get("unit") or ( "hr" if "trade" in item else "-")
        qty = item.get("quantity") or item.get("hours", 0)
        price = item.get("unit_price") or item.get("rate", 0)
        total = item.get("total") or (float(qty) * float(price))
        
        row = [i, desc, unit, price, qty, total]
        ws.append(row)
        
        # Wrap text for description
        ws.cell(row=ws.max_row, column=2).alignment = Alignment(wrap_text=True, horizontal="right")

    ws.append([])
    ws.append(["", "", "", "", "Grand Total", total_cost])
    ws[ws.max_row][5].font = Font(bold=True)
    ws[ws.max_row][6].font = Font(bold=True)

    # Adjust column widths
    ws.column_dimensions['A'].width = 10
    ws.column_dimensions['B'].width = 80
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 15
    ws.column_dimensions['F'].width = 20
    
    wb.save(filepath)
    return filepath
