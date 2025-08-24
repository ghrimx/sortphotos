#!/usr/bin/env python
# encoding: utf-8
"""
sortphotos.py

Modified to include:
- Summary of moved/copied/skipped/duplicates
- Skipped + duplicate files listed
- Summary written to log file (overwrite each run)
- Test mode reflected in summary
- Files without date or hidden files placed in "unknown" folder
"""
from __future__ import print_function
from __future__ import with_statement
import subprocess
import os
import sys
import shutil
try:
    import json
except:
    import simplejson as json
import filecmp
from datetime import datetime, timedelta
import re
import locale

from progressbar import percent_complete

# Setting locale to the 'local' value
locale.setlocale(locale.LC_ALL, '')

exiftool_location = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'Image-ExifTool', 'exiftool')


# -------- convenience methods -------------

def parse_date_exif(date_string):
    elements = str(date_string).strip().split()
    if len(elements) < 1:
        return None

    date_entries = elements[0].split(':')
    if len(date_entries) == 3 and date_entries[0] > '0000' and '.' not in ''.join(date_entries):
        year = int(date_entries[0])
        month = int(date_entries[1])
        day = int(date_entries[2])
    else:
        return None

    time_zone_adjust = False
    hour = 12
    minute = 0
    second = 0

    if len(elements) > 1:
        time_entries = re.split(r'(\+|-|Z)', elements[1])
        time = time_entries[0].split(':')

        if len(time) == 3:
            hour = int(time[0]); minute = int(time[1]); second = int(time[2].split('.')[0])
        elif len(time) == 2:
            hour = int(time[0]); minute = int(time[1])

        if len(time_entries) > 2:
            time_zone = time_entries[2].split(':')
            if len(time_zone) == 2:
                time_zone_hour = int(time_zone[0])
                time_zone_min = int(time_zone[1])
                if time_entries[1] == '+':
                    time_zone_hour *= -1
                dateadd = timedelta(hours=time_zone_hour, minutes=time_zone_min)
                time_zone_adjust = True

    try:
        date = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None

    try:
        date.strftime('%Y/%m-%b')
    except ValueError:
        return None

    if time_zone_adjust:
        date += dateadd

    return date


def get_oldest_timestamp(data, additional_groups_to_ignore, additional_tags_to_ignore, print_all_tags=False):
    date_available = False
    oldest_date = datetime.now()
    oldest_keys = []
    src_file = data['SourceFile']
    ignore_groups = ['ICC_Profile'] + additional_groups_to_ignore
    ignore_tags = ['SourceFile', 'XMP:HistoryWhen'] + additional_tags_to_ignore

    for key in data.keys():

        if (key not in ignore_tags) and (key.split(':')[0] not in ignore_groups) and 'GPS' not in key:
            date = data[key]
            if isinstance(date, list):
                date = date[0]
            try:
                exifdate = parse_date_exif(date)
            except Exception:
                exifdate = None
            if exifdate and exifdate < oldest_date:
                date_available = True
                oldest_date = exifdate
                oldest_keys = [key]
            elif exifdate and exifdate == oldest_date:
                oldest_keys.append(key)

    if not date_available:
        oldest_date = None
    return src_file, oldest_date, oldest_keys


def check_for_early_morning_photos(date, day_begins):
    if date.hour < day_begins:
        print('moving this photo to the previous day for classification purposes (day_begins=' + str(day_begins) + ')')
        date = date - timedelta(hours=date.hour+1)
    return date


class ExifTool(object):
    sentinel = "{ready}"

    def __init__(self, executable=exiftool_location, verbose=False):
        self.executable = executable
        self.verbose = verbose

    def __enter__(self):
        self.process = subprocess.Popen(
            ['perl', self.executable, "-stay_open", "True",  "-@", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.process.stdin.write(b'-stay_open\nFalse\n')
        self.process.stdin.flush()

    def execute(self, *args):
        args = args + ("-execute\n",)
        self.process.stdin.write(str.join("\n", args).encode('utf-8'))
        self.process.stdin.flush()
        output = ""
        fd = self.process.stdout.fileno()
        while not output.rstrip(' \t\n\r').endswith(self.sentinel):
            increment = os.read(fd, 4096)
            if self.verbose:
                sys.stdout.write(increment.decode('utf-8'))
            output += increment.decode('utf-8')
        return output.rstrip(' \t\n\r')[:-len(self.sentinel)]

    def get_metadata(self, *args):
        try:
            return json.loads(self.execute(*args))
        except ValueError:
            sys.stdout.write('No files to parse or invalid data\n')
            exit()


# ---------------------------------------

def sortPhotos(src_dir, dest_dir, sort_format, rename_format, recursive=False,
        copy_files=False, test=False, remove_duplicates=True, day_begins=0,
        additional_groups_to_ignore=['File'], additional_tags_to_ignore=[],
        use_only_groups=None, use_only_tags=None, verbose=True, keep_filename=False):

    if not os.path.exists(src_dir):
        raise Exception('Source directory does not exist')

    args = ['-j', '-a', '-G']
    if use_only_tags is not None:
        additional_groups_to_ignore = []
        additional_tags_to_ignore = []
        for t in use_only_tags:
            args += ['-' + t]
    elif use_only_groups is not None:
        additional_groups_to_ignore = []
        for g in use_only_groups:
            args += ['-' + g + ':Time:All']
    else:
        args += ['-time:all']

    if recursive:
        args += ['-r']
    args += [src_dir]

    if test:
        print("TEST MODE (no files will be moved/copied)")

    with ExifTool(verbose=verbose) as e:
        print('Preprocessing with ExifTool.  May take a while for a large number of files.')
        sys.stdout.flush()
        metadata = e.get_metadata(*args)

    num_files = len(metadata)
    print()

    if test:
        test_file_dict = {}

    moved_count = 0
    copied_count = 0
    skipped_count = 0
    duplicate_count = 0
    skipped_files = []
    duplicate_files = []
    cnt = 0

    for idx, data in enumerate(metadata):
        src_file, date, keys = get_oldest_timestamp(data, additional_groups_to_ignore, additional_tags_to_ignore)
        src_file.encode('utf-8')

        if verbose:
            ending = ']'
            if test:
                ending = '] (TEST - no files are being moved/copied)'
            print('[' + str(idx+1) + '/' + str(num_files) + ending)
            print('Source: ' + src_file)

        # if no valid date or hidden -> send to unknown folder
        if not date or os.path.basename(src_file).startswith('.'):
            skipped_count += 1
            skipped_files.append(src_file)
            if verbose:
                reason = "No valid date" if not date else "Hidden file"
                print(f"{reason}. Sending file to 'unknown' folder.\n")

            unknown_dir = os.path.join(dest_dir, "unknown")
            if not test and not os.path.exists(unknown_dir):
                os.makedirs(unknown_dir)

            filename = os.path.basename(src_file)
            dest_file = os.path.join(unknown_dir, filename)

            if test:
                test_file_dict[dest_file] = src_file
            else:
                if copy_files:
                    shutil.copy2(src_file, dest_file)
                else:
                    shutil.move(src_file, dest_file)
            continue

        if verbose:
            print('Date/Time: ' + str(date))
            print('Corresponding Tags: ' + ', '.join(keys))

        date = check_for_early_morning_photos(date, day_begins)
        dir_structure = date.strftime(sort_format)
        dirs = dir_structure.split('/')
        dest_file = dest_dir
        for thedir in dirs:
            dest_file = os.path.join(dest_file, thedir)
            if not test and not os.path.exists(dest_file):
                os.makedirs(dest_file)

        filename = os.path.basename(src_file)
        if rename_format is not None and date is not None:
            _, ext = os.path.splitext(filename)
            filename = date.strftime(rename_format) + ext.lower()

        dest_file = os.path.join(dest_file, filename)
        root, ext = os.path.splitext(dest_file)

        if verbose:
            name = 'Destination '
            name += '(copy): ' if copy_files else '(move): '
            print(name + dest_file)

        append = 1
        fileIsIdentical = False
        while True:
            if (not test and os.path.isfile(dest_file)) or (test and dest_file in (test_file_dict.keys() if test else [])):
                if test:
                    dest_compare = test_file_dict[dest_file]
                else:
                    dest_compare = dest_file
                if remove_duplicates and filecmp.cmp(src_file, dest_compare):
                    fileIsIdentical = True
                    if verbose:
                        print('Identical file already exists.  Duplicate will be ignored.\n')
                    break
                else:
                    if keep_filename:
                        orig_filename = os.path.splitext(os.path.basename(src_file))[0]
                        dest_file = root + '_' + orig_filename + '_' + str(append) + ext
                    else:
                        dest_file = root + '_' + str(append) + ext
                    append += 1
                    if verbose:
                        print('Same name already exists...renaming to: ' + dest_file)
            else:
                break

        if fileIsIdentical:
            duplicate_count += 1
            duplicate_files.append(src_file)
            continue

        if test:
            test_file_dict[dest_file] = src_file
            if copy_files:
                copied_count += 1
            else:
                moved_count += 1
        else:
            if copy_files:
                shutil.copy2(src_file, dest_file)
                copied_count += 1
                cnt += 1
            else:
                shutil.move(src_file, dest_file)
                moved_count += 1
                cnt += 1

        if verbose:
            print()
        else:
            action = "copying" if copy_files else "moving" 
            percent_complete(step=cnt, total_steps=num_files, title=action)

    total = moved_count + copied_count + skipped_count + duplicate_count
    summary_lines = []
    summary_lines.append("\n===== SUMMARY =====")
    if test:
        summary_lines.append("TEST MODE (no files actually moved/copied)\n")
    summary_lines.append(f"Total files processed: {total}")
    summary_lines.append(f"Moved files: {moved_count}")
    summary_lines.append(f"Copied files: {copied_count}")
    summary_lines.append(f"Sent to 'unknown' folder: {skipped_count}")
    summary_lines.append(f"Duplicates ignored: {duplicate_count}")
    summary_lines.append("===================")

    if skipped_files:
        summary_lines.append("\nFiles sent to 'unknown':")
        for f in skipped_files:
            summary_lines.append(" - " + f)

    if duplicate_files:
        summary_lines.append("\nDuplicate files ignored:")
        for f in duplicate_files:
            summary_lines.append(" - " + f)

    summary_text = "\n".join(summary_lines) + "\n"

    print(summary_text)

    with open("sortphotos_summary.log", "w", encoding="utf-8") as logf:
        logf.write(summary_text)


def main():
    import argparse
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
                                     description='Sort files (primarily photos and videos) into folders by date\nusing EXIF and other metadata')
    parser.add_argument('src_dir', type=str, help='source directory')
    parser.add_argument('dest_dir', type=str, help='destination directory')
    parser.add_argument('-r', '--recursive', action='store_true', help='search src_dir recursively')
    parser.add_argument('-c', '--copy', action='store_true', help='copy files instead of move')
    parser.add_argument('-s', '--silent', action='store_true', help='don\'t display parsing details.')
    parser.add_argument('-t', '--test', action='store_true', help='run a test. files will not be moved/copied\ninstead you will just see a list of what would happen')
    parser.add_argument('--sort', type=str, default='%Y/%m-%b',
                        help="choose destination folder structure using datetime format")
    parser.add_argument('--rename', type=str, default=None,
                        help="rename file using format codes. default is None (original filename)")
    parser.add_argument('--keep-filename', action='store_true', default=False,
                        help='In case of duplicated output filenames append original file name and number')
    parser.add_argument('--keep-duplicates', action='store_true',
                        help='If file is a duplicate keep it anyway (after renaming).')
    parser.add_argument('--day-begins', type=int, default=0, help='hour of day that new day begins (0-23)')
    parser.add_argument('--ignore-groups', type=str, nargs='+', default=[], help='groups to ignore')
    parser.add_argument('--ignore-tags', type=str, nargs='+', default=[], help='tags to ignore')
    parser.add_argument('--use-only-groups', type=str, nargs='+', default=None, help='restrict groups')
    parser.add_argument('--use-only-tags', type=str, nargs='+', default=None, help='restrict tags')

    args = parser.parse_args()

    sortPhotos(args.src_dir, args.dest_dir, args.sort, args.rename, args.recursive,
        args.copy, args.test, not args.keep_duplicates, args.day_begins,
        args.ignore_groups, args.ignore_tags, args.use_only_groups,
        args.use_only_tags, not args.silent, args.keep_filename)

if __name__ == '__main__':
    main()
