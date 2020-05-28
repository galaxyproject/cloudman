import csv
import io
import subprocess
import yaml

from ..exceptions import CMRunCommandException


def run_command(command, shell=False):
    """
    Runs a command and returns stdout
    """
    try:
        return subprocess.check_output(
            command, universal_newlines=True, shell=shell, encoding='utf-8',
            stderr=subprocess.STDOUT)
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


# based on: https://codereview.stackexchange.com/questions/21033/flatten-dic
# tionary-in-python-functional-style
# def flatten_dict(d):
#     def items():
#         for key, value in d.items():
#             if isinstance(value, dict):
#                 for subkey, subvalue in flatten_dict(value).items():
#                     yield key + "." + subkey, subvalue
#             else:
#                 yield key, value
#     return dict(items())
