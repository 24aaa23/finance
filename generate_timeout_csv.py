import pandas as pd
import json
import os

debug_csv = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial\aop_generate_500_multitable\pipeline_output\Pipeline_Debug_Report_gpt_oss_120b_llm_grader_newkg_100.csv"
benchmark_csv = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial\dataset_new\wealth_management_all_benchmark_questions_combined (2).csv"
output_path = r"C:\Users\AMAN KUMAR SINGH\Desktop\financial\aop_generate_500_multitable\pipeline_output\Pipeline_Timeout_Queries_Report_newkg_100.csv"

df_debug = pd.read_csv(debug_csv)
df_bench = pd.read_csv(benchmark_csv)

records = []

for idx, row in df_debug.iterrows():
    sample_id = row["Sample Row ID"]
    question = row["Question"]
    
    # Retrieve pipeline's retrieved classes
    classes_str = row.get("Retrieved Classes", "[]")
    if pd.isna(classes_str):
        classes_list = []
    else:
        try:
            classes_list = json.loads(classes_str)
        except Exception:
            classes_list = [c.strip() for c in classes_str.replace("[", "").replace("]", "").replace('"', '').split(",") if c.strip()]
    pipeline_retrieved_count = len(classes_list)
    
    # Find matching ground truth info from benchmark questions CSV
    bench_match = df_bench[df_bench["global_question_id"] == sample_id]
    if not bench_match.empty:
        bench_row = bench_match.iloc[0]
        gt_table_count = int(bench_row["number_of_tables_used"])
        gt_tables = str(bench_row["tables_used"])
        category = str(bench_row.get("category", ""))
        difficulty = str(bench_row.get("difficulty", ""))
    else:
        gt_table_count = 0
        gt_tables = "N/A"
        category = "N/A"
        difficulty = "N/A"
        
    trace_file = row["Debug Trace File"]
    
    # Parse scan attempts from JSON trace
    first_scan_status = "N/A"
    first_scan_error = ""
    first_scan_timeout = False
    any_scan_timeout = False
    
    if pd.notna(trace_file) and os.path.exists(trace_file):
        try:
            with open(trace_file, "r", encoding="utf-8") as f:
                trace_data = json.load(f)
                attempts = trace_data.get("scan_and_refine", {}).get("attempts", [])
                scan_attempts = [a for a in attempts if a.get("operator") == "Scan"]
                
                if len(scan_attempts) > 0:
                    first_scan = scan_attempts[0]
                    first_scan_status = first_scan.get("status")
                    first_scan_error = str(first_scan.get("error") or "")
                    if "timed out" in first_scan_error.lower():
                        first_scan_timeout = True
                    
                    for sa in scan_attempts:
                        err = str(sa.get("error") or "")
                        if "timed out" in err.lower():
                            any_scan_timeout = True
        except Exception as e:
            first_scan_error = f"Error reading trace: {e}"
            
    final_scan_status = row.get("Scan Status")
    final_scan_error = str(row.get("Scan Error") or "")
    final_scan_timeout = "timed out" in final_scan_error.lower()
    
    if final_scan_timeout:
        any_scan_timeout = True
        
    records.append({
        "Sample Row ID": sample_id,
        "Question": question,
        "Table Count": gt_table_count,
        "Ground Truth Tables": gt_tables,
        "Pipeline Retrieved Count": pipeline_retrieved_count,
        "Pipeline Retrieved Classes": classes_str,
        "First Scan Timed Out": first_scan_timeout,
        "Final Scan Timed Out": final_scan_timeout,
        "Any Scan Timed Out": any_scan_timeout,
        "First Scan Status": first_scan_status,
        "First Scan Error": first_scan_error,
        "Final Scan Status": final_scan_status,
        "Final Scan Error": final_scan_error,
        "Self Heal Attempts": row.get("Self Heal Attempts", 0),
        "Category": category,
        "Difficulty": difficulty,
        "New Status": row.get("New Status"),
        "Generated SPARQL": row.get("Generated SPARQL", ""),
        "Debug Failure Type": row.get("Debug Failure Type")
    })

all_processed_df = pd.DataFrame(records)

# Filter for rows where Any Scan Timed Out is True
timeout_filtered_df = all_processed_df[all_processed_df["Any Scan Timed Out"] == True]

# Sort by Ground Truth Table Count (descending)
timeout_filtered_df = timeout_filtered_df.sort_values(by="Table Count", ascending=False)

# Save to output CSV
timeout_filtered_df.to_csv(output_path, index=False)

print(f"Successfully processed {len(df_debug)} rows.")
print(f"Found {len(timeout_filtered_df)} queries with any timeout error.")
print(f"Saved timeout queries report to: {output_path}")
