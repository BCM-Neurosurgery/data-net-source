# Data Net Source

This package is a part of the Data Net ecosystem. It is primarily responsible for 
facilitating data aggregation from distributed resources to some central location.

It is designed to provide the boilerplate code to use a common interface for 
any format of data collection, with a particular emphasis on the research environment.

#### Publication:

#### License:

#### Citing Data Net:

## Table of Contents
  - [Quick Start]()
    - [Overview]()
    - [Installation]()
    - [Tutorials]()
  - [Source Parsers](#source-parsers)
    - [Checkers](#checkers)
    - [Transformers](#transformers)
    - [Uploaders](#uploaders)
  - [The Config File](#the-config-file)


# Quick Start

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

#### Assembling Parsers
Parsers can be dynamically assembled from their base elements by 

#### Existing Parsers
Th

### Initiation

### Settings 

## Logging

## Dependencies 




