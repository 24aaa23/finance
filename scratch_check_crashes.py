import pandas as pd

debug_csv = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial\aop_generate_500_multitable\pipeline_output\Pipeline_Debug_Report_gpt_oss_120b_llm_grader_newkg_100.csv"
df_debug = pd.read_csv(debug_csv)

print("--- Unique values of 'Pipeline Version' ---")
print(df_debug["Pipeline Version"].value_counts(dropna=False))

print("\n--- Unique values of 'Sample Row ID' count ---")
print("Total rows:", len(df_debug))
print("Unique Sample Row IDs:", df_debug["Sample Row ID"].nunique())
