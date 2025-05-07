# Data Net Source

This package is a part of the Data Net ecosystem. It is primarily responsible for 
facilitating data aggregation from distributed resources to some central location.

It is designed to provide the boilerplate code to use a common interface for 
any format of data collection, with a particular emphasis on the research environment.

#### Publication:

#### License:

#### Citing Data Net:

## Table of Contents
- [Data Net Source](#data-net-source)
      - [Publication:](#publication)
      - [License:](#license)
      - [Citing Data Net:](#citing-data-net)
  - [Table of Contents](#table-of-contents)
- [Quick Start](#quick-start)
  - [Overview](#overview)
    - [Installation](#installation)
  - [Usage](#usage)
    - [Running Parsers](#running-parsers)
    - [Managing Parsers](#managing-parsers)
- [Source Parsers](#source-parsers)
  - [Checkers](#checkers)
  - [Transformers](#transformers)
  - [Uploaders](#uploaders)
- [The Config File](#the-config-file)
  - [Parser Definition](#parser-definition)
    - [Class](#class)
      - [Assembling Parsers](#assembling-parsers)
      - [Existing Parsers](#existing-parsers)
    - [Initiation](#initiation)
    - [Settings](#settings)
  - [Logging](#logging)
      - [File](#file)
      - [Sentry](#sentry)
  - [Dependencies](#dependencies)
      - [Pip](#pip)


# Quick Start

## Overview

The work of this package is done by specifying 'Source Parsers'. Each Source Parser is responsible
for a single step in the data moving pipeline (i.e. moving neural data from the recording 
computer to the central server).

A SourceParser consists of three parts:
  - A Checker, which finds new data to be processed
  - An optional Transformer, which prepares the data
  - An Uploader, which sends the data to it's next location

Each parser is entirely specified by a config file. The details of this config
file are available below, and a few example files are available in the `examples/` directory.

### Installation
To install data-net-source, ensure that a conda environment is installed on the system.
On sufficiently small/dedicated systems conda is not required, but this will mean that python
dependencies will be installed directly into the system python, which is generally not advisable.

To ensure proper tracking, ensure that git is installed, and clone the source code from github:
```bash
git clone git@github.com:BCM-Neurosurgery/data-net-source.git
```
Once you're in the directory of the newly cloned code, install the minimal basic dependencies using pip.
If you're using a virtual environment of any kind, make sure it is activated.

```bash
cd data-net-source
pip install -r requirements.txt
```

Ensure any external dependencies required by the parser you would like
to run are correctly installed on your system.

You should not need to manually install python dependencies specific to your parser if your parser
has its dependencies specified in the config file. Instead, activate the appropriate conda
environment, and run the prepare script using:
```bash
python prepare.py path/to/the/config/file
```
In addition to installing dependencies, this will ensure that the logging directory is ready

## Usage

A standard interface to running and managing parsers is provided by the 
top level scripts in this package.

### Running Parsers

To run a parser as specified by the config file, simply run the `run.py`
script with the path to the config file as the first argument. 
```bash
python run.py path/to/the/config/file
```
This will run the parser once.

To have the parser run automatically, schedule the run.py script to run regularly
in the appropriate python environment. If you are on a Unix machine, you can use cron
or the TaskScheduler utility on Windows.

### Managing Parsers
When parsers run, they will save their state in the directory specified by the 
`state_path` in the config file. On systems with a large data throughput, this can 
be a large file which is difficult to understand manually. For this reason, we provide
the manage.py script, which provides some useful functions for understanding
the current state of the parser.
TO see the full documentation for this utility, run:
```bash
python manage.py --help
```

# Source Parsers

Source parsers are built using a Mixin Architecture. All source parsers
must inherit from the ParserCommon base class, which defines the basic workflow for
all parsers. 

The lifetime and action of a source parser is defined by the `ParserCommon`'s
process() function. It constitutes a check(), and optional transform(), and then 
an upload() to the appropriate destination.

To provide the appropriate behavior for each of these functions, a source 
parser must also inherit from the respective mixin, as detailed below.
Implementation details are available on the base class for each mixin family.

## Checkers
A CheckerMixin, is responsible for providing the check() and save() methods.
This method is responsible for interrogating the data source to find new data, by comparing
against the upload_state. These are then returned to the SourceParser as a list
of file paths, each of which indicates a data file to be processed and uploaded.

Once the parser has successfully run, the SourceParser will report to the checkers
save() method the list of all files that were successfully uploaded, as well as those for
which processing failed at some point in the pipeline, along with the appropriate metadata. 
These should then be saved in the state file.

When writing a custom Checker, you must inherit from `source.checkers.base.BaseChecker`.
You can then implement a customized check() method and optionally a save() method.

## Transformers
TransformerMixins are responsible for providing the transform() method. 

Most parsers that collect raw data from remote sources should avoid implementing 
complicated transform() methods, unless required for security of privacy purposes. 
This is to maximize robustness of the source parsers. However, they allow the SourceParsers
to be a powerful tool for automating secondary data processing.

## Uploaders
Uploader mixins are responsible for sending all discovered data to it's next destination, 
whatever that may be. They must implement the upload() method. 
When given a list of new files to process, this method must perform the entire
upload process and return back the success or failure metadata for each file.

# The Config File
The config file is responsible for specifying everything about a parser, and 
should be the only thing that needs to be customized for each deployment.

Config file is broken down into sections as follows:

## Parser Definition
`[parser]`

### Class
`[parser.class]`

The class element of the parser configuration defines the python class, and
thereby the Checker() Transformer() and Uploader() to use when running this parser.
These can be specified in one of two ways

#### Assembling Parsers
If the "type" set on the parser class is "dynamic" then the parser class will be assembled 
dynamically from the specified Mixins. This is the simplest way of specifying a parser
and allows creating of custom parsers without having to run any python code.

In this case, you must give the name to use for the new class, as well as a list of
identifiers for the Mixins to use to define the parser's behavior. Each identifier
consists of a pair of values, the first is the importable path from within the `data_net_source.source`
module, and the second is the name of the Mixin. At least a Checker and an Uploader must be specified, and 
you are expected to pass at most one of each.

Example:
```toml
[parser.class]
type = "dynamic" 
name = "MyCustomParser"
parts = [
  ["checkers.local", "StreamedFileCheckerMixin"],
  ["uploaders.ssh", "SCPUploaderMixin"]
]

```

#### Existing Parsers
Parsers can also be defined in python code as a ready-made class.
In this case, set the "type" to 'existing', and specify the "module" that contains the
desired class, as well as the "name". The runs script will then import this parser class 
and use it directly.

Module names are assumed to be the names of modules inside the 'parser' package.
Use `.` notation in case of nesting.

If the exact same parser needs to be used in multiple places, this will simplify the config file.

Example:
```toml
[parser.class] 
type = "existing"
module = "blackrock"  # Module inside the 'parsers' module which contains the class
class = "BlackrockRemoteParser"
```


### Initiation
`[parser.init]`

This section of the parser configuration specifies the run settings for 
this particular parser. Think of these are required arguments for the parser
which will be different in virtually every parser deployment.

All parsers require a `state_path`. This gives the directory in the local
filesystem where the parser should store the upload state.

In particular, these are broken down into `source`, `middle`, and `target`.
  - `[parser.init.source]` specifies settings for where the Checker should look for new files.
  - `[parser.init.middle]` specifies an intermediate storage location for files during processing,
  - `[parser.init.target]` specifies settings for where the uploader should move the data.

as well as any additional settings needed by the transformer.

If no middle location is given, then the Uploader will use the information
in source to locate and upload files identified by the checker.


Check each Mixin you plan to include in your parser for the settings they require.

### Settings
`[parser.settings]`
Additional optional settings for the parser. Think of these as keyword arguments where 
a reasonable default value exists, and they will only need to be modified
on some specific deployments.

All of these are set directly on the parser class, and therefore available to 
all parts and Mixins. Check the static class variables on each Mixin to know what
settings could be useful.

## Logging
`[logging]`

Specify setting for how each parser should log it's activity for later review. Note
that this is separate from the state tracking the parser does internally.
Multiple logging formats can be used simultaneously.
Two options are currently implemented

#### File
`[logging.file]`

Log to a file locally using python's built-in logging RotatingFileHandler.
Expected values are:
  - `level`: integer setting for the logging level in python's logging package
  - `filepath`: full path, including file name of where to save the logs
  - `max_size`: the maximum allowed size, in bytes, before rotating out the log file
  - `max files`: the number of old files to keep before deleting old logs.

#### Sentry
`[logging.sentry]`

Use the sentry API to send log information to the Sentry service.
Using this logging format will require setting up a Sentry account and installing
the sentry SDK. 
<LINK>

Available options are:
  - `dsn`: domain service name provided by sentry to send events to
  - `event_level`: python logging level as an integer. All log entries above this 
        level are sent to sentry as discrete events (ie errors)
  - `level`: python logging level as an integer. All log entries above this level
        are sent to sentry to be used as breadcrumbs to help track down the cause of events
  - `release`: release name of this code. Useful to be able to separate out events from 
        multiple related parsers all sending event information to the same endpoint.

## Dependencies
`[dependencies]`

Any additional dependencies that need to be installed for this particular parser.
Used by the prepare.py script to install dependencies for each individual parser deployment.

This allows each parser to have it's own dependencies without bloating the entire 
data-net-source package. 

The only currently supported dependency format are pip dependencies.

#### Pip 
`[dependencies.pip]`

Use pip to install all these dependencies into the currently active python environment.
Dependencies are given as a list of strings, where each string is a valid argument to 
pip for installing the desired package

For example:

```json
{
  "dependencies": {
    "pip": [
      "numpy",
      "scipy==1.0.3",
      "brpylib @ git+ssh://git@github.com/BCM-Neurosurgery/Blackrock-Python-Utilities.git@main"
    ]
  }
}
```
This will install the newest version of numpy, version 1.0.3 of scipy, and the brpylib package directly from github