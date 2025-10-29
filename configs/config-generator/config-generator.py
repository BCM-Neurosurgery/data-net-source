#!/usr/bin/env python3
"""
Interactive Config Generator for Data Net Source

This script helps users create configuration files by selecting from available
checkers, listeners, transformers, and uploaders.
"""

import os
import sys
import importlib
from pathlib import Path


def fetch_listener_metadata(module_path: str, class_name: str) -> dict:
    """
    Dynamically fetch metadata from a listener mixin class.
    
    Since metadata properties don't depend on instance state, we access them
    directly from the property's fget function.
    
    :param module_path: Module path (e.g., "listeners.watchdog_listener")
    :param class_name: Class name (e.g., "WatchdogListenerMixin")
    :return: Dictionary with dependencies and config_template
    """
    try:
        # Add parent directory to path if not already there
        current_dir = Path(__file__).parent if '__file__' in globals() else Path.cwd()
        parent_dir = current_dir.parent.parent if '__file__' in globals() else Path.cwd().parent
        
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))
        
        module = importlib.import_module(f"source.{module_path}")
        mixin_class = getattr(module, class_name)
        
        # Access property getters directly (they don't use self)
        dependencies = mixin_class.required_dependencies.fget(None)
        config = mixin_class.config_template.fget(None)
        
        return {
            'dependencies': dependencies or [],
            'source_config': config or {}
        }
    except Exception as e:
        print(f"Warning: Could not fetch metadata for {class_name}: {e}")
        return {'dependencies': [], 'source_config': {}}


# Available components registry
CHECKERS = {
    "1": {
        "name": "FileCheckerMixin",
        "module": "checkers.local.__init__",
        "description": "Check local directory for new files",
        "source_config": {
            "path": "path/to/local/directory",
            "check_for_modifications": False,
        },
        "dependencies": []
    },
    "2": {
        "name": "StreamedFileCheckerMixin",
        "module": "checkers.local.stream",
        "description": "Check local directory for streamed files",
        "source_config": {
            "path": "path/to/local/directory",
            "streamed_files": "*",
            "stream_rate": 60,
            "reliability_factor": 1.0,
        },
        "dependencies": []
    },
    "3": {
        "name": "S3CheckerMixin",
        "module": "checkers.s3",
        "description": "Check AWS S3 bucket for new files",
        "source_config": {
            "bucket": "source-bucket-name",
            "prefix": "path/in/bucket/",
        },
        "dependencies": ["boto3"]
    },
    "4": {
        "name": "OuraAPICheckerMixin",
        "module": "checkers.api.oura",
        "description": "Fetch data from Oura Ring API",
        "source_config": {
            "path": "path/to/store/downloaded/data",
            "oura_config": "path/to/oura/config.json",
        },
        "dependencies": ["requests"]
    },
    "5": {
        "name": "QualtricsAPICheckerMixin",
        "module": "checkers.api.qualtrics",
        "description": "Fetch data from Qualtrics API",
        "source_config": {
            "path": "path/to/store/downloaded/data",
            "qualtrics_config": "path/to/qualtrics/config.json",
        },
        "dependencies": ["requests"]
    },
    "6": {
        "name": "REDCapAPICheckerMixin",
        "module": "checkers.api.redcap",
        "description": "Fetch data from REDCap API",
        "source_config": {
            "path": "path/to/store/downloaded/data",
            "redcap_config": "path/to/redcap/config.json",
        },
        "dependencies": ["requests"]
    },
    "7": {
        "name": "RuneAPICheckerMixin",
        "module": "checkers.api.rune",
        "description": "Fetch data from Rune Labs API",
        "source_config": {
            "path": "path/to/store/downloaded/data",
            "rune_config": "path/to/rune/config",
            "rune_patients_config": "path/to/patients/config.json",
        },
        "dependencies": ["runeq"]
    },
}

# Dynamically fetch listener metadata
watchdog_meta = fetch_listener_metadata("listeners.watchdog_listener", "WatchdogListenerMixin")

LISTENERS = {
    "1": {
        "name": "WatchdogListenerMixin",
        "module": "listeners.watchdog_listener",
        "description": "Monitor filesystem for new files in real-time",
        "source_config": watchdog_meta['source_config'],
        "dependencies": watchdog_meta['dependencies']
    },
}

TRANSFORMERS = {
    "0": {
        "name": "None",
        "module": None,
        "description": "No transformation (pass-through)",
        "middle_config": None,
        "dependencies": []
    },
    "1": {
        "name": "OpenPoseTransformer",
        "module": "transformers.openpose",
        "description": "Process videos with OpenPose for pose estimation",
        "middle_config": {
            "path": "path/to/intermediate/storage",
        },
        "dependencies": []
    },
    "2": {
        "name": "MatlabTransformerMixin",
        "module": "transformers.matlab",
        "description": "Process data using MATLAB scripts",
        "middle_config": {
            "path": "path/to/intermediate/storage",
        },
        "dependencies": []
    },
}

UPLOADERS = {
    "1": {
        "name": "S3UploaderMixin",
        "module": "uploaders.local_to_s3",
        "description": "Upload files to AWS S3 bucket",
        "target_config": {
            "bucket": "target-bucket-name",
            "prefix": "raw_data/",
            "allow-overwrite": True,
        },
        "dependencies": ["boto3"]
    },
    "2": {
        "name": "CopyUploaderMixin",
        "module": "uploaders.simple",
        "description": "Copy files to local directory",
        "target_config": {
            "path": "path/to/destination",
        },
        "dependencies": []
    },
    "3": {
        "name": "FTPUploaderMixin",
        "module": "uploaders.ftp",
        "description": "Upload files via FTP",
        "target_config": {
            "host": "ftp.example.com",
            "port": 21,
            "username": "username",
            "password": "password",
            "path": "/remote/path",
        },
        "dependencies": []
    },
    "4": {
        "name": "SSHUploaderMixin",
        "module": "uploaders.ssh",
        "description": "Upload files via SSH/SFTP",
        "target_config": {
            "host": "ssh.example.com",
            "port": 22,
            "username": "username",
            "key_file": "path/to/ssh/key",
            "path": "/remote/path",
        },
        "dependencies": ["paramiko"]
    },
}

LOGGING = {
    "0": {
        "name": "None",
        "description": "No logging configuration",
        "config": None,
        "dependencies": []
    },
    "1": {
        "name": "File Logging",
        "description": "Log to rotating file on disk",
        "config": {
            "filepath": "path/to/log/file.log",
            "level": 0,  # 0=DEBUG, 10=INFO, 20=WARNING, 30=ERROR
            "max_size": 21048576,  # 20MB
            "max_files": 5,
        },
        "dependencies": []
    },
    "2": {
        "name": "Sentry",
        "description": "Send errors and logs to Sentry for monitoring",
        "config": {
            "dsn": "https://your-sentry-dsn",
            "level": 10,  # Breadcrumb level
            "event_level": 30,  # Event level (errors and above)
        },
        "dependencies": ["sentry-sdk"]
    },
    "3": {
        "name": "Healthchecks.io",
        "description": "Monitor job runs with healthchecks.io",
        "config": {
            "url": "https://hc-ping.com",
            "ping_key": "your-ping-key",
            "slug": "parser-slug",
            "level": 20,  # WARNING and above
            "create": True,
            "verify_cert": True,
        },
        "dependencies": ["requests"]
    },
    "4": {
        "name": "File + Sentry",
        "description": "Log to file and send errors to Sentry",
        "config": "combined",
        "dependencies": ["sentry-sdk"]
    },
    "5": {
        "name": "File + Healthchecks",
        "description": "Log to file and monitor with healthchecks.io",
        "config": "combined",
        "dependencies": ["requests"]
    },
    "6": {
        "name": "All Logging",
        "description": "File, Sentry, and Healthchecks combined",
        "config": "combined",
        "dependencies": ["sentry-sdk", "requests"]
    },
}


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_options(options_dict, title):
    """Print available options."""
    print(f"\n{title}:")
    print("-" * 70)
    for key, value in options_dict.items():
        print(f"  [{key}] {value['name']}")
        print(f"      {value['description']}")


def get_user_choice(prompt, valid_choices):
    """Get and validate user input."""
    while True:
        choice = input(f"\n{prompt}: ").strip()
        if choice in valid_choices:
            return choice
        print(f"Invalid choice. Please select from: {', '.join(valid_choices)}")


def generate_toml_config(parser_name, mode, checker_or_listener, transformer, uploader, logging_choice, state_path, log_path):
    """Generate TOML configuration content."""
    
    # Determine which component to use
    if mode == "checker":
        primary_component = CHECKERS[checker_or_listener]
    else:
        primary_component = LISTENERS[checker_or_listener]
    
    transformer_component = TRANSFORMERS[transformer]
    uploader_component = UPLOADERS[uploader]
    logging_component = LOGGING[logging_choice]
    
    # Build parts list
    parts = []
    parts.append([primary_component["module"], primary_component["name"]])
    
    if transformer_component["module"]:
        parts.append([transformer_component["module"], transformer_component["name"]])
    
    parts.append([uploader_component["module"], uploader_component["name"]])
    
    # Collect dependencies
    dependencies = set()
    dependencies.update(primary_component["dependencies"])
    dependencies.update(transformer_component["dependencies"])
    dependencies.update(uploader_component["dependencies"])
    dependencies.update(logging_component["dependencies"])
    
    # Start building TOML content
    config_lines = []
    config_lines.append("# " + "=" * 60)
    config_lines.append(f"# Auto-generated config for {parser_name}")
    config_lines.append(f"# Mode: {mode}")
    config_lines.append("# " + "=" * 60)
    config_lines.append("")
    config_lines.append("[parser]")
    config_lines.append("")
    config_lines.append("[parser.class]")
    config_lines.append('type = "dynamic"')
    config_lines.append(f'name = "{parser_name}"')
    config_lines.append("parts = [")
    for module, name in parts:
        config_lines.append(f'  ["{module}", "{name}"],')
    config_lines.append("]")
    config_lines.append("")
    
    # Parser initialization
    config_lines.append("[parser.init]")
    config_lines.append(f'state_path = "{state_path}"')
    config_lines.append("")
    
    # Source configuration
    config_lines.append("[parser.init.source]")
    for key, value in primary_component["source_config"].items():
        if isinstance(value, str):
            config_lines.append(f'{key} = "{value}"')
        elif isinstance(value, bool):
            config_lines.append(f'{key} = {str(value).lower()}')
        elif isinstance(value, list):
            config_lines.append(f'{key} = {value}')
        else:
            config_lines.append(f'{key} = {value}')
    config_lines.append("")
    
    # Middle configuration (if transformer is used)
    if transformer_component["middle_config"]:
        config_lines.append("[parser.init.middle]")
        for key, value in transformer_component["middle_config"].items():
            config_lines.append(f'{key} = "{value}"')
        config_lines.append("")
    
    # Target configuration
    config_lines.append("[parser.init.target]")
    for key, value in uploader_component["target_config"].items():
        if isinstance(value, str):
            config_lines.append(f'{key} = "{value}"')
        elif isinstance(value, bool):
            config_lines.append(f'{key} = {str(value).lower()}')
        else:
            config_lines.append(f'{key} = {value}')
    config_lines.append("")
    
    # Logging configuration
    if logging_component["config"] is not None:
        config_lines.append("# Logging configuration")
        
        if logging_component["config"] == "combined":
            # Handle combined logging options
            if logging_choice == "4":  # File + Sentry
                config_lines.append("[logging.file]")
                for key, value in LOGGING["1"]["config"].items():
                    if isinstance(value, str):
                        config_lines.append(f'{key} = "{value}"')
                    else:
                        config_lines.append(f'{key} = {value}')
                config_lines.append("")
                config_lines.append("[logging.sentry]")
                for key, value in LOGGING["2"]["config"].items():
                    if isinstance(value, str):
                        config_lines.append(f'{key} = "{value}"')
                    else:
                        config_lines.append(f'{key} = {value}')
                config_lines.append("")
            
            elif logging_choice == "5":  # File + Healthchecks
                config_lines.append("[logging.file]")
                for key, value in LOGGING["1"]["config"].items():
                    if isinstance(value, str):
                        config_lines.append(f'{key} = "{value}"')
                    else:
                        config_lines.append(f'{key} = {value}')
                config_lines.append("")
                config_lines.append("[logging.healthchecks]")
                for key, value in LOGGING["3"]["config"].items():
                    if isinstance(value, str):
                        config_lines.append(f'{key} = "{value}"')
                    elif isinstance(value, bool):
                        config_lines.append(f'{key} = {str(value).lower()}')
                    else:
                        config_lines.append(f'{key} = {value}')
                config_lines.append("")
            
            elif logging_choice == "6":  # All
                config_lines.append("[logging.file]")
                for key, value in LOGGING["1"]["config"].items():
                    if isinstance(value, str):
                        config_lines.append(f'{key} = "{value}"')
                    else:
                        config_lines.append(f'{key} = {value}')
                config_lines.append("")
                config_lines.append("[logging.sentry]")
                for key, value in LOGGING["2"]["config"].items():
                    if isinstance(value, str):
                        config_lines.append(f'{key} = "{value}"')
                    else:
                        config_lines.append(f'{key} = {value}')
                config_lines.append("")
                config_lines.append("[logging.healthchecks]")
                for key, value in LOGGING["3"]["config"].items():
                    if isinstance(value, str):
                        config_lines.append(f'{key} = "{value}"')
                    elif isinstance(value, bool):
                        config_lines.append(f'{key} = {str(value).lower()}')
                    else:
                        config_lines.append(f'{key} = {value}')
                config_lines.append("")
        else:
            # Single logging type
            log_type = logging_component["name"].lower().replace(" ", "")
            if "file" in log_type:
                section = "logging.file"
            elif "sentry" in log_type:
                section = "logging.sentry"
            elif "healthchecks" in log_type:
                section = "logging.healthchecks"
            else:
                section = "logging.file"
            
            config_lines.append(f"[{section}]")
            for key, value in logging_component["config"].items():
                if isinstance(value, str):
                    config_lines.append(f'{key} = "{value}"')
                elif isinstance(value, bool):
                    config_lines.append(f'{key} = {str(value).lower()}')
                else:
                    config_lines.append(f'{key} = {value}')
            config_lines.append("")
    
    # Dependencies
    if dependencies:
        config_lines.append("[dependencies]")
        config_lines.append("pip = [")
        for dep in sorted(dependencies):
            config_lines.append(f'  "{dep}",')
        config_lines.append("]")
    
    return "\n".join(config_lines)


def main():
    """Main interactive configuration generator."""
    print_header("Data Net Source - Config Generator")
    print("\nThis tool will help you create a configuration file for your parser.")
    
    # Step 1: Choose mode
    print_header("Step 1: Choose Parser Mode")
    print("\nSelect the execution mode for your parser:")
    print("  [1] Checker Mode - Batch processing (runs once per execution)")
    print("  [2] Listen Mode  - Continuous monitoring (event-driven)")
    
    mode_choice = get_user_choice("Select mode [1/2]", ["1", "2"])
    mode = "checker" if mode_choice == "1" else "listen"
    
    # Step 2: Choose checker or listener
    if mode == "checker":
        print_header("Step 2: Choose Checker")
        print_options(CHECKERS, "Available Checkers")
        checker_choice = get_user_choice(
            f"Select checker [1-{len(CHECKERS)}]",
            list(CHECKERS.keys())
        )
        primary_choice = checker_choice
    else:
        print_header("Step 2: Choose Listener")
        print_options(LISTENERS, "Available Listeners")
        listener_choice = get_user_choice(
            f"Select listener [1-{len(LISTENERS)}]",
            list(LISTENERS.keys())
        )
        primary_choice = listener_choice
    
    # Step 3: Choose transformer (optional)
    print_header("Step 3: Choose Transformer (Optional)")
    print_options(TRANSFORMERS, "Available Transformers")
    transformer_choice = get_user_choice(
        f"Select transformer [0-{len(TRANSFORMERS)-1}]",
        list(TRANSFORMERS.keys())
    )
    
    # Step 4: Choose uploader
    print_header("Step 4: Choose Uploader")
    print_options(UPLOADERS, "Available Uploaders")
    uploader_choice = get_user_choice(
        f"Select uploader [1-{len(UPLOADERS)}]",
        list(UPLOADERS.keys())
    )
    
    # Step 5: Choose logging
    print_header("Step 5: Choose Logging (Optional)")
    print_options(LOGGING, "Available Logging Options")
    logging_choice = get_user_choice(
        f"Select logging [0-{len(LOGGING)-1}]",
        list(LOGGING.keys())
    )
    
    # Step 6: Basic configuration
    print_header("Step 6: Basic Configuration")
    parser_name = input("\nEnter parser name (e.g., MyDataParser): ").strip()
    if not parser_name:
        parser_name = "CustomParser"
    
    state_path = input("Enter state directory path: ").strip()
    if not state_path:
        state_path = "path/to/state/directory"
    
    # Only ask for log path if file logging is selected
    log_path = None
    if logging_choice in ["1", "4", "5", "6"]:
        log_path = input("Enter log file path: ").strip()
        if not log_path:
            log_path = "path/to/log/file.log"
    
    # Generate config
    print_header("Generating Configuration")
    config_content = generate_toml_config(
        parser_name, mode, primary_choice, transformer_choice, 
        uploader_choice, logging_choice, state_path, log_path
    )
    
    # Save config
    output_filename = input("\nEnter output filename (e.g., my_parser.toml): ").strip()
    if not output_filename:
        output_filename = "generated_config.toml"
    
    if not output_filename.endswith('.toml'):
        output_filename += '.toml'
    
    # Determine output path (generated_configs directory)
    script_dir = Path(__file__).parent
    generated_dir = script_dir / "generated_configs"
    
    # Create generated_configs directory if it doesn't exist
    generated_dir.mkdir(exist_ok=True)
    
    output_path = generated_dir / output_filename
    
    with open(output_path, 'w') as f:
        f.write(config_content)
    
    print_header("Configuration Generated Successfully!")
    print(f"\nConfig file saved to: {output_path}")
    print("\nNext steps:")
    print(f"  1. Review and edit the config file: {output_filename}")
    print(f"  2. Replace placeholder values with your actual paths and settings")
    print(f"  3. Run: python prepare.py {output_filename}")
    print(f"  4. Run: python run.py {output_filename} --mode {mode}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nConfig generation cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}")
        sys.exit(1)
