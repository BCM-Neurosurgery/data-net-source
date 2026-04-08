"""
Entry-point script to run a parser in continuous listener mode.
This is equivalent to: python run.py config.toml --mode listen
"""

import argparse

# Reuse the existing functions from run.py to load the config and build the parser.
from run import load_config, load_parser


if __name__ == '__main__':
    # 1. Set up argument parsing to accept the path to a config file.
    arg_parser = argparse.ArgumentParser(
        description="Run a data-net-source parser in continuous listener mode."
    )
    arg_parser.add_argument(
        'config_file',
        type=str,
        help='Path to the .toml config file that specifies the parser to run.'
    )
    args = arg_parser.parse_args()

    # 2. Load the specified configuration file using the helper from run.py.
    config = load_config(args.config_file)

    # 3. Dynamically build the parser object from the mixins defined in the config.
    parser = load_parser(config['parser'])

    # 4. Set up logging as defined in the config, if present.
    if 'logging' in config:
        parser.make_loggers(config['logging'])

    # 5. Call the .listen() method to start the long-running, event-driven process.
    try:
        parser.listen()
    except AttributeError as e:
        if 'listen' in str(e):
            # Provide a helpful error if the user tries to run a checker-based config
            # with this script, as it will not have a .listen() method.
            parser.error(
                f"The configured parser '{parser.__class__.__name__}' does not have listener capabilities. "
                f"This config appears to use checker mixins instead of listener mixins. "
                f"Try using 'python run.py {args.config_file}' for checker mode."
            )
        else:
            parser.error(f"Parser setup failed: {e}", exc_info=True)
    except Exception as e:
        parser.error(f"The listener exited with an unexpected error: {e}", exc_info=True)