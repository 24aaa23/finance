"""Replace the main draw.io page with the connected flow and recovery loops."""
from pathlib import Path
import math
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont


def update_main_diagram():
    folder = Path(__file__).resolve().parent
    path = folder / 'Improvement7_Workflow.drawio'
    tree = ET.parse(path)
    page = tree.getroot().find('diagram')
    page.clear()
    page.set('name', 'Main_workflow')
    model = ET.SubElement(page, 'mxGraphModel', page='1', pageWidth='1900', pageHeight='2980')
    root = ET.SubElement(model, 'root')
    ET.SubElement(root, 'mxCell', id='0')
    ET.SubElement(root, 'mxCell', id='1', parent='0')
    canvas = Image.new('RGB', (1900, 2980), 'white')
    pen = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 29)
    title_font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 40)
    colors = {'model': '#E3EFF9', 'local': '#E5F2EA', 'repair': '#FFF1CE', 'data': '#F1F2F4'}
    nodes = {}
    edges = []

    # This frame encloses all five per-branch operators, not just Query_Spec.
    group = ET.SubElement(root, 'mxCell', id='branch_frame', vertex='1', parent='1',
                          style='rounded=0;fillColor=none;strokeColor=#71808D;dashed=1;')
    ET.SubElement(group, 'mxGeometry', x='605', y='897', width='590', height='965', **{'as': 'geometry'})
    pen.rectangle((605, 897, 1195, 1862), outline='#71808D', width=2)
    caption = 'PER SOURCE BRANCH'
    pen.text((628, 901), caption, font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 22), fill='#172126')
    group_label = ET.SubElement(root, 'mxCell', id='branch_label', value=caption, vertex='1', parent='1',
                               style='text;html=0;align=left;fontSize=22;fontColor=#172126;')
    ET.SubElement(group_label, 'mxGeometry', x='628', y='901', width='265', height='28', **{'as': 'geometry'})

    def node(ident, x, y, w, h, label, kind):
        nodes[ident] = (x, y, w, h, label, kind)
        cell = ET.SubElement(root, 'mxCell', id=ident, value=label, parent='1', vertex='1',
            style=f'rounded=1;arcSize=5;whiteSpace=wrap;html=0;fontSize=29;spacing=10;fillColor={colors[kind]};strokeColor=#71808D;fontColor=#172126;')
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), **{'as': 'geometry'})

    def edge(a, b, points, recovery=False):
        edges.append((a, b, points, recovery))

    stages = [
        ('domain', 'Domain Knowledge - shared startup\nDocs + YAML + physical schema\nCache hit 0; cache miss 1-3 calls', 'model'),
        ('qu', 'Query Understanding (default on)\n1 call per attempt; up to 3\nValid contract -> continue', 'model'),
        ('retrieve', 'Retrieve\nSelect source tables\n1 LLM call per invocation', 'model'),
        ('decompose', 'Decompose\nPlan B source branches\n1 LLM call per invocation', 'model'),
        ('qs', 'Query_Spec for each branch\n1 LLM call per attempt\nUp to 3 branch validation attempts', 'model'),
        ('generate', 'Generate SQL\nLocal renderer succeeds: 0 calls\nOtherwise: 1 LLM call', 'model'),
        ('pre', 'Pre_Scan_Validate\n0 calls; default 3 checks per loop\nLimit configurable in environment', 'local'),
        ('scan', 'Scan - read-only SQLite\n0 calls; default 3 attempts per loop\nLimit configurable in environment', 'local'),
        ('process', 'Processing_Spec - preserve rows\n0 calls; up to 3 local attempts\nAll branches feed Final_Spec', 'local'),
        ('final', 'Final_Spec\nBuild the calculation plan\n1 LLM call per attempt', 'model'),
        ('execute', 'Compile and execute Final_Spec\nJoins, filters, sums, math, sorting\nLocal work inside Final_Spec stage', 'local'),
        ('validate', 'Validate + Explain\nLocal / structured path: 0 calls\nOptional model path: up to 1 each', 'model'),
        ('report', 'Save answer or execution error\nRaw report and diagnostics\nContinue with the next question', 'data'),
        ('grader', 'Separate grader\nCompare answer with ground truth\nCalls excluded from pipeline average', 'data'),
    ]
    for i, (ident, label, kind) in enumerate(stages):
        node(ident, 620, 150 + i * 195, 560, 135, label, kind)
        if i:
            previous = stages[i - 1][0]
            y = nodes[previous][1]
            edge(previous, ident, [(900, y + 135), (900, y + 195)])

    node('qu_retry', 20, 345, 470, 155,
         'Invalid interpretation\nAttempts remain: feedback + retry\nMaximum 3 attempts\nAfter attempt 3: fallback below', 'repair')
    edge('qu', 'qu_retry', [(620, 390), (490, 390)], True)
    edge('qu_retry', 'qu', [(490, 430), (545, 430), (545, 320), (900, 320), (900, 345)], True)
    node('qu_fallback', 20, 540, 470, 135,
         'Still invalid after 3 attempts\nReturn empty contract {}\nOriginal question -> Retrieve', 'repair')
    edge('qu_retry', 'qu_fallback', [(255, 500), (255, 540)], True)
    edge('qu_fallback', 'retrieve', [(490, 607), (620, 607)], True)
    node('decompose_retry', 20, 730, 470, 160,
         'Invalid decomposition OR\nQuery_Spec retries exhausted\nPasses left: Decompose again\nMax 3 passes; exhausted: error', 'repair')
    edge('decompose', 'decompose_retry', [(620, 780), (490, 780)], True)
    edge('decompose_retry', 'decompose', [(490, 830), (550, 830), (550, 710), (900, 710), (900, 735)], True)
    node('qs_retry', 20, 930, 470, 135,
         'Invalid Query_Spec\nAttempts remain: feedback + retry\n3 failures: replan upstream', 'repair')
    edge('qs', 'qs_retry', [(620, 980), (490, 980)], True)
    edge('qs_retry', 'qs', [(490, 1020), (545, 1020), (545, 885), (900, 885), (900, 930)], True)
    edge('qs_retry', 'decompose_retry', [(255, 930), (255, 890)], True)
    node('pre_retry', 20, 1320, 470, 145,
         'Pre-scan fails; attempts remain\nRegenerate SQL\nLocal 0 calls or LLM fallback 1\nNo attempts left: error row', 'repair')
    edge('pre', 'pre_retry', [(620, 1387), (490, 1387)], True)
    edge('pre_retry', 'generate', [(255, 1320), (255, 1192), (620, 1192)], True)
    node('scan_retry', 20, 1515, 470, 295,
         'Scan fails; attempts remain\nNo SQL: Generate (0 or 1)\nUnknown fields: Query_Spec (1)\nValid: Generate; invalid: Refine\nOther SQL error: Refine (1)\nSimilar timeout SQL: Generate too\nThen pre-check and Scan again\nNo attempts left: error row', 'repair')
    edge('scan', 'scan_retry', [(620, 1560), (490, 1560)], True)
    edge('scan_retry', 'pre', [(490, 1650), (550, 1650), (550, 1420), (620, 1420)], True)
    edge('scan_retry', 'generate', [(20, 1690), (5, 1690), (5, 1140), (620, 1140)], True)
    node('final_retry', 20, 2100, 470, 185,
         'Invalid plan or execution error\nAttempts left: Final_Spec again\n1 LLM call per new plan\nUp to 4 attempts per execution\nNo attempts left: error row', 'repair')
    edge('final', 'final_retry', [(620, 1940), (520, 1940), (520, 2140), (490, 2140)], True)
    edge('execute', 'final_retry', [(620, 2170), (490, 2170)], True)
    edge('final_retry', 'final', [(255, 2100), (255, 1972), (620, 1972)], True)

    node('consult', 1300, 750, 480, 220,
         'OPTIONAL ADVICE (default off)\nRequests from Decompose,\nQuery_Spec or Final_Spec\nDomain: 1 LLM call\nQuery Understanding: 1-3\nShared limit: 5 requests', 'repair')
    node('consult_return', 1300, 1020, 480, 165,
         'UNCHANGED interpretation\nRepeat ONLY requesting stage\nDecompose, Query_Spec OR\nFinal_Spec - not all three', 'repair')
    node('consult_changed', 1300, 1270, 480, 180,
         'CHANGED interpretation\nPasses left: Retrieve again\nThen restart Decompose\nNo passes left: error row', 'repair')
    edge('decompose', 'consult', [(1180, 785), (1240, 785), (1240, 805), (1300, 805)], True)
    edge('qs', 'consult', [(1180, 970), (1220, 970), (1220, 920), (1300, 920)], True)
    edge('consult', 'consult_return', [(1540, 970), (1540, 1020)], True)
    edge('consult_return', 'decompose', [(1300, 1090), (1280, 1090), (1280, 850), (1180, 850)], True)
    edge('consult_return', 'qs', [(1300, 1090), (1280, 1090), (1280, 1050), (1180, 1050)], True)
    edge('consult_return', 'final', [(1300, 1090), (1280, 1090), (1280, 2025), (1180, 2025)], True)
    edge('consult', 'consult_changed', [(1780, 890), (1830, 890), (1830, 1360), (1780, 1360)], True)
    edge('consult_changed', 'retrieve', [(1780, 1390), (1850, 1390), (1850, 607), (1180, 607)], True)
    edge('final', 'consult', [(1180, 1945), (1260, 1945), (1260, 860), (1300, 860)], True)
    node('upstream', 1300, 2000, 480, 200,
         'Missing required source data\nRequest upstream retrieval repair\nDecompose -> rerun branches\nUp to 3 decomposition passes\nAdditional model calls each pass', 'repair')
    edge('final', 'upstream', [(1180, 2005), (1230, 2005), (1230, 2080), (1300, 2080)], True)
    edge('upstream', 'decompose', [(1780, 2080), (1795, 2080), (1795, 690), (1200, 690), (1200, 765), (1180, 765)], True)
    node('limits', 1300, 2350, 480, 215,
         'RETRY BUDGETS ARE LOCAL\nThey can nest or restart stages.\nThere is no 3-call total limit.\nExhausted repair -> error row.\nQuota or startup failures\ncan stop the batch.', 'data')

    node('startup_note', 1300, 150, 480, 225,
         'STARTUP AND QUESTION INPUT\nCache reused across questions.\nInvalid domain pack: startup stops.\nQuestion is preprocessed first.\nUnderstanding off: 0 for that agent;\nRetrieve still makes its own call.', 'data')
    node('consult_limits', 1300, 1530, 480, 210,
         'CONSULTATION EXCEPTIONS\nInvalid request or budget spent:\nreturn a plan contract error.\nOther unavailable advice: reask.\nQuota / transient error: propagate.\nReasks add model calls.', 'data')
    node('validation_note', 1300, 2630, 480, 215,
         'VALIDATION DOES NOT REPAIR\nExecution check fails: error row.\nOptional model review rejection:\nrecord verdict, retain result.\nSuccessful report saves actual\nexecuted data, not LLM prose.', 'data')
    node('error_note', 20, 2350, 470, 255,
         'ERROR EXIT (not forward flow)\nUnrepaired stages skip ahead\nto report the failed question.\nProcessing failure: error row.\nUnderstanding API exceptions\nneed not reach its fallback.\nEmpty Scan results can be valid.', 'data')
    edge('error_note', 'report', [(490, 2520), (550, 2520), (550, 2557), (620, 2557)], True)

    for index, (a, b, points, recovery) in enumerate(edges):
        color = '#AA7222' if recovery else '#55616B'
        pen.line(points, fill=color, width=4)
        x, y = points[-1]
        px, py = points[-2]
        angle = math.atan2(y - py, x - px)
        pen.polygon([(x, y), (x - 15 * math.cos(angle - .5), y - 15 * math.sin(angle - .5)),
                     (x - 15 * math.cos(angle + .5), y - 15 * math.sin(angle + .5))], fill=color)
        ax, ay, aw, ah, *_ = nodes[a]
        bx, by, bw, bh, *_ = nodes[b]
        start, finish = points[0], points[-1]
        style = (f'edgeStyle=segmentEdgeStyle;rounded=0;endArrow=block;strokeColor={color};strokeWidth=3;'
                 f'exitX={(start[0]-ax)/aw};exitY={(start[1]-ay)/ah};entryX={(finish[0]-bx)/bw};entryY={(finish[1]-by)/bh};')
        cell = ET.SubElement(root, 'mxCell', id=f'e{index}', edge='1', parent='1', source=a, target=b, style=style)
        geometry = ET.SubElement(cell, 'mxGeometry', relative='1', **{'as': 'geometry'})
        array = ET.SubElement(geometry, 'Array', **{'as': 'points'})
        for x, y in points[1:-1]:
            ET.SubElement(array, 'mxPoint', x=str(x), y=str(y))
    for ident, (x, y, w, h, text, kind) in nodes.items():
        bounds = pen.multiline_textbbox((0, 0), text, font=font, spacing=7, align='center')
        assert bounds[2] < w - 16 and bounds[3] - bounds[1] < h - 12, (ident, bounds, w, h)
        pen.rounded_rectangle((x, y, x + w, y + h), radius=8, fill=colors[kind], outline='#71808D', width=2)
        pen.multiline_text((x + w / 2, y + h / 2), text, font=font, spacing=7, fill='#172126', anchor='mm', align='center')
    texts = [
        (20, 20, 'Improvement 7 workflow with self healing', True),
        (20, 82, 'Blue: can call an LLM   Green: local execution   Yellow: conditional repair   Gold arrows: recovery', False),
        (20, 2865, 'Calls are per underlying model invocation; consultation reasks add calls within an operator attempt.', False),
        (20, 2910, 'Historical average: 7.26 per question over the original 1,000 attempts; startup, later reruns and grading excluded.', False),
    ]
    for i, (x, y, text, is_title) in enumerate(texts):
        pen.text((x, y), text, font=title_font if is_title else font, fill='#172126')
        cell = ET.SubElement(root, 'mxCell', id=f'text{i}', value=text, vertex='1', parent='1',
            style=f'text;html=0;align=left;fontSize={40 if is_title else 29};fontColor=#172126;')
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width='1760', height='55', **{'as': 'geometry'})
    ET.indent(tree)
    tree.write(path, encoding='utf-8', xml_declaration=True)
    canvas.save(folder / 'Improvement7_Workflow.png')
    print('Updated main diagram with connected recovery loops; retained both detail pages.')


if __name__ == '__main__':
    update_main_diagram()
