import os
import sys
import argparse

noticed_folders = ""    #
completed_folders = ""

watched_dir = ""


def list_folders(directory):
    """Return a list of all the subfolders in a given directory"""
    return [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]


def check_vs_list(directory, list_file):
    """Check for any folders in the directory that are not listed in the list_file"""
    try:
        with open(list_file) as nf:
            listed = nf.read()
    except FileNotFoundError:
        listed = ''

    not_listed = []
    for folder in list_folders(directory):
        if folder not in listed:
            not_listed.append(folder)

    split_notice = not_listed + listed.split('\n')
    with open(list_file, 'w') as nf:
        nf.writelines(split_notice)

    return not_listed


def check_unnoticed(directory):
    """Check for new folders against the "noticed_folders" file"""
    return check_vs_list(directory, noticed_folders)


def check_incomplete(directory):
    """Check for new folders against the "noticed_folders" file"""
    return check_vs_list(directory, completed_folders)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Check for new or incomplete uploads in a directory')
    parser.add_argument('directory', metavar='dir', type=str, nargs=1,
                        help='location to run the check', default=watched_dir)
    args = parser.parse_args()

    incomplete = check_incomplete(args.directory)
    if incomplete:
        print('Incomplete directories:')
        for f in incomplete:
            print(f'  - {f}')
    else:
        print('No incomplete directories')

    unnoticed = check_unnoticed(args.directory)
    if unnoticed:
        print('Unnoticed directories:')
        for f in unnoticed:
            print(f'  - {f}')
    else:
        print('No unnoticed directories')

