from __future__ import annotations

from pathlib import Path


def write_report(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in summary.items())
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Bharat.Law Pipeline Metrics</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #202124; }}
    table {{ border-collapse: collapse; min-width: 420px; }}
    th, td {{ border: 1px solid #d6d9de; padding: 10px 12px; text-align: left; }}
    th {{ background: #f3f5f7; }}
  </style>
</head>
<body>
  <h1>Bharat.Law Pipeline Metrics</h1>
  <table>{rows}</table>
</body>
</html>
""",
        encoding="utf-8",
    )
