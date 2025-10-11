"""
Script to load and run a single parser based on a config json file
"""

import toml
import argparse
import importlib
from source.common import ParserCommon
from os import PathLike


def load_config(config_fp: str | PathLike) -> dict:
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


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('config_file', type=str,
                            help='Path to the config file that specifies the parser to run')
    arg_parser.add_argument('--mode', choices=['checker', 'listen'], required=True,
                            help='Execution mode: checker (batch processing) or listen (continuous monitoring)')
    args = arg_parser.parse_args()

    config = load_config(args.config_file)
    parser = load_parser(config['parser'])
    if 'logging' in config:
        parser.make_loggers(config['logging'])

    # Execute in the specified mode
    if args.mode == 'listen':
        try:
            parser.listen()
        except AttributeError:
            parser.error(
                f"Parser '{parser.__class__.__name__}' does not support listen mode. "
                f"Ensure your config uses listener mixins, not checker mixins."
            )
        except Exception as e:
            parser.error(f"Listen mode failed: {e}", exc_info=True)
    else:
        # Checker mode
        try:
            parser.process()
        except AttributeError as e:
            parser.error(
                f"Parser '{parser.__class__.__name__}' does not support checker mode. "
                f"This config appears to use listener mixins instead of checker mixins. "
                f"Try using --mode listen instead."
            )
        except Exception as e:
            parser.error(f"Checker mode failed: {e}", exc_info=True)
