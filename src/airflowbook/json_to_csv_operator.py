import csv
import json
from pathlib import Path
from typing import Any

from airflow.models import BaseOperator

# The operator below is introduced in chapter 09 of the book Data Pipelines with Apache Airflow
class JsonToCsvOperator(BaseOperator):
    def __init__(self, input_path: Path, output_path: Path, **kwargs):
        super().__init__(**kwargs)
        self._input_path = input_path
        self._output_path = output_path

    def execute(self, context: Any):
        with open(self._input_path, "r") as json_file:
            data = json.load(json_file)

        columns = {key for row in data for key in row}

        with open(self._output_path, "w") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(columns))
            writer.writeheader()
            writer.writerows(data)