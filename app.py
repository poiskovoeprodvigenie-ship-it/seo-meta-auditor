"""Flask-интерфейс SEO Meta Auditor."""
import io

import requests
from flask import Flask, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import auditor

app = Flask(__name__)
LAST_RESULT = {"rows": []}  # MVP: результат последней проверки хранится в памяти

FILLS = {"critical": "F8D7DA", "warning": "FFF3CD", "info": "E2E3E5", "ok": "D4EDDA"}


@app.route("/", methods=["GET", "POST"])
def index():
    rows, error, summary = [], None, None
    if request.method == "POST":
        try:
            sitemap = request.form.get("sitemap", "").strip()
            if sitemap:
                urls = auditor.urls_from_sitemap(sitemap)
            else:
                urls = auditor.parse_urls(request.form.get("urls", ""))
            if not urls:
                error = "Добавьте хотя бы один URL или адрес sitemap.xml"
            else:
                rows = auditor.run_audit(urls)
                LAST_RESULT["rows"] = rows
                summary = {lvl: sum(r["level"] == lvl for r in rows)
                           for lvl in ("critical", "warning", "info", "ok")}
                summary["total"] = len(rows)
        except requests.RequestException as exc:
            error = f"Не удалось загрузить sitemap: {type(exc).__name__}"
    return render_template("index.html", rows=rows, error=error, summary=summary,
                           max_urls=auditor.MAX_URLS)


@app.route("/export")
def export():
    rows = LAST_RESULT["rows"]
    if not rows:
        return "Сначала запустите проверку", 400
    wb = Workbook()
    ws = wb.active
    ws.title = "SEO аудит"
    head = ["URL", "Код", "Title", "Длина title", "Description", "Длина desc",
            "H1", "Кол-во H1", "Canonical", "Проблемы"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r["url"], r["status"], r["title"], len(r["title"]), r["description"],
                   len(r["description"]), r["h1"], r["h1_count"], r["canonical"],
                   "; ".join(msg for _, msg in r["issues"])])
        fill = PatternFill("solid", fgColor=FILLS[r["level"]])
        ws.cell(row=ws.max_row, column=10).fill = fill
    for i, width in enumerate([45, 7, 45, 8, 55, 8, 35, 8, 40, 50], 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="seo_audit.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    app.run(debug=False, port=5000)
