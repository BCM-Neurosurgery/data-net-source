"""
Script to load and run a single parser based on a config json file
"""

import toml
import argparse
import importlib
import sys
from typing import List, Union
from source.common import ParserCommon
from os import PathLike


def load_config(config_fp: Union[str, PathLike]) -> dict:
    with open(config_fp, 'r') as f:
        toml_config = toml.load(f)
    return toml_config


def load_parser(parser_config: dict) -> ParserCommon:
    """
    Initialize a source parser object based on the config file

    Doing dynamic importing like this makes it so that the only external requirements needed to run any parser are
    the software that particular parser needs. There are no global non-python requirements
    """

    class_config = parser_config['class']
    # Build a source parser from a ready class
    if class_config['type'] == "existing":
        pointer = importlib.import_module(f'parsers.{class_config["module"]}')
        parser_class = pointer.__dict__[class_config["class"]]

    # Dynamically build a parser class from the config information
    elif parser_config['class']['type'] == "dynamic":
        mixins = []
        class_parts = class_config['parts']
        for (module, mixin) in class_parts:
            pointer = importlib.import_module(f'source.{module}')
            mixins.append(pointer.__dict__[mixin])
        sub_classes = (*mixins, ParserCommon)
        parser_class = type(class_config['name'], sub_classes, {})
    else:
        raise KeyError('Invalid parser class configuration!')

    source_parser = parser_class(**parser_config["init"])

    # Set any additional values on this SourceParser
    if 'settings' in parser_config:
        for name, value in parser_config['settings'].items():
            setattr(source_parser, name, value)
    return source_parser


def parse_override(override: str):
    if '=' not in override:
        raise ValueError(f'Invalid --with value "{override}". Expected format: key.path=value')
    key_path, raw_value = override.split('=', 1)
    key_path = key_path.strip()
    if not key_path:
        raise ValueError(f'Invalid --with value "{override}". Key path cannot be empty')
    return key_path, parse_toml_value(raw_value)


def parse_toml_value(raw_value: str):
    raw_value = raw_value.strip()

    # Parse value using TOML syntax so callers can pass booleans, numbers, arrays, etc.
    try:
        parsed = toml.loads(f'value = {raw_value}')
        return parsed['value']
    except Exception:
        # If it is not valid TOML literal syntax, treat it as a plain string.
        return raw_value


def set_config_value(config: dict, key_path: str, value, allow_overwrite: bool = False):
    parts = [part.strip() for part in key_path.split('.') if part.strip()]
    if not parts:
        raise ValueError(f'Invalid config path "{key_path}"')

    current = config
    for part in parts[:-1]:
        if part in current:
            if not isinstance(current[part], dict):
                raise ValueError(
                    f'Cannot set "{key_path}": "{part}" is not a nested object in config'
                )
        else:
            current[part] = {}
        current = current[part]

    leaf = parts[-1]
    if leaf in current and current[leaf] != value and not allow_overwrite:
        raise ValueError(
            f'Config key "{key_path}" already exists with a different value. '
            f'Use --allow-overwrite to replace it.'
        )
    current[leaf] = value


def apply_overrides(config: dict, overrides: List[str], allow_overwrite: bool = False):
    for override in overrides:
        key_path, value = parse_override(override)
        set_config_value(config, key_path, value, allow_overwrite=allow_overwrite)


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('config_file', type=str,
                            help='Path to the config file that specifies the parser to run')
    arg_parser.add_argument(
        '--with',
        dest='overrides',
        action='append',
        default=[],
        metavar='key.path=value',
        help='Override a config value from the command line. Can be repeated'
    )
    arg_parser.add_argument(
        '--allow-overwrite',
        action='store_true',
        help='Allow --with values to replace existing config values'
    )

    argv = sys.argv[1:]
    if '--' in argv:
        argv = argv.copy()
        argv.remove('--')

    args = arg_parser.parse_args(argv)

    config = load_config(args.config_file)
    if args.overrides:
        apply_overrides(config, args.overrides, allow_overwrite=args.allow_overwrite)

    parser = load_parser(config['parser'])
    if 'logging' in config:
        parser.make_loggers(config['logging'])

    parser.process()
