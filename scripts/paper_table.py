"""Render the reported h=10 anchor table from packaged aggregate CSVs."""
import csv
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with (root/'data/known_anchor_summary.csv').open() as f:
    rows={r['policy']:r for r in csv.DictReader(f) if int(r['history_budget'])==10}
lines=['| Policy | Mean anchors | Extra-record coverage (%) | Extra records/task |','|---|---:|---:|---:|']
for policy,label in [('minilm','MiniLM'),('qwen','Qwen'),('deepseek','DeepSeek')]:
    r=rows[policy]
    lines.append(f"| {label} | {float(r['anchors']):.2f} | {100*float(r['any_additional_known']):.2f} | {float(r['additional_known_documents']):.3f} |")
text='\n'.join(lines)+'\n'
assert text==(root/'expected/paper_table.md').read_text()
(root/'output').mkdir(exist_ok=True)
(root/'output/paper_table.md').write_text(text)
print(text)
