from io import BytesIO
from typing import Dict, Any, Optional
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
from app.models.quotation import Quotation, QuotationData
from app.utils.language_detector import detect_language
# from app.utils.quotation_descriptions import get_category_description
import os
import logging

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Generate PDF quotation documents"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.arabic_font_name = 'Helvetica'  # Default fallback
        self._setup_bilingual_fonts()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles with Arabic font support"""
        # Only add styles if they don't already exist
        if 'CustomTitle' not in self.styles.byName:
            self.styles.add(ParagraphStyle(
                name='CustomTitle',
                parent=self.styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#1a1a1a'),
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName=self.arabic_font_name
            ))
        
        if 'SectionHeading' not in self.styles.byName:
            self.styles.add(ParagraphStyle(
                name='SectionHeading',
                parent=self.styles['Heading2'],
                fontSize=16,
                textColor=colors.HexColor('#0070f3'),
                spaceAfter=12,
                spaceBefore=20,
                fontName=self.arabic_font_name
            ))
        
        # Modify existing BodyText style instead of adding a new one
        if 'BodyText' in self.styles.byName:
            self.styles['BodyText'].fontSize = 11
            self.styles['BodyText'].textColor = colors.HexColor('#333333')
            self.styles['BodyText'].spaceAfter = 12
            self.styles['BodyText'].fontName = self.arabic_font_name
    
    def _setup_bilingual_fonts(self):
        """Setup fonts for Arabic and English support using DejaVu Sans"""
        # Common paths for DejaVu Sans font
        dejavu_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",  # macOS
            "/usr/local/share/fonts/dejavu/DejaVuSans.ttf",
        ]
        
        # Try to find and register DejaVu Sans
        dejavu_font_path = None
        for path in dejavu_paths:
            if os.path.exists(path):
                dejavu_font_path = path
                break
        
        # Also try to find via fontconfig or Python packages
        if not dejavu_font_path:
            try:
                import matplotlib.font_manager as fm
                fonts = [f.name for f in fm.fontManager.ttflist]
                # Look for DejaVu Sans in system fonts
                for font_name in fonts:
                    if 'dejavu' in font_name.lower() and 'sans' in font_name.lower():
                        # Try to get the font path
                        font_paths = [f.fname for f in fm.fontManager.ttflist if 'dejavu' in f.name.lower()]
                        if font_paths:
                            dejavu_font_path = font_paths[0]
                            break
            except ImportError:
                pass
        
        # Register font if found
        if dejavu_font_path and os.path.exists(dejavu_font_path):
            try:
                pdfmetrics.registerFont(TTFont('DejaVuSans', dejavu_font_path))
                # Also try to register bold variant if available
                bold_path = dejavu_font_path.replace('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf')
                if os.path.exists(bold_path):
                    try:
                        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_path))
                        logger.info(f"Registered Arabic font (regular and bold): {dejavu_font_path}")
                    except Exception:
                        logger.info(f"Registered Arabic font (regular only): {dejavu_font_path}")
                else:
                    logger.info(f"Registered Arabic font: {dejavu_font_path}")
                self.arabic_font_name = 'DejaVuSans'
            except Exception as e:
                logger.warning(f"Failed to register DejaVu Sans font: {e}")
                self.arabic_font_name = 'Helvetica'  # Fallback
        else:
            # Fallback: try using reportlab's built-in font handling
            # Helvetica doesn't support Arabic well, but we'll log a warning
            logger.warning("DejaVu Sans font not found. Arabic text may not render correctly. Consider installing dejavu-fonts package.")
            self.arabic_font_name = 'Helvetica'  # Fallback (may have Arabic issues)
    
    def _create_table_cell(self, text: str, font_name: str = None, font_size: int = 8, alignment: str = 'LEFT') -> Any:
        """
        Create a table cell content - use Paragraph for text, plain string for simple content.
        For Arabic text, always use Paragraph with proper font and RTL direction.
        """
        if not text:
            return ""
        
        # Check if text contains Arabic characters
        has_arabic = any('\u0600' <= char <= '\u06FF' for char in text)
        
        # For Arabic text or if font is specified, use Paragraph
        if has_arabic or font_name:
            font_to_use = font_name or self.arabic_font_name
            align_enum = TA_RIGHT if has_arabic else (TA_LEFT if alignment == 'LEFT' else TA_CENTER if alignment == 'CENTER' else TA_RIGHT)
            
            # Create a style for this cell with RTL support for Arabic
            style_kwargs = {
                'name': f'TableCell_{font_to_use}_{font_size}',
                'parent': self.styles['BodyText'],
                'fontName': font_to_use,
                'fontSize': font_size,
                'alignment': align_enum,
                'leading': font_size * 1.2,  # Line spacing
                'spaceBefore': 0,
                'spaceAfter': 0
            }
            
            # DO NOT use wordWrap='RTL' when using get_display() - they conflict
            # Use get_display() for proper bidirectional text processing instead
            
            cell_style = ParagraphStyle(**style_kwargs)
            
            # Process Arabic text with proper reshaping and bidirectional text handling
            processed_text = text
            if has_arabic:
                try:
                    import arabic_reshaper
                    from bidi.algorithm import get_display
                    
                    # Step 1: Reshape Arabic characters to their proper forms based on position
                    # This is necessary for correct character rendering (isolated, initial, medial, final forms)
                    reshaped_text = arabic_reshaper.reshape(text)
                    
                    # Step 2: Apply bidirectional algorithm for proper RTL text display
                    # This ensures Arabic text flows correctly from right to left
                    processed_text = get_display(reshaped_text)
                except ImportError as e:
                    # If libraries not installed, try arabic_reshaper alone
                    try:
                        import arabic_reshaper
                        processed_text = arabic_reshaper.reshape(text)
                        logger.warning(f"python-bidi not installed: {e}. Arabic text may not display with correct direction.")
                    except ImportError:
                        # arabic-reshaper not installed, use text as-is
                        logger.warning(f"arabic-reshaper not installed: {e}. Arabic characters may not render with correct shapes.")
                        pass
            
            return Paragraph(processed_text, cell_style)
        
        # For plain text without Arabic, return as string
        return text
    
    def _normalize_cost_breakdown(self, cost_breakdown: Any, total_cost: float) -> Dict[str, Any]:
        """
        Normalize cost_breakdown to expected dictionary format.
        Handles both list format (from create_quotation tool) and dictionary format.
        Separates materials and labor items intelligently.
        """
        if isinstance(cost_breakdown, list):
            # Separate materials and labor
            material_items = []
            labor_items = []
            material_keywords = ['material', 'tile', 'paint', 'sanitaryware', 'electrical', 'plumbing', 'pipe', 'wire', 'cement', 'adhesive', 'grout', 'miscellaneous']
            labor_keywords = ['labor', 'worker', 'painter', 'tiler', 'electrician', 'plumber', 'mason', 'carpenter']
            
            for item in cost_breakdown:
                if not isinstance(item, dict):
                    continue
                    
                name = item.get("name", "").lower()
                # Check if it's labor or material
                is_labor = any(kw in name for kw in labor_keywords)
                
                item_name = item.get("name", "")
                item_quantity = item.get("quantity", 0)
                item_unit = item.get("unit", "unit")
                
                # Generate detailed description
                item_description = item.get("description", "base")
                
                item_data = {
                    "name": item_name,
                    "description": item_description,
                    "quantity": item_quantity,
                    "unit_cost": item.get("unit_price", 0),
                    "cost": item_quantity * item.get("unit_price", 0),
                    "unit": item_unit,
                    "category": item.get("category", "General")
                }
                
                if is_labor:
                    labor_items.append(item_data)
                else:
                    material_items.append(item_data)
            
            materials_total = sum(item["cost"] for item in material_items)
            labor_total = sum(item["cost"] for item in labor_items)
            
            result = {
                "currency": "EGP",
                "materials": {
                    "subtotal": materials_total,
                    "percentage": (materials_total / total_cost * 100) if total_cost > 0 else 0.0,
                    "items": material_items
                }
            }
            
            if labor_items:
                result["labor"] = {
                    "subtotal": labor_total,
                    "percentage": (labor_total / total_cost * 100) if total_cost > 0 else 0.0,
                    "items": labor_items  # Store as items for consistency
                }
            
            return result
        elif isinstance(cost_breakdown, dict):
            # Already in dictionary format, return as-is
            return cost_breakdown
        else:
            # Fallback: empty structure
            return {"currency": "EGP"}
    
    def generate_quotation_pdf(self, quotation: Quotation, quotation_data: Optional[QuotationData]) -> BytesIO:
        """Generate PDF quotation document with bilingual support"""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        story = []
        
        # Detect language
        detected_lang = detect_language(quotation.project_description)
        is_arabic = detected_lang == "ar"
        
        # Title (bilingual)
        title = "عرض سعر البناء / CONSTRUCTION QUOTATION" if is_arabic else "CONSTRUCTION QUOTATION"
        story.append(Paragraph(title, self.styles['CustomTitle']))
        story.append(Spacer(1, 0.2 * inch))
        
        # Quotation details (bilingual labels)
        id_label = "رقم العرض:" if is_arabic else "Quotation ID:"
        date_label = "التاريخ:" if is_arabic else "Date:"
        story.append(Paragraph(f"<b>{id_label}</b> {quotation.id}", self.styles['BodyText']))
        story.append(Paragraph(f"<b>{date_label}</b> {quotation.created_at.strftime('%B %d, %Y')}", self.styles['BodyText']))
        story.append(Spacer(1, 0.3 * inch))
        
        # Project summary
        summary_label = "ملخص المشروع" if is_arabic else "PROJECT SUMMARY"
        desc_label = "الوصف:" if is_arabic else "Description:"
        story.append(Paragraph(summary_label, self.styles['SectionHeading']))
        story.append(Paragraph(f"<b>{desc_label}</b> {quotation.project_description}", self.styles['BodyText']))
        
        if quotation.location:
            loc_label = "الموقع:" if is_arabic else "Location:"
            story.append(Paragraph(f"<b>{loc_label}</b> {quotation.location}", self.styles['BodyText']))
        if quotation.zip_code:
            zip_label = "الرمز البريدي:" if is_arabic else "Zip Code:"
            story.append(Paragraph(f"<b>{zip_label}</b> {quotation.zip_code}", self.styles['BodyText']))
        if quotation.project_type:
            project_type_label = quotation.project_type.value.replace('_', ' ').title()
            type_label = "نوع المشروع:" if is_arabic else "Project Type:"
            story.append(Paragraph(f"<b>{type_label}</b> {project_type_label}", self.styles['BodyText']))
        if quotation.timeline:
            timeline_label = "الجدول الزمني:" if is_arabic else "Timeline:"
            story.append(Paragraph(f"<b>{timeline_label}</b> {quotation.timeline}", self.styles['BodyText']))
        
        story.append(Spacer(1, 0.3 * inch))
        
        # Cost breakdown
        if quotation_data and quotation_data.cost_breakdown:
            breakdown_label = "تفاصيل التكلفة" if is_arabic else "COST BREAKDOWN"
            story.append(Paragraph(breakdown_label, self.styles['SectionHeading']))
            
            total_cost = quotation_data.total_cost or 0.0
            
            # Normalize cost_breakdown (handle both list and dict formats)
            cost_breakdown = self._normalize_cost_breakdown(quotation_data.cost_breakdown, total_cost)
            
            # Get currency symbol
            currency = cost_breakdown.get("currency", "EGP")
            currency_symbol = "EGP" if currency == "EGP" else "$"
            
            # Materials section
            if "materials" in cost_breakdown and cost_breakdown["materials"].get("items"):
                materials = cost_breakdown["materials"]
                mat_items = materials.get("items", [])
                
                if mat_items:
                    mat_label = "1. المواد / MATERIALS" if is_arabic else "1. MATERIALS"
                    story.append(Paragraph(mat_label, self.styles['SectionHeading']))
                    
                    # Material items table with item numbers and detailed descriptions
                    # Create headers as Paragraph objects for Arabic text
                    header_font = f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'
                    header_texts = ["#", "Item Description / الوصف", "Qty.", "Unit / الوحدة", f"Unit Price ({currency_symbol})", f"Total ({currency_symbol})"] if is_arabic else ["#", "Item Description", "Qty.", "Unit", f"Unit Price ({currency_symbol})", f"Total ({currency_symbol})"]
                    headers = [self._create_table_cell(h, header_font, 10, 'CENTER') if any('\u0600' <= char <= '\u06FF' for char in h) else h for h in header_texts]
                    mat_data = [headers]
                    
                    for idx, item in enumerate(mat_items, 1):
                        unit = item.get("unit", "unit")
                        quantity = item.get("quantity", 0)
                        # Format quantity - show decimal only if needed
                        qty_str = f"{quantity:.0f}" if quantity == int(quantity) else f"{quantity:.2f}"
                        
                        # Use detailed description if available, otherwise use name
                        description = item.get("description", item.get("name", ""))
                        
                        # Use Paragraph objects for Arabic text, plain strings for simple text
                        mat_data.append([
                            str(idx),
                            self._create_table_cell(description, self.arabic_font_name, 8, 'LEFT'),  # Description as Paragraph if Arabic
                            qty_str,  # Numbers as plain string
                            unit,  # Unit as plain string
                            f"{item.get('unit_cost', 0):,.2f}",  # Numbers as plain string
                            f"{item.get('cost', 0):,.2f}"  # Numbers as plain string
                        ])
                    
                    # Add subtotal row
                    mat_subtotal = materials.get('subtotal', 0)
                    mat_data.append([
                        "", "", "", "", "<b>Subtotal:</b>", f"<b>{mat_subtotal:,.2f}</b>"
                    ])
                    
                    # Wider description column to accommodate detailed Arabic descriptions
                    # Total page width ~8.5 inch, minus margins leaves ~7.5 inch for content
                    mat_table = Table(mat_data, colWidths=[0.3*inch, 3.5*inch, 0.5*inch, 0.6*inch, 0.9*inch, 1*inch])
                    mat_table.setStyle(TableStyle([
                        # Header row
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), header_font),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                        ('TOPPADDING', (0, 0), (-1, 0), 10),
                        # Data rows
                        ('ALIGN', (0, 1), (0, -2), 'CENTER'),  # Item #
                        ('ALIGN', (1, 1), (1, -2), 'LEFT'),    # Description
                        ('ALIGN', (2, 1), (-1, -2), 'RIGHT'),  # Numbers
                        ('FONTNAME', (0, 1), (-1, -2), self.arabic_font_name),
                        ('FONTSIZE', (0, 1), (0, -2), 8),  # Item number
                        ('FONTSIZE', (1, 1), (1, -2), 8),  # Description (smaller for longer text)
                        ('FONTSIZE', (2, 1), (-1, -2), 9),  # Other columns
                        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fa')]),
                        ('TOPPADDING', (0, 1), (-1, -2), 6),
                        ('BOTTOMPADDING', (0, 1), (-1, -2), 6),
                        # Grid
                        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#dee2e6')),
                        # Subtotal row
                        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
                        ('FONTNAME', (4, -1), (-1, -1), f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'),
                        ('FONTSIZE', (4, -1), (-1, -1), 10),
                        ('ALIGN', (4, -1), (-1, -1), 'RIGHT'),
                        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
                        ('TOPPADDING', (0, -1), (-1, -1), 8),
                        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
                    ]))
                    story.append(Spacer(1, 0.15 * inch))
                    story.append(mat_table)
                    story.append(Spacer(1, 0.25 * inch))
            
            # Labor section
            if "labor" in cost_breakdown:
                labor = cost_breakdown["labor"]
                # Check if labor has items (from normalized list format) or trades (from dict format)
                labor_items = labor.get("items", labor.get("trades", []))
                
                if labor_items:
                    lab_label = "2. العمالة / LABOR" if is_arabic else "2. LABOR"
                    story.append(Paragraph(lab_label, self.styles['SectionHeading']))
                    
                    # Labor items table - create headers as Paragraph objects for Arabic text
                    header_font = f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'
                    header_texts = ["#", "Trade / الحرفة", "Qty.", "Unit / الوحدة", f"Unit Rate ({currency_symbol})", f"Total ({currency_symbol})"] if is_arabic else ["#", "Trade", "Qty.", "Unit", f"Unit Rate ({currency_symbol})", f"Total ({currency_symbol})"]
                    headers = [self._create_table_cell(h, header_font, 10, 'CENTER') if any('\u0600' <= char <= '\u06FF' for char in h) else h for h in header_texts]
                    labor_data = [headers]
                    
                    for idx, item in enumerate(labor_items, 1):
                        # Handle both item format and trade format
                        if "trade" in item:
                            name = item.get("trade", "").replace("_", " ").title()
                            quantity = item.get("hours", item.get("quantity", 0))
                            unit = "hours"
                            unit_cost = item.get("rate", item.get("unit_cost", 0))
                            cost = item.get("cost", 0)
                        else:
                            name = item.get("name", "")
                            quantity = item.get("quantity", 0)
                            unit = item.get("unit", "unit")
                            unit_cost = item.get("unit_cost", 0)
                            cost = item.get("cost", 0)
                        
                        # Use detailed description if available
                        description = item.get("description", name)
                        
                        qty_str = f"{quantity:.0f}" if quantity == int(quantity) else f"{quantity:.2f}"
                        
                        # Use Paragraph objects for Arabic text
                        labor_data.append([
                            str(idx),
                            self._create_table_cell(description, self.arabic_font_name, 8, 'LEFT'),  # Description as Paragraph if Arabic
                            qty_str,  # Numbers as plain string
                            unit,  # Unit as plain string
                            f"{unit_cost:,.2f}",  # Numbers as plain string
                            f"{cost:,.2f}"  # Numbers as plain string
                        ])
                    
                    # Add subtotal row
                    labor_subtotal = labor.get('subtotal', 0)
                    labor_data.append([
                        "", "", "", "", "<b>Subtotal:</b>", f"<b>{labor_subtotal:,.2f}</b>"
                    ])
                    
                    # Wider description column to accommodate detailed Arabic descriptions
                    # Total page width ~8.5 inch, minus margins leaves ~7.5 inch for content
                    labor_table = Table(labor_data, colWidths=[0.3*inch, 3.5*inch, 0.5*inch, 0.6*inch, 0.9*inch, 1*inch])
                    labor_table.setStyle(TableStyle([
                        # Header row
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                        ('TOPPADDING', (0, 0), (-1, 0), 10),
                        # Data rows
                        ('ALIGN', (0, 1), (0, -2), 'CENTER'),  # Item #
                        ('ALIGN', (1, 1), (1, -2), 'LEFT'),    # Description
                        ('ALIGN', (2, 1), (-1, -2), 'RIGHT'),  # Numbers
                        ('FONTNAME', (0, 1), (-1, -2), self.arabic_font_name),
                        ('FONTSIZE', (0, 1), (0, -2), 8),  # Item number
                        ('FONTSIZE', (1, 1), (1, -2), 8),  # Description (smaller for longer text)
                        ('FONTSIZE', (2, 1), (-1, -2), 9),  # Other columns
                        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fa')]),
                        ('TOPPADDING', (0, 1), (-1, -2), 6),
                        ('BOTTOMPADDING', (0, 1), (-1, -2), 6),
                        # Grid
                        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#dee2e6')),
                        # Subtotal row
                        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
                        ('FONTNAME', (4, -1), (-1, -1), f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'),
                        ('FONTSIZE', (4, -1), (-1, -1), 10),
                        ('ALIGN', (4, -1), (-1, -1), 'RIGHT'),
                        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
                        ('TOPPADDING', (0, -1), (-1, -1), 8),
                        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
                    ]))
                    story.append(Spacer(1, 0.15 * inch))
                    story.append(labor_table)
                    story.append(Spacer(1, 0.25 * inch))
            
            story.append(Spacer(1, 0.2 * inch))
            
            # Summary section
            summary_label = "3. ملخص التكلفة / COST SUMMARY" if is_arabic else "3. COST SUMMARY"
            story.append(Paragraph(summary_label, self.styles['SectionHeading']))
            
            # Build summary table
            summary_data = []
            
            # Materials subtotal - use Paragraph for Arabic labels
            if "materials" in cost_breakdown:
                mat_sub = cost_breakdown["materials"].get("subtotal", 0)
                mat_pct = cost_breakdown["materials"].get("percentage", 0)
                mat_label = self._create_table_cell("Materials / المواد", self.arabic_font_name, 10, 'LEFT')
                summary_data.append([mat_label, f"{currency_symbol} {mat_sub:,.2f}", f"{mat_pct:.1f}%"])
            
            # Labor subtotal - use Paragraph for Arabic labels
            if "labor" in cost_breakdown:
                lab_sub = cost_breakdown["labor"].get("subtotal", 0)
                lab_pct = cost_breakdown["labor"].get("percentage", 0)
                lab_label = self._create_table_cell("Labor / العمالة", self.arabic_font_name, 10, 'LEFT')
                summary_data.append([lab_label, f"{currency_symbol} {lab_sub:,.2f}", f"{lab_pct:.1f}%"])
            
            # Other costs
            if "permits_and_fees" in cost_breakdown:
                permits = cost_breakdown["permits_and_fees"]
                permits_sub = permits.get('subtotal', 0)
                permits_pct = permits.get('percentage', 0)
                summary_data.append(["Permits & Fees / التصاريح والرسوم", f"{currency_symbol} {permits_sub:,.2f}", f"{permits_pct:.1f}%"])
            
            if "contingency" in cost_breakdown:
                contingency = cost_breakdown["contingency"]
                cont_sub = contingency.get('subtotal', 0)
                cont_pct = contingency.get('percentage', 0)
                summary_data.append([f"Contingency ({contingency.get('percentage', 0):.0f}%) / الطوارئ", f"{currency_symbol} {cont_sub:,.2f}", f"{cont_pct:.1f}%"])
            
            if "markup" in cost_breakdown:
                markup = cost_breakdown["markup"]
                markup_sub = markup.get('subtotal', 0)
                markup_pct = markup.get('percentage', 0)
                summary_data.append([f"Markup ({markup.get('percentage', 0):.0f}%) / هامش الربح", f"{currency_symbol} {markup_sub:,.2f}", f"{markup_pct:.1f}%"])
            
            # Add headers and total - use Paragraph for Arabic headers
            header_font = f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'
            header_texts = ["Category / الفئة", f"Amount ({currency_symbol})", "Percentage / النسبة"] if is_arabic else ["Category", f"Amount ({currency_symbol})", "Percentage"]
            summary_headers = [self._create_table_cell(h, header_font, 11, 'CENTER') if any('\u0600' <= char <= '\u06FF' for char in h) else h for h in header_texts]
            summary_table_data = [summary_headers] + summary_data
            total_label = self._create_table_cell("TOTAL / الإجمالي", f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold', 12, 'CENTER') if is_arabic else "<b>TOTAL</b>"
            summary_table_data.append([total_label, f"<b>{currency_symbol} {total_cost:,.2f}</b>", "<b>100.0%</b>"])
            
            summary_table = Table(summary_table_data, colWidths=[3.5*inch, 1.5*inch, 1.2*inch])
            summary_table.setStyle(TableStyle([
                # Header row
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                # Data rows
                ('ALIGN', (0, 1), (0, -2), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -2), 'RIGHT'),
                ('FONTNAME', (0, 1), (-1, -2), self.arabic_font_name),
                ('FONTSIZE', (0, 1), (-1, -2), 10),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fa')]),
                ('TOPPADDING', (0, 1), (-1, -2), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -2), 8),
                # Grid
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#dee2e6')),
                # Total row
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#0070f3')),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
                ('FONTNAME', (0, -1), (-1, -1), f'{self.arabic_font_name}-Bold' if self.arabic_font_name == 'DejaVuSans' else 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 12),
                ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
                ('LINEABOVE', (0, -1), (-1, -1), 2, colors.white),
                ('TOPPADDING', (0, -1), (-1, -1), 12),
                ('BOTTOMPADDING', (0, -1), (-1, -1), 12),
            ]))
            story.append(Spacer(1, 0.15 * inch))
            story.append(summary_table)
            story.append(Spacer(1, 0.3 * inch))
            
            # Confidence interval
            if quotation_data and quotation_data.extracted_data:
                confidence = quotation_data.confidence_score or 0.5
                story.append(Spacer(1, 0.2 * inch))
                confidence_style = ParagraphStyle(
                    name='Confidence',
                    parent=self.styles['BodyText'],
                    fontSize=10,
                    textColor=colors.grey,
                    alignment=TA_RIGHT
                )
                story.append(Paragraph(f"<i>Confidence Score: {confidence:.0%}</i>", confidence_style))
        
        story.append(PageBreak())
        
        # Terms and conditions - Egyptian market specific
        terms_label = "الشروط والأحكام / TERMS AND CONDITIONS" if is_arabic else "TERMS AND CONDITIONS"
        story.append(Paragraph(terms_label, self.styles['SectionHeading']))
        
        if is_arabic:
            terms = [
                "صالحية العرض: هذا العرض صالح لمدة 30 يوماً من تاريخ الإصدار.",
                "الأسعار: جميع الأسعار تقديرية وقابلة للتغيير حسب المواصفات النهائية للمشروع وظروف السوق.",
                "التكاليف النهائية: قد تختلف التكاليف النهائية حسب ظروف الموقع وتوفر المواد وتقلبات السوق.",
                "التصاريح: هذا العرض لا يشمل التصاريح الرسمية ما لم يتم ذكره صراحة.",
                "شروط الدفع: دفعة مقدمة 30% عند القبول، والمتبقي عند الانتهاء من الأعمال.",
                "التعديلات: أي تغييرات في نطاق المشروع قد تؤدي إلى تكاليف إضافية.",
                "الضمان: ضمان جميع الأعمال لمدة سنة واحدة من تاريخ التسليم النهائي.",
                "المعايير والمواصفات: جميع الأعمال تتم طبقاً للمواصفات الفنية وأصول الصناعة والكود المصري للبناء (ECP) وقانون البناء الموحد رقم 119 لسنة 2008.",
                "الإشراف: يتطلب المشروع إشراف مهندس مرخص من نقابة المهندسين (قانون رقم 66 لسنة 1974).",
                "الفحص والموافقة: جميع الأعمال تخضع للفحص من قبل المهندس المشرف والجهات المختصة قبل التسليم النهائي.",
                "التسليم: يتم التسليم مع شهادة الإنجاز من المهندس المشرف وشهادة صلاحية السكن من الجهة المختصة.",
            ]
        else:
            terms = [
                "Validity: This quotation is valid for 30 days from the date of issue.",
                "Prices: All prices are estimates and subject to change based on final project specifications and market conditions.",
                "Final Costs: Final costs may vary based on site conditions, material availability, and market fluctuations.",
                "Permits: This quotation does not include official permits unless specifically stated.",
                "Payment Terms: 30% deposit upon acceptance, balance due upon completion of works.",
                "Modifications: Any changes to the project scope may result in additional costs.",
                "Warranty: All works are warranted for one year from the date of final delivery.",
                "Standards & Specifications: All works are executed according to technical specifications, industry standards, Egyptian Building Code (ECP), and Unified Building Law No. 119 of 2008.",
                "Supervision: The project requires supervision by a licensed engineer from the Engineers' Syndicate (Law No. 66 of 1974).",
                "Inspection & Approval: All works are subject to inspection by the supervising engineer and relevant authorities before final delivery.",
                "Delivery: Delivery includes completion certificate from the supervising engineer and occupancy certificate from relevant authorities.",
            ]
        
        for term in terms:
            story.append(Paragraph(f"• {term}", self.styles['BodyText']))
        
        story.append(Spacer(1, 0.3 * inch))
        footer_style = ParagraphStyle(
            name='Footer',
            parent=self.styles['BodyText'],
            fontSize=9,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        story.append(Paragraph(
            "<i>This quotation was generated by AI Construction Agent. Please review all details carefully.</i>",
            footer_style
        ))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer
