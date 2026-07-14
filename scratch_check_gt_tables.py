import pandas as pd

output_path = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial\aop_generate_500_multitable\pipeline_output\Pipeline_Timeout_Queries_Report_newkg_100.csv"
df = pd.read_csv(output_path)

print("Total timeout queries in CSV:", len(df))
print("\n--- Distribution of Ground-Truth Table Counts ---")
print(df["Table Count"].value_counts().sort_index())

print("\n--- Summary of Queries ---")
print(df[["Sample Row ID", "Table Count", "Ground Truth Tables", "Pipeline Retrieved Count", "First Scan Timed Out"]])
