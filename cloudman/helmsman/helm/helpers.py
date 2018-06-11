import csv
import io
import subprocess


def run_list_command(command):
    output = subprocess.check_output(command, universal_newlines=True)
    reader = csv.DictReader(io.StringIO(output), delimiter="\t")
    output = []
    for row in reader:
        data = {key.strip(): val.strip() for key, val in row.items()}
        output.append(data)
    return output
