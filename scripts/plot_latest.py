"""Main-paper panels from aggregate fixed-knowledge and object-service results."""
from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parents[1]
(root/'output').mkdir(exist_ok=True)
plt.rcParams.update({'font.size':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':6.5,'pdf.fonttype':42})
s=json.loads((root/'data/object_server_summary.json').read_text())
df=pd.read_csv(root/'data/fixed_knowledge_summary.csv')
fig=plt.figure(figsize=(2.65,2.35));ax=fig.add_axes([.21,.22,.76,.55])
for policy,label,color in [('minilm','MiniLM','#0072B2'),('qwen','Qwen','#D55E00'),('deepseek','DeepSeek','#009E73')]:
 d=df[(df.reference=='all_prior')&(df.selection=='uniform')&(df.k==10)&(df.policy==policy)&df.metric.str.startswith('coverage_lag')].sort_values('metric')
 ax.plot(range(1,6),100*d['mean'],'o-',ms=3,lw=1,label=label,color=color)
 ax.fill_between(range(1,6),100*d.ci_low,100*d.ci_high,color=color,alpha=.12)
ax.set(xlabel='Future task offset',ylabel='Extra-record coverage (%)',xticks=range(1,6),ylim=(0,30));ax.legend(frameon=False,loc='lower center',bbox_to_anchor=(.5,1.01),ncol=2,columnspacing=.6,handlelength=1)
ax.spines[['top','right']].set_visible(False);fig.savefig(root/'output/fixed_knowledge_k10.pdf');plt.close(fig)
for name,values,labels,ylabel,upper in [
 ('object_rotation_disclosure',[s['stable_extra_records'],s['rotated_direct_extra_records'],s['rotated_length_extra_records'],s['padded_extra_records']],['Stable','Keys','Length','Padded'],'Extra record–task pairs',32),
 ('object_rotation_recovery',[s['length_recovered_mappings'],s['padded_recovered_mappings']],['Length','Padded'],'Recovered initial mappings',300)]:
 fig=plt.figure(figsize=(2.65,2.35));ax=fig.add_axes([.21,.22,.76,.55]);ax.bar(range(len(values)),values,width=.6,color=['#0072B2','#999999','#D55E00','#009E73'] if len(values)==4 else ['#D55E00','#009E73'])
 for i,n in enumerate(values):ax.text(i,n+upper*.025,str(n),ha='center',fontsize=8)
 ax.set(xticks=range(len(values)),xticklabels=labels,ylabel=ylabel,ylim=(0,upper));ax.spines[['top','right']].set_visible(False)
 fig.savefig(root/f'output/{name}.pdf');plt.close(fig)
