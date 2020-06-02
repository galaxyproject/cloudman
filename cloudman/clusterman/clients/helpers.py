import csv
import io
import subprocess
import yaml

from ..exceptions import CMRunCommandException


def run_command(command, shell=False, stderr=None):
    """
    Runs a command and returns stdout
    """
    try:
        return subprocess.check_output(
            command, universal_newlines=True, shell=shell, encoding='utf-8',
            stderr=stderr)
    except subprocess.CalledProcessError as e:
        raise CMRunCommandException(f"Error running command: {e.output}")


def run_list_command(command, delimiter="\t", skipinitialspace=True):
    """
    Runs a command, and parses the output as
    tab separated columnar output. First row must be column names."
    """
    output = run_command(command)
    reader = csv.DictReader(io.StringIO(output), delimiter=delimiter, skipinitialspace=skipinitialspace)
    output = []
    for row in reader:
        data = {key.strip(): val.strip() for key, val in row.items()}
        output.append(data)
    return output


def run_yaml_command(command):
    """
    Runs a command, and parses the output as yaml.
    """
    output = run_command(command)
    return yaml.safe_load(output)
