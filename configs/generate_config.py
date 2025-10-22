#!/usr/bin/env python3
"""
Interactive Config Generator for Data Net Source

This script helps users create configuration files by selecting from available
checkers, listeners, transformers, and uploaders.
"""

import os
import sys
from pathlib import Path


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

LISTENERS = {
    "1": {
        "name": "WatchdogListenerMixin",
        "module": "listeners.watchdog_listener",
        "description": "Monitor filesystem for new files in real-time",
        "source_config": {
            "path": "path/to/monitor",
            "include_patterns": [".*\\.csv$", ".*\\.txt$"],
            "exclude_patterns": [".*\\.tmp$"],
            "batch_max_size": 10,
            "batch_max_latency_seconds": 60,
        },
        "dependencies": ["watchdog"]
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


def generate_toml_config(parser_name, mode, checker_or_listener, transformer, uploader, state_path, log_path):
    """Generate TOML configuration content."""
    
    # Determine which component to use
    if mode == "checker":
        primary_component = CHECKERS[checker_or_listener]
    else:
        primary_component = LISTENERS[checker_or_listener]
    
    transformer_component = TRANSFORMERS[transformer]
    uploader_component = UPLOADERS[uploader]
    
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
    config_lines.append("# Logging configuration")
    config_lines.append("[logging.file]")
    config_lines.append(f'filepath = "{log_path}"')
    config_lines.append("level = 0  # 0=DEBUG, 10=INFO, 20=WARNING, 30=ERROR")
    config_lines.append("max_size = 21048576  # 20MB")
    config_lines.append("max_files = 5")
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
    
    # Step 5: Basic configuration
    print_header("Step 5: Basic Configuration")
    parser_name = input("\nEnter parser name (e.g., MyDataParser): ").strip()
    if not parser_name:
        parser_name = "CustomParser"
    
    state_path = input("Enter state directory path: ").strip()
    if not state_path:
        state_path = "path/to/state/directory"
    
    log_path = input("Enter log file path: ").strip()
    if not log_path:
        log_path = "path/to/log/file.log"
    
    # Generate config
    print_header("Generating Configuration")
    config_content = generate_toml_config(
        parser_name, mode, primary_choice, transformer_choice, 
        uploader_choice, state_path, log_path
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
