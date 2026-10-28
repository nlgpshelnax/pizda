"""Verify browser-downloaded plans against the actual confirmation screen."""
import json
from pathlib import Path
import pdfplumber

folder = Path('test-results/pdf')
reports = json.loads((folder / 'ui-data.json').read_text(encoding='utf-8'))
for report in reports:
    with pdfplumber.open(folder / f"{report['name']}.pdf") as pdf:
        assert len(pdf.pages) == 1, 'Expected one page'
        page = pdf.pages[0]
        assert abs(page.width - 595.28) < 1 and abs(page.height - 841.89) < 1, 'Expected A4'
        text = page.extract_text()
        compact = ''.join(text.split())
        assert report['total'] in compact, (report['total'], text)
        assert report['date'] in text, text
        assert report['guests'] in text, text
        assert 'О!динзапрос' in compact
        for part in ['Демонстрационный план','Маршрут','Проживание','Стоимость','Важная информация','Перед путешествием']:
            assert part in text, part
        for char in page.chars:
            assert char['x0'] >= 0 and char['x1'] <= page.width and char['top'] >= 0 and char['bottom'] <= page.height, char
        print(f"PASS {report['name']}: A4, one page, date, travellers, UI total, headings and character bounds")
