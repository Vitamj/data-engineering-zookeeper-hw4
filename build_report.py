import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "report/report.pdf"
DATA = json.loads((ROOT / "results/experiment.json").read_text(encoding="utf-8"))
LOG = (ROOT / "logs/experiment.log").read_text(encoding="utf-8").splitlines()
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
pdfmetrics.registerFont(TTFont("Arial", FONT))
pdfmetrics.registerFont(TTFont("Arial-Bold", FONT_BOLD))

INK = colors.HexColor("#34283D")
MUTED = colors.HexColor("#766B7D")
ROSE = colors.HexColor("#F4C7D8")
PALE = colors.HexColor("#FBF1F6")
LILAC = colors.HexColor("#EEE9FA")
GREEN = colors.HexColor("#417D66")
RED = colors.HexColor("#A74962")
WHITE = colors.white

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", fontName="Arial-Bold", fontSize=26, leading=32, textColor=INK, alignment=TA_CENTER, spaceAfter=7 * mm))
styles.add(ParagraphStyle(name="CoverSub", fontName="Arial", fontSize=13, leading=19, textColor=MUTED, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="H1x", fontName="Arial-Bold", fontSize=18, leading=22, textColor=INK, spaceBefore=2 * mm, spaceAfter=4 * mm))
styles.add(ParagraphStyle(name="H2x", fontName="Arial-Bold", fontSize=12, leading=16, textColor=INK, spaceBefore=3 * mm, spaceAfter=2 * mm))
styles.add(ParagraphStyle(name="Bodyx", fontName="Arial", fontSize=9.5, leading=14, textColor=INK, spaceAfter=2.2 * mm))
styles.add(ParagraphStyle(name="Smallx", fontName="Arial", fontSize=8, leading=11, textColor=MUTED))
styles.add(ParagraphStyle(name="Logx", fontName="Arial", fontSize=7.4, leading=10, textColor=INK))


def para(text, style="Bodyx"):
    return Paragraph(text, styles[style])


def cell(text, header=False):
    return para(str(text), "H2x" if header else "Bodyx")


def page(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(PALE)
    canvas.rect(0, h - 7 * mm, w, 7 * mm, stroke=0, fill=1)
    if doc.page > 1:
        canvas.setStrokeColor(ROSE)
        canvas.line(18 * mm, 15 * mm, w - 18 * mm, 15 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Arial", 8)
        canvas.drawString(18 * mm, 10 * mm, "Apache ZooKeeper · j3313")
        canvas.drawRightString(w - 18 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


def table(rows, widths, header=True):
    formatted = [[cell(v, header and i == 0) for v in row] for i, row in enumerate(rows)]
    t = Table(formatted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#E3D9E5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), LILAC))
        commands.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE]))
    else:
        commands.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, PALE]))
    t.setStyle(TableStyle(commands))
    return t


stories = []
stories += [Spacer(1, 35 * mm), para("Apache ZooKeeper", "CoverTitle"), para("Отказоустойчивый ансамбль и восстановление расчёта", "CoverSub"), Spacer(1, 15 * mm)]
stories += [HRFlowable(width="54%", thickness=2, color=ROSE, hAlign="CENTER"), Spacer(1, 13 * mm)]
stories += [para("Практическая работа", "CoverSub"), Spacer(1, 12 * mm)]
stories += [table([["Студентка", "Группа", "ИСУ"], [DATA["student"], DATA["group"], DATA["isu"]]], [82 * mm, 33 * mm, 28 * mm]), Spacer(1, 10 * mm)]
stories += [para("Вариант 7 · разработчик на Go", "CoverSub"), Spacer(1, 56 * mm), para("ZooKeeper 3.9.6 · Java 17 · таймаут сессии 10 секунд", "Smallx"), PageBreak()]

stories += [para("1. Ансамбль и кворум", "H1x"), para("Три процесса ZooKeeper 3.9.6 запущены на одной машине. У каждого собственные dataDir и myid. В конфигурациях совпадает список server.1–server.3; клиентские порты 2181–2183, порты кворума и выборов выделены отдельно для каждого процесса.")]
stories += [para("Проверки состояния", "H2x")]
stories += [table([["Сценарий", "Наблюдение"], ["Все три процесса", "2 followers и 1 leader"], ["Остановлен server 1", "Два сервера сохранили кворум; запись через клиента успешна"], ["Остановлены server 1 и 2", "server 3 остался без большинства; клиентская операция не прошла"], ["После перезапуска", "Все три сервера вернулись в роли leader/follower"], ["Эфемерный znode", "Узел существовал в сессии; после закрытия сессии exists=false"]], [49 * mm, 94 * mm])]
stories += [Spacer(1, 5 * mm), para("Временные порты на localhost нужны потому, что три экземпляра работают на одной машине. В реальном ансамбле каждому серверу назначается отдельный узел сети, и тогда порты кворума можно повторять.", "Smallx"), PageBreak()]

stories += [para("2. Координаторы и чекпоинт", "H1x"), para("Два процесса Python используют KazooClient с session timeout 10 секунд. Они создают ephemeral sequential znodes под /coordinators. Координатор с наименьшим порядковым номером становится лидером; второй ждёт удаления предыдущего узла. Смена эпохи хранится в /control/epoch.")]
stories += [para("Расчёт и восстановление", "H2x"), para("Набор состоит из 124 вакансий Go. Каждая вакансия обрабатывается один раз: навыки нормализуются и из них формируются пары. После каждого чанка частичные счётчики атомарно сохраняются в checkpoint.json. Лидера приостанавливали на 40 секунд после завершения первых чанков. ZooKeeper удалил его ephemeral znode после истечения сессии, резервный координатор стал лидером и обработал только отсутствующие чанки.")]
stories += [para("Время смены лидера", "H2x")]
run_rows = [["Режим", "Смена лидера, с", "Версия указателя", "Пик RSS A / B, MiB", "Сверка с ДЗ №3"]]
for run in DATA["runs"]:
    mode = run["mode"]
    measurements = []
    for worker in ("coord-A", "coord-B"):
        text = (ROOT / f"logs/{mode}-{worker}.log").read_text(encoding="utf-8")
        match = re.search(r"PROCESS_METRICS .*peak_rss_mb=([0-9.]+)", text)
        measurements.append(match.group(1) if match else "-")
    run_rows.append(["С эпохой" if mode == "fenced" else "Без эпохи", f"{run['failover_seconds']:.3f}", str(run["pointer_version"]), " / ".join(measurements), "Да" if run["result_matches_hw3"] else "Нет"])
stories += [table(run_rows, [34 * mm, 32 * mm, 30 * mm, 39 * mm, 27 * mm])]
stories += [Spacer(1, 4 * mm), para("Время измерено локальными монотонными часами от отправки SIGSTOP лидеру до записи BECAME_LEADER в журнал резервного процесса. Это включает обнаружение истечения ZooKeeper-сессии, поэтому измерение показывает поведение всего failover-сценария, а не только внутреннюю фазу голосования.", "Smallx"), PageBreak()]

stories += [para("3. Проверка результата и эпохи", "H1x"), para("Эталон — полный файл пар из расчёта ДЗ № 3 для варианта Go. Резервный координатор восстановил те же пары после чекпоинта. Пары сравниваются по ключам и числам, а не только по общей сумме.")]
stories += [table([["Контроль", "ДЗ № 3", "ZooKeeper ДЗ", "Результат"], ["Различных пар", "1 008", "1 008", "Совпало"], ["Вхождений пар", "2 382", "2 382", "Совпало"]], [50 * mm, 34 * mm, 38 * mm, 31 * mm])]
stories += [para("Два сценария публикации", "H2x"), para("Без защиты получатель принял запись координатора B, а затем позднюю запись координатора A со старой эпохой: указатель результата перешёл на версию 2. Это демонстрирует, что ZooKeeper может уже исключить процесс из лидерства, но не способен отменить внешнюю запись, сделанную после длительной паузы.")]
stories += [para("При FENCING=1 получатель сравнил переданную эпоху с активной в одной SQLite-транзакции вместе с обновлением указателя. После захвата лидерства B активной стала эпоха B. Возобновившийся A получил BadVersionError; указатель остался на единственной принятой версии 1.")]
stories += [para("Наблюдаемые строки журналов", "H2x")]
snippets = []
for line in LOG:
    if any(key in line for key in ("ENSEMBLE_INITIAL", "ONE_SERVER_DOWN", "TWO_SERVERS_DOWN", "EPHEMERAL_AFTER", "UNFENCED FINAL", "FENCED FINAL", "FAILOVER_SECONDS")):
        snippets.append(para(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), "Logx"))
stories += [Table([[s] for s in snippets], colWidths=[151 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.5, ROSE), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])), PageBreak()]

stories += [para("4. Выводы", "H1x"), para("Почему три сервера, а не два или четыре?", "H2x"), para("ZooKeeper подтверждает запись большинством. При двух серверах отказ одного оставляет только половину ансамбля: большинство недоступно. Три сервера сохраняют два голоса после одного отказа. Четыре также переживают один отказ, но не два: оставшиеся два голоса не составляют большинства. Поэтому три узла — минимальный нечётный размер, который переживает отказ одного узла.")]
stories += [para("Почему эпоху проверяет получатель записи, а не ZooKeeper?", "H2x"), para("ZooKeeper управляет членством координаторов и выдаёт им эпохи, но расчёт записывает результат в отдельное хранилище. Оно не участвует в протоколе ZooKeeper. После паузы старый процесс может продолжить исполняться и отправить старый результат, хотя его сессия уже истекла. Получатель должен атомарно сравнить эпоху с текущей и отклонить устаревшую запись. Проверка только в координаторе не защищает от процесса, который проснулся после долгой паузы.")]
stories += [para("Ограничение демонстрации", "H2x"), para("Получатель результата представлен SQLite-файлом на общей машине. Это позволяет проверить атомарное сравнение эпохи и версии указателя. В распределённой системе та же проверка должна выполняться в фактическом получателе результата — например, транзакцией в целевой БД или условной записью в хранилище.")]
stories += [para("Файлы доказательств", "H2x"), para("Конфигурации серверов находятся в config/, команды управления — в scripts/, журналы ZooKeeper и координаторов — в logs/, итоговые указатели и сводка — в results/. Полный эталон пар ДЗ № 3 приложен в data/hw3_pair_counts.json.")]

doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm, topMargin=19 * mm, bottomMargin=22 * mm, title="Apache ZooKeeper - отказоустойчивость", author=DATA["student"])
doc.build(stories, onFirstPage=page, onLaterPages=page)
print(OUT)
