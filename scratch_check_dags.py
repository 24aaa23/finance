import pandas as pd

file_path = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial\aop_generate_500_multitable\pipeline_output\Pipeline_Retest_Report_gpt_oss_120b_llm_grader_newkg_300.csv"
df = pd.read_csv(file_path)

# Fill na values
df['DAG Sequence'] = df['DAG Sequence'].fillna('Unknown')
df['New Status'] = df['New Status'].fillna('Unknown')

# Group by and count
grouped = df.groupby(['DAG Sequence', 'New Status']).size().unstack(fill_value=0)

# Add row totals
grouped['Total'] = grouped.sum(axis=1)

# Sort by Total descending
grouped = grouped.sort_values(by='Total', ascending=False)

print("--- Cross-tabulation of DAG Sequence and New Status ---")
print(grouped.to_string())
