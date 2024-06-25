"""
Script to load and run a single parser based on a config json file
"""

import json
import argparse
import importlib
from source.common import ParserCommon
from os import PathLike


def load_config(config_fp: [str, PathLike]) -> dict:
    with open(config_fp, 'r') as f:
        json_config = json.load(f)
    return json_config


def load_parser(parser_config: dict) -> ParserCommon:
    """
    Initialize a source parser object based on the config file

    Doing dynamic importing like this makes it so that the only external requirements needed to run any parser are
    the software that particular parser needs. There are no global non-python requirements
    """
    # Build a source parser from a ready class
    if 'module' in parser_config and 'class' in parser_config:
        pointer = importlib.import_module(f'parsers.{parser_config["module"]}')
        parser_class = pointer.__dict__[parser_config["class"]]

    # Dynamically build a parser class from the config information
    elif 'make-class' in parser_config:
        mixins = []
        class_parts = parser_config['make-class']['parts']
        for (module, mixin) in class_parts:
            pointer = importlib.import_module(f'source.{module}')
            mixins.append(pointer.__dict__[mixin])
        sub_classes = (*mixins, ParserCommon)
        parser_class = type(parser_config['make-class']['name'], sub_classes, {})
    else:
        raise KeyError('Invalid parser configuration!')

    source_parser = parser_class(**parser_config["init"])

    # Set any additional values on this SourceParser
    if 'settings' in parser_config:
        for name, value in parser_config['settings'].items():
            setattr(source_parser, name, value)
    return source_parser


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('config_file', type=str,
                            help='Path to the config file that specifies the parser to run')
    args = arg_parser.parse_args()

    config = load_config(args.config_file)
    parser = load_parser(config['parser'])
    if 'logging' in config:
        parser.make_loggers(config['logging'])

    parser.process()
