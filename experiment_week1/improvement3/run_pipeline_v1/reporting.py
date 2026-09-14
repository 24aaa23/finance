"""Dataset loading helper."""

from .common import INPUT_SAMPLE_SHEET, os, pd


def load_input_samples(sample_file: str) -> pd.DataFrame:
    """Load benchmark questions from CSV or XLSX without changing downstream schema."""
    extension = os.path.splitext(sample_file)[1].lower()
    if extension in {".xlsx", ".xls"}:
        if INPUT_SAMPLE_SHEET:
            return pd.read_excel(sample_file, sheet_name=INPUT_SAMPLE_SHEET)
        return pd.read_excel(sample_file)
    return pd.read_csv(sample_file)
