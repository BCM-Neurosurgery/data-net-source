# Data Net Source

This package is a part of the Data Net ecosystem. It is primarily responsible for 
facilitating data aggregation from distributed resources to some central location.

It is designed to provide the boilerplate code to use a common interface for 
any format of data collection, with a particular emphasis on the research environment.

#### Publication:

#### License:

#### Citing Data Net:

## Table of Contents
  - [Quick Start](#quick-start)
    - [Overview](#overview)
    - [Installation](#installation)
    - [Running Parsers](#running-parsers)
  - [Source Parsers](#source-parsers)
    - [Checkers](#checkers)
    - [Transformers](#transformers)
    - [Uploaders](#uploaders)
  - [The Config File](#the-config-file)


# Quick Start

## Overview

A SourceParser consists of three parts:
  - A Checker, which finds new data to be processed
  - An optional Transformer, which prepares the data
  - An Uploader, which sends the data to it's next location

Each parser is entirely specified by a config file. The details of this config
file are available below, and a few example files are available in the `examples/` directory.

## Installation
To install data-net-source, ensure that a conda environment is installed on the system.
To ensure proper tracking, ensure that git is installed, and clone the source code from github.

```bash
git clone git@github.com:BCM-Neurosurgery/data-net-source.git
```

Ensure that any external dependencies required by the parser you would like
to run are correctly installed on your system.

You should not need to manually install any python dependencies if your parser
has its dependencies specified. Instead, activate the appropriate conda
environment, and run the prepare script using:
```bash
python prepare.py path/to/the/config/file
```
In addition to installing dependencies, this will ensure that the logging directory is ready

## Running Parsers

To run a parser as specified by the config file, simply run the `run.py`
script with the path to the config file as the first argument. 
```bash
python run.py path/to/the/config/file
```
This will run the parser once.

To have the parser run automatically, schedule the run.py script to run regularly
in the appropriate python environment. If you are on a Unix machine, you can use cron
or the TaskScheduler utility on Windows.

## Managing Parsers
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
which processing failed at some point in the pipeline, along with the appropriate metadate. 
These should then be saved in the state file.

When writing a custom Checker, you must inherit from `source.checkers.base.BaseChecker`.
You can then implement a customized check() method and optionally a save() method.

## Transformers
TransformerMixins are responsible for providing the transform() method. 

Most parsers that collect raw data from remote sources should avoid implementing 
complicated transform() methods, unless required for security of privacy purposes. 
This is to maximize robustness of the source parsers. However, they allow the SourceParsers
to be a powerful tool for automating secondary data processing a

## Uploaders
Uploader mixins are responsible for sending all discovered data to it's next destination, 
whatever that may be. They must implement the upload method(). 
When given a list of new files to process, this method must perform the entire
upload process and return back the success or failure metadata for each file.

# The Config File

## Parser Definition

### Class
The class element of the parser configuration defines the python class, and therefore
thereby the Checker() Transformer() and Uploader() to to use when running this parser.
These can be specified in one of two ways

#### Assembling Parsers
If the "type" set on the parser class is "dynamic" then the parser class will be assembeld 
dynamically from the specified Mixins. This is the simplest way of specifying a parsers
and allows creating of custom parsers without having to run any python code.

#### Existing Parsers
Parsers can also be defined in python code as a ready made class.
In this case, set the "type" to 'existing', and specify the "module" that contains the
desired class, as well as the "name". The runs script will then import this parser class 
and use it directly.
If the exact same parser needs to be used in multiple places, this will simplify the config file.

### Initiation

### Settings 

## Logging

## Dependencies 




